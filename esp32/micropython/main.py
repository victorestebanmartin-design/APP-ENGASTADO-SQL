# main.py — Panel produccion ENGASTADO (flat, sin clase ILI9341)
# Mismo enfoque que test_display.py que funcionó
# Protocolo: {"p":12,"e":5,"t":47,"hora":"10:45","fecha":"07/08"}\n

import sys
import json
import time
import select
from machine import SoftSPI, Pin
import framebuf

# ── Pines (verificados 4D Systems gen4-ESP32-24) ─────────────────────────────
Pin(4, Pin.OUT, value=1)                                        # backlight ON
spi = SoftSPI(baudrate=500_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
dc  = Pin(21, Pin.OUT, value=0)
rst = Pin(7,  Pin.OUT, value=1)

# ── Reset + init display ──────────────────────────────────────────────────────
rst(0); time.sleep_ms(100); rst(1); time.sleep_ms(250)

def _cmd(c, d=None):
    dc(0); spi.write(bytes([c]))
    if d: dc(1); spi.write(d)

_cmd(0x11); time.sleep_ms(120)
_cmd(0xCB, b'\x39\x2C\x00\x34\x02')
_cmd(0xCF, b'\x00\xC1\x30')
_cmd(0xE8, b'\x85\x00\x78')
_cmd(0xEA, b'\x00\x00')
_cmd(0xED, b'\x64\x03\x12\x81')
_cmd(0xF7, b'\x20')
_cmd(0xC0, b'\x1b')
_cmd(0xC1, b'\x10')
_cmd(0xC5, b'\x2d\x33')
_cmd(0x36, b'\x48')  # MX=1 corrige text direction (FPC invertido)
_cmd(0x3A, b'\x55')
_cmd(0xB1, b'\x00\x1d')
_cmd(0xB6, b'\x0A\x82')
_cmd(0xF2, b'\x00')
_cmd(0x26, b'\x01')
_cmd(0xE0, b'\x0F\x3a\x36\x0b\x0d\x06\x4c\x91\x31\x08\x10\x04\x11\x0c\x00')
_cmd(0xE1, b'\x00\x06\x0a\x05\x12\x09\x2c\x92\x3f\x08\x0e\x0b\x2e\x33\x0F')
_cmd(0x29); time.sleep_ms(100)
_cmd(0x21)  # INVON cancela REV=1 del DISCTRL (panel IPS)

def _window(x0, y0, x1, y1):
    _cmd(0x2A, bytes([x0>>8, x0&0xFF, x1>>8, x1&0xFF]))
    _cmd(0x2B, bytes([y0>>8, y0&0xFF, y1>>8, y1&0xFF]))
    dc(0); spi.write(b'\x2C')

def rect(x, y, w, h, color):
    _window(x, y, x+w-1, y+h-1)
    hi, lo = color>>8, color&0xFF
    chunk = bytes([hi, lo]*64)
    dc(1)
    n = w * h
    while n >= 64: spi.write(chunk); n -= 64
    if n: spi.write(bytes([hi, lo]*n))

def hline(x, y, w, color):
    rect(x, y, w, 1, color)

def char_big(x, y, ch, fg, bg, scale):
    buf = bytearray(8)
    fb  = framebuf.FrameBuffer(buf, 8, 8, framebuf.MONO_VLSB)
    fb.fill(0); fb.text(ch, 0, 0, 1)
    cw = 8 * scale
    ch_h = 8 * scale
    pixels = bytearray(cw * ch_h * 2)
    fh, fl = fg>>8, fg&0xFF
    bh, bl = bg>>8, bg&0xFF
    for row in range(8):
        for col in range(8):
            on = (buf[col] >> row) & 1
            hi = fh if on else bh
            lo = fl if on else bl
            for sy in range(scale):
                for sx in range(scale):
                    idx = ((row*scale+sy)*cw + col*scale+sx)*2
                    pixels[idx] = hi; pixels[idx+1] = lo
    _window(x, y, x+cw-1, y+ch_h-1)
    dc(1); spi.write(pixels)
    return cw

def text(x, y, s, fg, bg, scale=1):
    for ch in s:
        x += char_big(x, y, ch, fg, bg, scale) + scale

# Colores invertidos para panel IPS con INVON (el hardware invierte ~valor antes de mostrar)
BLACK=0x0000; WHITE=0xFFFF; YELLOW=0xFFE0; ORANGE=0xFD20
GREEN=0x07E0; RED=0xF800; DGRAY=0x4208; LGRAY=0x8410

Y_TITLE=6; Y_DATE=36; Y_SEP1=54; Y_ROW1=68; Y_ROW2=132; Y_ROW3=196
Y_SEP2=254; Y_STATUS=262

def draw_static():
    rect(0,0,240,320,BLACK)
    text(4,Y_TITLE,"ENGASTADO",WHITE,BLACK,scale=2)
    hline(0,Y_SEP1,240,DGRAY); hline(0,Y_SEP2,240,DGRAY)
    text(4,Y_ROW1+6,"PENDIENTES",YELLOW,BLACK,scale=2)
    text(4,Y_ROW2+6,"EN PROCESO",ORANGE,BLACK,scale=2)
    text(4,Y_ROW3+6,"TERMINADAS",GREEN,BLACK,scale=2)

def draw_num(y, color, val):
    s = "--" if val < 0 else str(val)
    rect(155, y, 82, 42, BLACK)
    x = 234 - len(s)*27
    text(x, y+4, s, color, BLACK, scale=3)

def draw_datetime(fecha, hora):
    rect(0,Y_DATE,240,17,BLACK)
    text(4,Y_DATE,fecha+"  "+hora,LGRAY,BLACK,scale=1)

def draw_sw_logo():
    W=WHITE; B=BLACK; G=LGRAY; DG=DGRAY; O=ORANGE
    rect(0, 0, 240, 320, W)
    # Badge superior
    text(8,   5, "Automated Crimping System", DG, W, scale=1)
    hline(20, 19, 200, DG)
    # COJO (negro grande) + sw (gris pequeño, bottom-aligned)
    text(12,  35, "COJO", B, W, scale=5)   # 4*45=180px, height=40
    text(192, 59, "sw",   G, W, scale=2)   # x=12+180, y=35+24 (bottom alineado)
    # Tagline
    text(35,  82, "Crimping Operations",  G, W, scale=1)
    text(21,  95, "Jobs & Orders Software", G, W, scale=1)
    hline(20, 108, 200, DG)
    # Acrónimo igual que el HTML
    text(5, 116, "C",  O, W, scale=1); text(19, 116, " Crimping",   B, W, scale=1)
    text(5, 130, "O",  O, W, scale=1); text(19, 130, " Operations", B, W, scale=1)
    text(5, 144, "J",  O, W, scale=1); text(19, 144, " Jobs",       B, W, scale=1)
    text(5, 158, "O",  O, W, scale=1); text(19, 158, " Orders",     B, W, scale=1)
    text(5, 172, "sw", G, W, scale=1); text(23, 172, " Software",   B, W, scale=1)
    hline(20, 190, 200, DG)
    # Meta
    text(30, 198, "MERAK - Knorr-Bremse", DG, W, scale=1)
    text(52, 212, "Version 3.0 Pro",      DG, W, scale=1)

def draw_status(ok, hora=""):
    rect(0,Y_STATUS,240,17,BLACK)
    if ok: text(4,Y_STATUS,"OK  "+hora,GREEN,BLACK,scale=1)
    else:  text(4,Y_STATUS,"Sin datos...",RED,BLACK,scale=1)

draw_sw_logo()

vp=ve=vt=-1; ultimo_rx=0; buf=""
poll=select.poll(); poll.register(sys.stdin,select.POLLIN)

while True:
    if poll.poll(1000):
        c=sys.stdin.read(1)
        if c=='\n':
            line=buf.strip(); buf=""
            if line.startswith('{'):
                try:
                    d=json.loads(line)
                    np=int(d.get('p',-1)); ne=int(d.get('e',-1)); nt=int(d.get('t',-1))
                    hora=str(d.get('hora','--:--')); fecha=str(d.get('fecha','--/--'))
                    if np!=vp: vp=np; draw_num(Y_ROW1,YELLOW,vp)
                    if ne!=ve: ve=ne; draw_num(Y_ROW2,ORANGE,ve)
                    if nt!=vt: vt=nt; draw_num(Y_ROW3,GREEN,vt)
                    draw_datetime(fecha,hora); ultimo_rx=time.ticks_ms(); draw_status(True,hora)
                except: pass
        elif c not in('\r','\x03','\x04'): buf+=c
    if ultimo_rx and time.ticks_diff(time.ticks_ms(),ultimo_rx)>90000:
        ultimo_rx=0; draw_status(False)