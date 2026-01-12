import machine
import time
import ustruct

class XPT2046:
    def __init__(self, spi, cs, irq=None):
        self.spi = spi
        self.cs = cs
        self.irq = irq
        
        self.cs.init(self.cs.OUT, value=1)
        if self.irq:
            self.irq.init(self.irq.IN)

    def _read_coord(self, cmd):
        self.cs.value(0)
        self.spi.write(bytearray([cmd]))
        data = self.spi.read(2)
        self.cs.value(1)
        # 12-bit result is in the middle of 2 bytes
        return ((data[0] << 8) | data[1]) >> 4

    def get_touch(self):
        # Pressure (Z1) - Increase threshold to prevent phantom noise
        z1 = self._read_coord(0xB1)
        if z1 < 200: return None
        
        # Multiple samples for stability
        x_raw = 0
        y_raw = 0
        samples = 3
        for _ in range(samples):
            x_raw += self._read_coord(0x91) # X
            y_raw += self._read_coord(0xD1) # Y
        
        x_raw //= samples
        y_raw //= samples
        
        # Calibration for 240x320 landscape (CYD specific approximate)
        # X raw is usually ~200 to ~3800
        # Y raw is usually ~200 to ~3800
        x = int((x_raw - 200) * 320 / 3600)
        y = int((y_raw - 200) * 240 / 3600)
        
        # Constrain
        x = max(0, min(x, 319))
        y = max(0, min(y, 239))
        
        return (x, y)
