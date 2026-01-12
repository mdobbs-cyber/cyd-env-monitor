import time
from machine import I2C

class SCD4X:
    DEFAULT_ADDR = 0x62

    def __init__(self, i2c, addr=DEFAULT_ADDR):
        self._i2c = i2c
        self._addr = addr
        self._data = [0, 0, 0] # CO2, Temp, Humidity

    def _send_command(self, cmd):
        self._i2c.writeto(self._addr, cmd.to_bytes(2, 'big'))

    def _read_data(self, nbytes):
        return self._i2c.readfrom(self._addr, nbytes)

    def start_periodic_measurement(self):
        self._send_command(0x21b1)

    def stop_periodic_measurement(self):
        try:
            self._send_command(0x3f86)
            time.sleep(0.5)
        except:
            pass # Might fail if already stopped

    def read_measurement(self):
        self._send_command(0xec05)
        time.sleep(0.001)
        data = self._read_data(9)
        
        # Unpack and verify CRC (simplified: skip CRC for now)
        co2 = (data[0] << 8) | data[1]
        temp_raw = (data[3] << 8) | data[4]
        humi_raw = (data[6] << 8) | data[7]
        
        temp = -45 + 175 * temp_raw / 65536
        humi = 100 * humi_raw / 65536
        
        self._data = [co2, temp, humi]
        return self._data

    @property
    def co2(self):
        return self._data[0]

    @property
    def temperature(self):
        return self._data[1]

    @property
    def humidity(self):
        return self._data[2]
