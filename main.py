import machine
import time
import random
import ujson
import urequests
from ili9341 import ILI9341
from scd4x import SCD4X
from xpt2046 import XPT2046
import boot
import font

# CYD Pinout
SPI_SCK, SPI_MOSI, SPI_MISO = 14, 13, 12
DISP_CS, DISP_DC, DISP_BL = 15, 2, 21
TOUCH_CLK, TOUCH_CS, TOUCH_DIN, TOUCH_DO = 25, 33, 32, 39
I2C_SCL, I2C_SDA = 22, 27
LDR_PIN = 34

# UI States
DASHBOARD = 0
GRAPHS = 1
CLOCK = 2

def main():
    # 1. Load Config
    config = {"tz_offset": 0, "city": "Atlanta", "sensor_name": "cyd-monitor"}
    print("Loading config.json...")
    try:
        with open('config.json', 'r') as f:
            config.update(ujson.load(f))
            print("Config loaded successfully.")
    except Exception as e:
        print("Error loading config.json:", e)
        print("Using defaults:", config)
    
    tz_offset = config['tz_offset']
    location = config['city']
    sensor_name = config['sensor_name']
    print(f"Active City: {location}, Sensor Name: {sensor_name}")
    i_url, i_org, i_bucket, i_token = config.get('influx_url'), config.get('influx_org'), config.get('influx_bucket'), config.get('influx_token')

    # 2. Init Hardware
    boot.connect_wifi()
    
    # Display
    spi_disp = machine.SPI(1, baudrate=40000000, sck=machine.Pin(SPI_SCK), mosi=machine.Pin(SPI_MOSI))
    display = ILI9341(spi_disp, cs=machine.Pin(DISP_CS), dc=machine.Pin(DISP_DC), rst=None, bl=machine.Pin(DISP_BL))
    display.clear(0)
    font.draw_text(display, "Initializing...", 20, 100, scale=2)

    # Touch (Software SPI often more reliable for touch on CYD)
    spi_touch = machine.SoftSPI(baudrate=1000000, sck=machine.Pin(TOUCH_CLK), mosi=machine.Pin(TOUCH_DIN), miso=machine.Pin(TOUCH_DO))
    touch = XPT2046(spi_touch, cs=machine.Pin(TOUCH_CS))

    # Sensors
    i2c = machine.I2C(1, scl=machine.Pin(I2C_SCL, machine.Pin.PULL_UP), sda=machine.Pin(I2C_SDA, machine.Pin.PULL_UP), freq=100000)
    scd = SCD4X(i2c)
    try: scd.stop_periodic_measurement()
    except: pass
    time.sleep(0.5)
    scd.start_periodic_measurement()
    ldr = machine.ADC(machine.Pin(LDR_PIN))
    ldr.atten(machine.ADC.ATTN_11DB)

    # Data Buffers (60 points for sparklines)
    history_co2 = [0] * 60
    history_temp = [0] * 60

    # Globals
    state = DASHBOARD
    last_sensor_read = 0
    last_display_update = 0
    last_weather_read = 0
    weather_str = "Loading..."
    co2, temp_f, humi, lux = 400, 72, 40, 50

    def get_weather():
        import gc
        gc.collect() # Maximize RAM before fetch
        try:
            # ?0 returns only the current day's forecast, reducing payload
            loc_query = location.replace(" ", "+")
            res = urequests.get(f"http://wttr.in/{loc_query}?0&format=j1")
            data = res.json()
            res.close()
            
            curr = data['current_condition'][0]
            today = data['weather'][0]
            
            cond = curr['weatherDesc'][0]['value']
            temp = curr['temp_F']
            high = today['maxtempF']
            low = today['mintempF']
            
            # Clean up memory
            del data
            gc.collect()
            
            return f"{cond} {temp}F H:{high} L:{low}"
        except Exception as e:
            print("Weather error:", e)
            return "Weather Unavailable"

    def draw_sparkline(data, x, y, w, h, color):
        if not data: return
        max_val = max(data) if max(data) > 0 else 1
        min_val = min(data)
        rng = max_val - min_val if max_val != min_val else 1
        
        step = w / (len(data) - 1)
        for i in range(len(data) - 1):
            y1 = y + h - int((data[i] - min_val) * h / rng)
            y2 = y + h - int((data[i+1] - min_val) * h / rng)
            display.fill_rect(x + int(i*step), min(y1, y2), 2, abs(y1-y2)+1, color)

    while True:
        now = time.time()
        state_changed = False

        # Check Touch
        t_pos = touch.get_touch()
        if t_pos:
            print("Touch detected at:", t_pos)
            state = (state + 1) % 3
            state_changed = True
            time.sleep(0.3) # Debounce

        # Update Sensors (60s)
        if now - last_sensor_read >= 60 or last_sensor_read == 0:
            try:
                m = scd.read_measurement()
                co2, temp_f, humi = m[0], (m[1] * 9/5) + 32, m[2]
                history_co2.pop(0); history_co2.append(co2)
                history_temp.pop(0); history_temp.append(temp_f)
                lux = 100 - (ldr.read() * 100 // 4095)
                last_sensor_read = now
                state_changed = True
                
                if i_url and i_token and i_org and i_bucket:
                    try:
                        url = f"{i_url}/api/v2/write?org={i_org}&bucket={i_bucket}&precision=s"
                        headers = {"Authorization": f"Token {i_token}"}
                        p = f"env,device={sensor_name},loc={location} co2={co2},temp={temp_f},humi={humi},lux={lux}"
                        r = urequests.post(url, data=p, headers=headers)
                        r.close()
                    except Exception as e:
                        print("InfluxDB error:", e)
            except: pass

        # Update Weather (30 min)
        if now - last_weather_read >= 1800 or last_weather_read == 0:
            weather_str = get_weather()
            last_weather_read = now
            state_changed = True

        # Render
        if state_changed or (now - last_display_update >= 60):
            display.clear(0)
            t = time.localtime(now + (tz_offset * 3600))
            time_str = "{:02d}:{:02d}".format(t[3], t[4])
            off_x, off_y = random.getrandbits(3), random.getrandbits(3)
            last_display_update = now

            if state == DASHBOARD:
                font.draw_text(display, weather_str, 5 + off_x, 5 + off_y, scale=1, color=0x7BEF)
                font.draw_char(display, 'clock', 10 + off_x, 30 + off_y, scale=1)
                font.draw_text(display, time_str, 30 + off_x, 30 + off_y, scale=2)
                
                c_color = 0x001F if co2 < 1000 else (0xFDA0 if co2 < 1400 else 0xF800)
                font.draw_char(display, 'molecule', 5 + off_x, 65 + off_y, scale=1, color=c_color)
                font.draw_text(display, f"{co2}ppm", 30 + off_x, 70 + off_y, scale=3, color=c_color)
                draw_sparkline(history_co2, 180 + off_x, 75 + off_y, 100, 30, c_color)

                font.draw_char(display, 'therm', 5 + off_x, 125 + off_y, scale=1, color=0x07E0)
                font.draw_text(display, f"{temp_f:.1f}F", 30 + off_x, 130 + off_y, scale=2, color=0x07E0)
                draw_sparkline(history_temp, 180 + off_x, 135 + off_y, 100, 20, 0x07E0)

                font.draw_char(display, 'drop', 5 + off_x, 165 + off_y, scale=1, color=0x07FF)
                font.draw_text(display, f"{humi:.1f}%", 30 + off_x, 170 + off_y, scale=2)

                font.draw_char(display, 'sun', 5 + off_x, 205 + off_y, scale=1)
                font.draw_text(display, f"L:{lux}%", 30 + off_x, 210 + off_y, scale=2)

            elif state == GRAPHS:
                font.draw_text(display, "CO2 History (1h)", 10, 10, scale=2, color=0x07FF)
                draw_sparkline(history_co2, 20, 40, 280, 100, 0x07FF)
                font.draw_text(display, "Temp History (1h)", 10, 150, scale=2, color=0x07E0)
                draw_sparkline(history_temp, 20, 180, 280, 40, 0x07E0)

            elif state == CLOCK:
                font.draw_text(display, time_str, 20 + off_x, 80 + off_y, scale=8)
                font.draw_text(display, weather_str, 40 + off_x, 180 + off_y, scale=2, color=0x7BEF)

        time.sleep(0.1)

if __name__ == "__main__":
    main()
