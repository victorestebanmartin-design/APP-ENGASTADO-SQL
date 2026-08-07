# main_wifi.py — Panel COJOsw vía WiFi (sin cable USB)
# Subir con: mpremote connect COM5 cp esp32\micropython\main_wifi.py :main.py + reset
#
# ANTES DE SUBIR: ajusta SSID, PASSWORD y HOST_IP abajo.
# Activa el hotspot móvil del PC: Configuración → Sistema → Hotspot móvil
# El PC tendrá la IP 192.168.137.1 por defecto con hotspot Windows.

import time
import json
import network
import socket
from machine import SoftSPI, Pin
import framebuf

# ── CONFIG WIFI ───────────────────────────────────────────────────────────────
SSID     = "MOVISTAR_8A70"   # nombre del hotspot del PC
PASSWORD = "tnADEofvTsc8MNGj6PSK"      # contraseña del hotspot
HOST_IP  = "192.168.1.46"   # IP del PC con hotspot Windows (defecto)
PORT     = 5001              # puerto Flask local
INTERVAL = 30                # segundos entre peticiones
# ─────────────────────────────────────────────────────────────────────────────

# ── Pines display ─────────────────────────────────────────────────────────────
Pin(4, Pin.OUT, value=1)
spi = SoftSPI(baudrate=500_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
dc  = Pin(21, Pin.OUT, value=0)
rst = Pin(7,  Pin.OUT, value=1)

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
_cmd(0xC0, b'\x1b'); _cmd(0xC1, b'\x10')
_cmd(0xC5, b'\x2d\x33')
_cmd(0x36, b'\x48'); _cmd(0x3A, b'\x55')
_cmd(0xB1, b'\x00\x1d'); _cmd(0xB6, b'\x0A\x82')
_cmd(0xF2, b'\x00'); _cmd(0x26, b'\x01')
_cmd(0xE0, b'\x0F\x3a\x36\x0b\x0d\x06\x4c\x91\x31\x08\x10\x04\x11\x0c\x00')
_cmd(0xE1, b'\x00\x06\x0a\x05\x12\x09\x2c\x92\x3f\x08\x0e\x0b\x2e\x33\x0F')
_cmd(0x29); time.sleep_ms(100)
_cmd(0x21)

def _window(x0, y0, x1, y1):
    _cmd(0x2A, bytes([x0>>8, x0&0xFF, x1>>8, x1&0xFF]))
    _cmd(0x2B, bytes([y0>>8, y0&0xFF, y1>>8, y1&0xFF]))
    dc(0); spi.write(b'\x2C')

def rect(x, y, w, h, color):
    _window(x, y, x+w-1, y+h-1)
    hi, lo = color>>8, color&0xFF
    chunk = bytes([hi, lo]*64); dc(1)
    n = w*h
    while n >= 64: spi.write(chunk); n -= 64
    if n: spi.write(bytes([hi, lo]*n))

def hline(x, y, w, color): rect(x, y, w, 1, color)

def char_big(x, y, ch, fg, bg, scale):
    buf = bytearray(8)
    fb  = framebuf.FrameBuffer(buf, 8, 8, framebuf.MONO_VLSB)
    fb.fill(0); fb.text(ch, 0, 0, 1)
    cw = 8*scale; ch_h = 8*scale
    pixels = bytearray(cw*ch_h*2)
    fh, fl = fg>>8, fg&0xFF; bh, bl = bg>>8, bg&0xFF
    for row in range(8):
        for col in range(8):
            on = (buf[col] >> row) & 1
            hi = fh if on else bh; lo = fl if on else bl
            for sy in range(scale):
                for sx in range(scale):
                    idx = ((row*scale+sy)*cw + col*scale+sx)*2
                    pixels[idx]=hi; pixels[idx+1]=lo
    _window(x, y, x+cw-1, y+ch_h-1); dc(1); spi.write(pixels)
    return cw

def text(x, y, s, fg, bg, scale=1):
    for ch in s:
        x += char_big(x, y, ch, fg, bg, scale) + scale

BLACK=0x0000; WHITE=0xFFFF; YELLOW=0xFFE0; ORANGE=0xFD20
GREEN=0x07E0; RED=0xF800; DGRAY=0x4208; LGRAY=0x8410

Y_TITLE=6; Y_DATE=36; Y_SEP1=54; Y_ROW1=68; Y_ROW2=132; Y_ROW3=196
Y_SEP2=254; Y_STATUS=262; Y_WIFI=282
wifi_ip = ""  # IP asignada al conectar

def draw_panel():
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
    rect(0,Y_DATE,240,17,BLACK); text(4,Y_DATE,fecha+"  "+hora,LGRAY,BLACK,scale=1)

def draw_status(msg, color):
    rect(0,Y_STATUS,240,17,BLACK); text(4,Y_STATUS,msg,color,BLACK,scale=1)

def draw_wifi_bar():
    """Barra inferior con indicador visual de conexión WiFi."""
    rect(0, Y_WIFI, 240, 20, BLACK)
    if wifi_ip:
        rect(4, Y_WIFI+4, 8, 8, GREEN)          # punto verde = conectado
        text(16, Y_WIFI+2, "WiFi "+wifi_ip, GREEN, BLACK, scale=1)
    else:
        rect(4, Y_WIFI+4, 8, 8, RED)            # punto rojo = sin WiFi
        text(16, Y_WIFI+2, "Sin WiFi", RED, BLACK, scale=1)

def draw_connect_screen(msg):
    rect(0,0,240,320,BLACK)
    text(4,140,"Conectando WiFi...",LGRAY,BLACK,scale=1)
    text(4,158,msg[:26],YELLOW,BLACK,scale=1)

# ── HTTP GET mínimo sin urequests ──────────────────────────────────────────────
def http_get(host, port, path):
    """HTTP/1.0 GET básico, devuelve el body como string o None."""
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(8)
        s.connect(addr)
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        s.send(req.encode())
        resp = b""
        while True:
            chunk = s.recv(512)
            if not chunk: break
            resp += chunk
        s.close()
        # Separar header y body
        idx = resp.find(b"\r\n\r\n")
        if idx < 0: return None
        return resp[idx+4:].decode('utf-8', 'ignore')
    except Exception as e:
        print("HTTP error:", e)
        return None

# ── Conectar WiFi ──────────────────────────────────────────────────────────────
def conectar_wifi():
    global wifi_ip
    draw_connect_screen(SSID[:22])
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        for _ in range(20):
            if wlan.isconnected(): break
            time.sleep(0.5)
    if wlan.isconnected():
        wifi_ip = wlan.ifconfig()[0]
        rect(0,175,240,17,BLACK)
        text(4,175,"IP: "+wifi_ip,GREEN,BLACK,scale=1)
        time.sleep(1)
        return True
    else:
        wifi_ip = ""
        rect(0,175,240,17,BLACK)
        text(4,175,"Sin conexion",RED,BLACK,scale=1)
        return False

# ── Arranque ───────────────────────────────────────────────────────────────────
conectado = conectar_wifi()
draw_panel()
draw_num(Y_ROW1,YELLOW,-1); draw_num(Y_ROW2,ORANGE,-1); draw_num(Y_ROW3,GREEN,-1)
draw_datetime("--/--","--:--")
draw_status("Iniciando..." if conectado else "Sin WiFi",LGRAY)
draw_wifi_bar()

vp=ve=vt=-1
ultimo_ok = 0

while True:
    if not conectado:
        time.sleep(5)
        conectado = conectar_wifi()
        if conectado:
            draw_panel()
            draw_num(Y_ROW1,YELLOW,-1); draw_num(Y_ROW2,ORANGE,-1); draw_num(Y_ROW3,GREEN,-1)
        continue

    body = http_get(HOST_IP, PORT, "/api/display")
    if body:
        try:
            d = json.loads(body)
            np=int(d.get('p',-1)); ne=int(d.get('e',-1)); nt=int(d.get('t',-1))
            hora=str(d.get('hora','--:--')); fecha=str(d.get('fecha','--/--'))
            if np!=vp: vp=np; draw_num(Y_ROW1,YELLOW,vp)
            if ne!=ve: ve=ne; draw_num(Y_ROW2,ORANGE,ve)
            if nt!=vt: vt=nt; draw_num(Y_ROW3,GREEN,vt)
            draw_datetime(fecha,hora)
            draw_status("OK  "+hora,GREEN)
            draw_wifi_bar()
            ultimo_ok = time.ticks_ms()
        except Exception as ex:
            print("JSON err:", ex)
            draw_status("Error JSON",RED)
    else:
        draw_status("Sin respuesta",ORANGE)
        draw_wifi_bar()
        # Reconectar si llevan >60s sin respuesta
        if ultimo_ok and time.ticks_diff(time.ticks_ms(), ultimo_ok) > 60000:
            conectado = conectar_wifi()

    for _ in range(INTERVAL * 2):   # sleep en bloques de 0.5s para poder interrumpir
        time.sleep(0.5)
