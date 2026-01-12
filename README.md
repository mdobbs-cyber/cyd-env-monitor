# ESP32 CYD Environmental Monitor (SCD40)

Real-time air quality monitoring for the ESP32-2432S028 (Cheap Yellow Display). This project features a touch-responsive UI, historical sparklines, and live weather data integration.

![Dashboard View](https://via.placeholder.com/320x240?text=Dashboard+View) <!-- Replace with actual screenshot if available -->

## Features
- **Triple-View UI**: Cycle between Dashboard, Graphs, and Big Clock views via touch.
- **Sensors**: CO2, Temperature, Humidity (SCD40) and Ambient Light (LDR).
- **Historical Data**: Real-time sparklines for CO2 and Temperature (1-hour history).
- **Live Weather**: Integrated weather data from `wttr.in` based on your zip code.
- **MicroPython Powered**: High performance with easy customization.
- **Burn-in Protection**: Dynamic UI jittering to protect the LCD.
- **Data Logging**: Optional integration with InfluxDB/Grafana.

## Hardware Requirement
- **ESP32-2432S028**: Also known as the "Cheap Yellow Display" (CYD).
- **Sensata SCD40/SCD41**: High-accuracy CO2, temperature, and humidity sensor.
- **Wiring (I2C)**:
    - SCL: IO22
    - SDA: IO27
    - VCC: 3.3V / 5V
    - GND: GND

## Installation

### 1. Flash MicroPython
Flash your ESP32 with the latest MicroPython firmware from [micropython.org](https://micropython.org/download/esp32/).

### 2. Configure Your Device
1. Rename `config.json.example` to `config.json`.
2. Fill in your WiFi, Zip Code (for weather), and optional InfluxDB credentials.

```json
{
    "ssid": "YOUR_WIFI_SSID",
    "password": "YOUR_WIFI_PASSWORD",
    "tz_offset": -5,
    "city": "Atlanta",
    "sensor_name": "living-room",
    "influx_url": "...",
    "influx_org": "...",
    "influx_bucket": "...",
    "influx_token": "..."
}
```

### 3. Upload Files
Upload the following to the root of your ESP32:
- `boot.py`
- `main.py`
- `scd4x.py`
- `ili9341.py`
- `xpt2046.py` (Touch driver)
- `font.py`
- `config.json`

Recommended tool: `mpremote cp * :`

## Navigation
Tapping anywhere on the screen cycles through the interactive views:
1. **Dashboard**: Current metrics + sparklines.
2. **Graphs**: Full-screen history for CO2 and Temperature.
3. **Big Clock**: Large digital clock with weather forecast.

## Data Logging (Optional)
If InfluxDB credentials are provided in `config.json`, the device will push sensor data every 60 seconds. This is compatible with InfluxDB v2 and Grafana Cloud's InfluxDB endpoint.

## License
MIT
