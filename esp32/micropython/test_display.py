# test_display.py — SoftSPI para eliminar problemas de hardware SPI
from machine import SoftSPI, Pin, PWM
import time

# Backlight: probar ambos niveles con blink para confirmar cuál enciende
p4 = Pin(4, Pin.OUT, value=1)   # HIGH primero
time.sleep_ms(500)
p4(0)                           # LOW
time.sleep_ms(500)
p4(1)                           # HIGH = dejamos encendido si HIGH=ON
# Si la pantalla sigue negra pero el backlight parpadea → problema es el SPI/init
# Si no hay parpadeo → prueba con PWM abajo
# pwm_bl = PWM(Pin(4), freq=25000, duty_u16=65535)

# SoftSPI: más lento pero no depende del hardware SPI del chip
spi = SoftSPI(baudrate=500_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
dc  = Pin(21, Pin.OUT, value=0)
rst = Pin(7,  Pin.OUT, value=1)

# HW reset con tiempos más largos
rst(0); time.sleep_ms(100); rst(1); time.sleep_ms(250)

def cmd(c, d=None):
    dc(0); spi.write(bytes([c]))
    if d: dc(1); spi.write(d)

# Secuencia exacta Init_Commandili de 4D Systems (gfx4desp32_gen4_ESP32_24_Init.h)
# Sleep Out primero, luego registros extendidos
cmd(0x11); time.sleep_ms(120)             # Sleep Out
cmd(0xCB, b'\x39\x2C\x00\x34\x02')       # Power Control A
cmd(0xCF, b'\x00\xC1\x30')               # Power Control B
cmd(0xE8, b'\x85\x00\x78')               # Driver Timing Control A
cmd(0xEA, b'\x00\x00')                   # Driver Timing Control B
cmd(0xED, b'\x64\x03\x12\x81')           # Power On Sequence Control
cmd(0xF7, b'\x20')                       # Pump Ratio Control
cmd(0xC0, b'\x1b')                       # Power Control 1 (VRH)
cmd(0xC1, b'\x10')                       # Power Control 2
cmd(0xC5, b'\x2d\x33')                   # VCOM Control 1
cmd(0x36, b'\x08')                       # MADCTL BGR, sin espejo (igual que 4D)
cmd(0x3A, b'\x55')                       # Pixel Format 16-bit
cmd(0xB1, b'\x00\x1d')                   # Frame Rate Control
cmd(0xB6, b'\x0A\x82')                   # Display Function Control
cmd(0xF2, b'\x00')                       # Enable 3G off
cmd(0x26, b'\x01')                       # Gamma Set
cmd(0xE0, b'\x0F\x3a\x36\x0b\x0d\x06\x4c\x91\x31\x08\x10\x04\x11\x0c\x00')
cmd(0xE1, b'\x00\x06\x0a\x05\x12\x09\x2c\x92\x3f\x08\x0e\x0b\x2e\x33\x0F')
cmd(0x29)                                # Display ON
time.sleep_ms(50)

def fill(color):
    hi, lo = color >> 8, color & 0xFF
    cmd(0x2A, b'\x00\x00\x00\xEF')  # cols 0-239
    cmd(0x2B, b'\x00\x00\x01\x3F')  # rows 0-319
    dc(0); spi.write(b'\x2C')
    dc(1)
    chunk = bytes([hi, lo] * 64)
    n = 240 * 320
    while n >= 64: spi.write(chunk); n -= 64
    if n: spi.write(bytes([hi, lo] * n))

def rect(x, y, w, h, color):
    hi, lo = color >> 8, color & 0xFF
    xs, xe = x, x + w - 1
    ys, ye = y, y + h - 1
    cmd(0x2A, bytes([xs>>8,xs&0xFF,xe>>8,xe&0xFF]))
    cmd(0x2B, bytes([ys>>8,ys&0xFF,ye>>8,ye&0xFF]))
    dc(0); spi.write(b'\x2C')
    dc(1)
    chunk = bytes([hi, lo] * 64)
    n = w * h
    while n >= 64: spi.write(chunk); n -= 64
    if n: spi.write(bytes([hi, lo] * n))

# ── pintar pantalla de prueba ──────────────────────────────────────────────────
fill(0x0000)            # negro

rect(0,   0,  240, 50, 0x001F)  # franja azul
rect(0,  50,  240, 10, 0x4208)  # separador gris
rect(0,  70,  240, 60, 0xFFE0)  # franja amarilla (PENDIENTES)
rect(0, 140,  240, 60, 0xFD20)  # franja naranja (EN PROCESO)
rect(0, 210,  240, 60, 0x07E0)  # franja verde  (TERMINADAS)
rect(0, 270,  240, 10, 0x4208)  # separador gris

print("test_display OK - pantalla con franjas de colores")
