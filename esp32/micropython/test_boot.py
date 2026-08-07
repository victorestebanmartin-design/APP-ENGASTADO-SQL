from machine import SoftSPI,Pin
import time
Pin(4,Pin.OUT,value=1)
spi=SoftSPI(baudrate=500000,sck=Pin(14),mosi=Pin(13),miso=Pin(12))
dc=Pin(21,Pin.OUT,value=0)
rst=Pin(7,Pin.OUT,value=1)
rst(0);time.sleep_ms(100);rst(1);time.sleep_ms(250)
def cmd(c,d=None):
    dc(0);spi.write(bytes([c]))
    if d:dc(1);spi.write(d)
cmd(0x11);time.sleep_ms(120)
cmd(0x36,b'\x48');cmd(0x3A,b'\x55')
cmd(0x29);time.sleep_ms(50);cmd(0x21)
cmd(0x2A,b'\x00\x00\x00\xEF')
cmd(0x2B,b'\x00\x00\x01\x3F')
dc(0);spi.write(b'\x2C');dc(1)
chunk=bytes([0x07,0xE0]*64)
n=76800
while n>=64:spi.write(chunk);n-=64
print("VERDE_BOOT_OK")
