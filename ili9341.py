import machine
import time
import ustruct

# Constants for ILI9341
LCD_WIDTH = 240
LCD_HEIGHT = 320

class ILI9341:
    def __init__(self, spi, cs, dc, rst=None, bl=None, rotation=3):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.bl = bl
        self.width = 240
        self.height = 320
        
        self.cs.init(self.cs.OUT, value=1)
        self.dc.init(self.dc.OUT, value=0)
        
        if self.rst and self.rst != -1:
            self.rst.init(self.rst.OUT, value=1)
            self.reset()
        
        if self.bl and self.bl != -1:
            self.bl.init(self.bl.OUT)
            self.backlight(True)
            
        self.init()

    def backlight(self, on):
        if self.bl and self.bl != -1:
            self.bl.value(1 if on else 0)

    def _write_cmd(self, cmd):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytearray([cmd]))
        self.cs.value(1)

    def _write_data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(data)
        self.cs.value(1)

    def reset(self):
        self.rst.value(0)
        time.sleep(0.05)
        self.rst.value(1)
        time.sleep(0.05)

    def init(self, rotation=3):
        # Rotation 3 is landscape 270 degrees
        # MADCTL bits: MY, MX, MV, ML, BGR, MH
        madctl = [
            0x48, # 0: Portrait
            0x28, # 1: Landscape
            0x88, # 2: Portrait 180
            0xE8  # 3: Landscape 270
        ][rotation % 4]
        
        if rotation % 2 == 1:
            self.width, self.height = 320, 240
        else:
            self.width, self.height = 240, 320
        
        for cmd, data in [
            (0x01, None), # Soft reset
            (0x11, None), # Sleep out
            (0x3A, b'\x55'), # Interface pixel format (16-bit)
            (0x36, bytearray([madctl])), # MADCTL
            (0x29, None), # Display on
        ]:
            if data:
                self._write_cmd(cmd)
                self._write_data(data)
            else:
                self._write_cmd(cmd)
                time.sleep(0.1)

    def set_window(self, x0, y0, x1, y1):
        self._write_cmd(0x2A) # Column addr set
        self._write_data(ustruct.pack(">HH", x0, x1))
        self._write_cmd(0x2B) # Row addr set
        self._write_data(ustruct.pack(">HH", y0, y1))
        self._write_cmd(0x2C) # Memory write

    def fill_rect(self, x, y, w, h, color):
        x = max(0, min(x, self.width - 1))
        y = max(0, min(y, self.height - 1))
        w = min(w, self.width - x)
        h = min(h, self.height - y)
        self.set_window(x, y, x + w - 1, y + h - 1)
        chunk_size = 1024
        buf = ustruct.pack(">H", color) * chunk_size
        pixels = w * h
        self.dc.value(1)
        self.cs.value(0)
        for _ in range(pixels // chunk_size):
            self.spi.write(buf)
        
        remainder = pixels % chunk_size
        if remainder > 0:
            self.spi.write(buf[:remainder * 2])
        
        self.cs.value(1)

    def clear(self, color=0):
        self.fill_rect(0, 0, self.width, self.height, color)

    def color565(self, r, g, b):
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
