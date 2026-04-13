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
WEATHER = 1
NUM_SCREENS = 2

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
    auto_scroll = config.get('auto_scroll', False)
    scroll_interval = config.get('scroll_interval', 30)
    print(f"Active City: {location}, Sensor Name: {sensor_name}")
    print(f"Auto-scroll: {auto_scroll}, Interval: {scroll_interval}s")
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
    weather_data = None
    weather_str = "Loading..."
    co2, temp_f, humi, lux = 400, 72, 40, 50
    last_scroll = 0

    def get_weather():
        import gc
        gc.collect() # Maximize RAM before fetch
        try:
            lat = config.get("lat")
            lon = config.get("lon")
            if lat is None or lon is None:
                loc_query = location.replace(" ", "+")
                url_geo = f"http://geocoding-api.open-meteo.com/v1/search?name={loc_query}&count=1&format=json"
                r_geo = urequests.get(url_geo)
                geo_data = r_geo.json()
                r_geo.close()
                if not geo_data.get("results"):
                    return "Geo Error"
                lat = geo_data["results"][0]["latitude"]
                lon = geo_data["results"][0]["longitude"]
                config["lat"] = lat
                config["lon"] = lon
                del geo_data
                gc.collect()

            url = f"http://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto&forecast_days=1"
            res = urequests.get(url)
            data = res.json()
            res.close()
            
            curr = data['current']
            daily = data['daily']
            
            code = curr['weather_code']
            wmo = {0:"Clear", 1:"Clear", 2:"Cloudy", 3:"Overcast", 45:"Fog", 48:"Fog", 51:"Drizzle", 53:"Drizzle", 55:"Drizzle", 61:"Rain", 63:"Rain", 65:"Rain", 71:"Snow", 73:"Snow", 75:"Snow", 95:"Storm"}
            cond = wmo.get(code, "Unknown")
            
            # Map weather codes to icon names
            icon_map = {0:"sun_lg", 1:"sun_lg", 2:"cloud_lg", 3:"cloud_lg", 45:"fog_lg", 48:"fog_lg", 51:"rain_lg", 53:"rain_lg", 55:"rain_lg", 61:"rain_lg", 63:"rain_lg", 65:"rain_lg", 71:"snow_lg", 73:"snow_lg", 75:"snow_lg", 95:"storm_lg"}
            icon = icon_map.get(code, "cloud_lg")
            
            temp = int(curr['temperature_2m'])
            high = int(daily['temperature_2m_max'][0])
            low = int(daily['temperature_2m_min'][0])
            
            # Clean up memory
            del data
            gc.collect()
            
            return {"cond": cond, "icon": icon, "temp": temp, "high": high, "low": low}
        except Exception as e:
            print("Weather error:", e)
            return None

    def is_dst(year, month, day, hour):
        # DST starts 2nd Sunday of March, ends 1st Sunday of November
        # Simple rule for North America
        if month < 3 or month > 11: return False
        if month > 3 and month < 11: return True
        
        # Calculate days since start of year for first day of transition months
        # (Approximate but works for DST boundaries)
        # For March: 2nd Sunday
        if month == 3:
            # Day of week for March 1st (0=Mon, 6=Sun)
            # Simplified for MicroPython without full calendar module:
            # time.localtime(time.mktime((year, 3, 1, 0, 0, 0, 0, 0)))[6]
            import time
            first_march = time.mktime((year, 3, 1, 0, 0, 0, 0, 0))
            wday = time.localtime(first_march)[6]
            # 2nd Sunday: 1st Sunday is 1 + (6-wday)%7. 2nd Sunday is that + 7.
            second_sun = 1 + (6 - wday) % 7 + 7
            if day > second_sun: return True
            if day < second_sun: return False
            return hour >= 2
            
        # For November: 1st Sunday
        if month == 11:
            import time
            first_nov = time.mktime((year, 11, 1, 0, 0, 0, 0, 0))
            wday = time.localtime(first_nov)[6]
            # 1st Sunday: 1 + (6-wday)%7
            first_sun = 1 + (6 - wday) % 7
            if day > first_sun: return False
            if day < first_sun: return True
            return hour < 2
            
        return False

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
            state = (state + 1) % NUM_SCREENS
            state_changed = True
            last_scroll = now
            time.sleep(0.3) # Debounce

        # Auto-scroll between screens
        if auto_scroll and (now - last_scroll >= scroll_interval):
            state = (state + 1) % NUM_SCREENS
            state_changed = True
            last_scroll = now

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
            wd = get_weather()
            if wd:
                weather_data = wd
                weather_str = f"{wd['cond']} {wd['temp']}F H:{wd['high']} L:{wd['low']}"
            last_weather_read = now
            state_changed = True

        # Render
        if state_changed or (now - last_display_update >= 60):
            display.clear(0)
            
            # Apply Timezone and DST
            local_time_s = now + (tz_offset * 3600)
            t_base = time.localtime(local_time_s)
            
            final_offset = tz_offset
            if config.get("use_dst", False):
                if is_dst(t_base[0], t_base[1], t_base[2], t_base[3]):
                    final_offset += 1
            
            t = time.localtime(now + (final_offset * 3600))
            time_str = "{:02d}:{:02d}".format(t[3], t[4])
            off_x, off_y = random.getrandbits(3), random.getrandbits(3)
            last_display_update = now

            if state == DASHBOARD:
                # --- Header bar ---
                display.fill_rect(0, 0, 320, 36, 0x18E3)
                if weather_data:
                    ic = 0xFFE0 if weather_data['icon'] == 'sun_lg' else 0xBDF7
                    font.draw_icon32(display, weather_data['icon'], 2, 2, scale=1, color=ic)
                    font.draw_text(display, weather_data['cond'], 38, 4, scale=1, color=0xFFFF)
                    font.draw_text(display, f"{weather_data['temp']}F", 38, 16, scale=2, color=0xFDA0)
                else:
                    font.draw_text(display, weather_str, 8, 12, scale=1, color=0x7BEF)
                font.draw_text(display, time_str, 246, 10, scale=2, color=0xFFFF)
                
                # --- Card grid (2x2) ---
                cx1, cx2, cy1, cy2 = 4, 162, 40, 137
                cw, ch, bw = 154, 93, 138
                c_color = 0x001F if co2 < 1000 else (0xFDA0 if co2 < 1400 else 0xF800)
                
                # Draw card backgrounds + colored left accents
                for cx, cy, ac in [(cx1,cy1,c_color),(cx2,cy1,0x07E0),(cx1,cy2,0x07FF),(cx2,cy2,0xFFE0)]:
                    display.fill_rect(cx, cy, cw, ch, 0x10A2)
                    display.fill_rect(cx, cy, 3, ch, ac)
                
                # CO2 card
                font.draw_text(display, "CO2", cx1+8, cy1+4, scale=1, color=0x7BEF)
                font.draw_char(display, 'molecule', cx1+8, cy1+16, scale=1, color=c_color)
                font.draw_text(display, f"{co2}ppm", cx1+28, cy1+20, scale=2, color=c_color)
                draw_sparkline(history_co2, cx1+8, cy1+55, bw, 30, c_color)
                
                # Temp card
                font.draw_text(display, "TEMP", cx2+8, cy1+4, scale=1, color=0x7BEF)
                font.draw_char(display, 'therm', cx2+8, cy1+16, scale=1, color=0x07E0)
                font.draw_text(display, f"{temp_f:.1f}F", cx2+28, cy1+20, scale=2, color=0x07E0)
                draw_sparkline(history_temp, cx2+8, cy1+55, bw, 30, 0x07E0)
                
                # Humidity card
                font.draw_text(display, "HUMIDITY", cx1+8, cy2+4, scale=1, color=0x7BEF)
                font.draw_char(display, 'drop', cx1+8, cy2+18, scale=1, color=0x07FF)
                font.draw_text(display, f"{humi:.1f}%", cx1+28, cy2+22, scale=2, color=0x07FF)
                display.fill_rect(cx1+8, cy2+58, bw, 8, 0x2104)
                hw = max(0, min(int(humi * bw / 100), bw))
                display.fill_rect(cx1+8, cy2+58, hw, 8, 0x07FF)
                
                # Light card
                font.draw_text(display, "LIGHT", cx2+8, cy2+4, scale=1, color=0x7BEF)
                font.draw_char(display, 'sun', cx2+8, cy2+18, scale=1, color=0xFFE0)
                font.draw_text(display, f"{lux}%", cx2+28, cy2+22, scale=2, color=0xFFE0)
                display.fill_rect(cx2+8, cy2+58, bw, 8, 0x2104)
                lw = max(0, min(int(lux * bw / 100), bw))
                display.fill_rect(cx2+8, cy2+58, lw, 8, 0xFFE0)


            elif state == WEATHER:
                if weather_data:
                    wd = weather_data
                    # --- Large weather icon (64x64 at scale 2) ---
                    icon_color = 0xFFE0 if wd['icon'] == 'sun_lg' else 0xFFFF
                    font.draw_icon32(display, wd['icon'], 10, 10, scale=2, color=icon_color)
                    
                    # --- Condition text ---
                    font.draw_text(display, wd['cond'], 80, 18, scale=3, color=0xFFFF)
                    
                    # --- Current temp (large, warm amber) ---
                    temp_str = f"{wd['temp']}F"
                    font.draw_text(display, temp_str, 80, 50, scale=4, color=0xFDA0)
                    
                    # --- Gradient accent bar (orange -> cyan) ---
                    bar_y = 100
                    for bx in range(280):
                        # Blend from orange (0xFDA0) to cyan (0x07FF)
                        ratio = bx / 280
                        r = int(31 * (1 - ratio))
                        g = int(45 + (63 - 45) * ratio)
                        b = int(0 + 31 * ratio)
                        c = (r << 11) | (g << 5) | b
                        display.fill_rect(20 + bx, bar_y, 1, 3, c)
                    
                    # --- High / Low temps ---
                    # Up arrow for high
                    for a in range(5):
                        display.fill_rect(45 - a, 120 + a, 1 + a * 2, 1, 0xFB20)
                    font.draw_text(display, f"High {wd['high']}F", 55, 118, scale=2, color=0xFB20)
                    
                    # Down arrow for low
                    for a in range(5):
                        display.fill_rect(45 - a, 160 - a, 1 + a * 2, 1, 0x07FF)
                    font.draw_text(display, f"Low {wd['low']}F", 55, 148, scale=2, color=0x07FF)
                    
                    # --- Thin separator ---
                    display.fill_rect(20, 178, 280, 1, 0x4208)
                    
                    # --- City and time at bottom ---
                    font.draw_text(display, location, 10, 192, scale=2, color=0x7BEF)
                    font.draw_text(display, time_str, 220, 192, scale=3, color=0xFFFF)
                else:
                    font.draw_text(display, "Weather", 40, 80, scale=4, color=0x7BEF)
                    font.draw_text(display, "Loading...", 60, 140, scale=2, color=0xFFFF)

        time.sleep(0.1)

if __name__ == "__main__":
    main()
