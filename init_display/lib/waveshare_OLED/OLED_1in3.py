from . import config
import time

OLED_WIDTH = 128  # OLED width
OLED_HEIGHT = 64  # OLED height

class OLED_1in3(config.RaspberryPi):
    def __init__(self):
        super().__init__()
        self.width = OLED_WIDTH
        self.height = OLED_HEIGHT

    def command(self, cmd):
        self.digital_write(self.DC_PIN, False)
        self.spi_writebyte([cmd])

    def init_display(self):
        if self.module_init() != 0:
            return -1

        self.reset()
        time.sleep(0.1)

        commands = [
            0xAE,  # turn off oled panel
            0x02,  # set low column address
            0x10,  # set high column address
            0x40,  # set start line address
            0x81,  # set contrast control register
            0xA0,  # Set SEG/Column Mapping
            0xC0,  # Set COM/Row Scan Direction
            0xA6,  # set normal display
            0xA8,  # set multiplex ratio(1 to 64)
            0x3F,  # 1/64 duty
            0xD3,  # set display offset
            0x00,  # not offset
            0xD5,  # set display clock divide ratio/oscillator frequency
            0x80,  # set divide ratio, Set Clock as 100 Frames/Sec
            0xD9,  # set pre-charge period
            0xF1,  # Set Pre-Charge as 15 Clocks & Discharge as 1 Clock
            0xDA,  # set com pins hardware configuration
            0x12,
            0xDB,  # set vcomh
            0x40,  # Set VCOM Deselect Level
            0x20,  # Set Page Addressing Mode
            0x02,
            0xA4,  # Disable Entire Display On
            0xA6,  # Disable Inverse Display On
        ]

        for cmd in commands:
            self.command(cmd)

        time.sleep(0.1)
        self.command(0xAF)  # turn on oled panel

    def reset(self):
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.1)
        self.digital_write(self.RST_PIN, False)
        time.sleep(0.1)
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.1)

    def get_buffer(self, image):
        buf = [0xFF] * ((self.width // 8) * self.height)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()

        if imwidth == self.width and imheight == self.height:
            for y in range(imheight):
                for x in range(imwidth):
                    if pixels[x, y] == 0:
                        buf[x + (y // 8) * self.width] &= ~(1 << (y % 8))
        elif imwidth == self.height and imheight == self.width:
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    if pixels[x, y] == 0:
                        buf[(newx + (newy // 8) * self.width)] &= ~(1 << (y % 8))
        return buf

    def show_image(self, buf):        
        for page in range(8):
            self.command(0xB0 + page)  # set page address
            self.command(0x02)  # set low column address
            self.command(0x10)  # set high column address
            
            self.digital_write(self.DC_PIN, True)

            for i in range(self.width):
                self.spi_writebyte([~buf[i + self.width * page]])

    def clear(self):
        _buffer = [0xFF] * (self.width * self.height // 8)
        self.show_image(_buffer)

