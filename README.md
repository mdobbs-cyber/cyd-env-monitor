# ESP32 CYD Environmental Monitor (SCD40)

This project displays real-time CO2, Temperature, and Humidity readings from an SCD40 sensor on an ESP32-2432S028 (Cheap Yellow Display).

## Features
- WiFi connection for NTP time sync.
- Real-time sensor data reading.
- Burn-in protection (jittering text/screen clearing).
- MicroPython based.

## Hardware Wiring
| Component | ESP32 Pin |
|-----------|-----------|
| SCD40 SCL | IO22      |
| SCD40 SDA | IO27      |
| SCD40 VCC | 3.3V / 5V |
| SCD40 GND | GND       |

## Installation Guide

### 1. Flash MicroPython
1. Download the latest MicroPython firmware for ESP32 from [micropython.org](https://micropython.org/download/esp32/).
2. Use `esptool.py` to flash the firmware:
   ```bash
   esptool.py --chip esp32 --port /dev/ttyUSB0 erase_flash
   esptool.py --chip esp32 --port /dev/ttyUSB0 --baud 460800 write_flash -z 0x1000 esp32-xxxx.bin
   ```

### 2. Configure WiFi
Create a file named `config.json` on the device (or edit the local one) with your credentials:
```json
{
    "ssid": "YOUR_WIFI_SSID",
    "password": "YOUR_WIFI_PASSWORD"
}
```

### 3. Upload Files
Upload the following files to your ESP32:
- `boot.py`
- `main.py`
- `scd4x.py`
- `ili9341.py`
- `font.py`
- `config.json`

Recommended command using `mpremote`:
```bash
mpremote cp boot.py main.py scd4x.py ili9341.py font.py config.json :
```

### 4. Run
Restart the board. It will connect to WiFi, sync time, and begin displaying sensor data.

## Grafana Cloud Integration (Optional)

The app can push metrics every minute using the InfluxDB Line Protocol. If the credentials are missing from `config.json`, this feature is disabled.

### 1. Get Credentials
1. Log in to [Grafana Cloud](https://grafana.com/products/cloud/).
2. Go to **Cloud Portal** -> **InfluxDB** (or **Prometheus** -> **InfluxDB compatible endpoint**).
3. Copy the **URL** (it should look like `https://influx-prod-xx.../api/v1/push/influx/write`).
4. Note your **Username/User ID** (numeric).
5. Generate an **API Token** with `MetricsPublisher` or `write` permissions.

### 2. Update config.json
Fill in the values in your local `config.json`:
```json
{
    "grafana_url": "...",
    "grafana_user": "...",
    "grafana_token": "..."
}
```

### 3. Verify
Check the serial output for `Grafana push status: 204`. Use the **Explore** view in Grafana with the InfluxDB data source to see your metrics (`co2`, `temp_f`, `humidity`, `light`).

## Note on Burn-in Protection
The app jitters the display contents and periodically clears the screen to prevent static image retention on the LCD.

## Note on VOC
The SCD40 measures CO2. VOC readings would require an additional sensor like the SGP40.
