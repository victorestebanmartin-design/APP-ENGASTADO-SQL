# main_wifi.py — Panel COJOsw vía WiFi (sin cable USB)
# Subir con: mpremote connect COM5 cp esp32\micropython\main_wifi.py :main.py + reset
#
# ANTES DE SUBIR: ajusta SSID, PASSWORD y HOST_IP abajo.
# Activa el hotspot móvil del PC: Configuración → Sistema → Hotspot móvil
# El PC tendrá la IP 192.168.137.1 por defecto con hotspot Windows.

import time
import json
from machine import SoftSPI, Pin
import framebuf
# network y socket se importan tarde, tras el primer draw, para no ralentizar SoftSPI

# ── CONFIG WIFI ───────────────────────────────────────────────────────────────
SSID     = "MOVISTAR_8A70"
PASSWORD = "tnADEofvTsc8MNGj6PSK"
HOST_IP  = "viktor85.pythonanywhere.com"
PORT     = 80
INTERVAL = 30          # segundos entre polls de stats generales
PUSH_INTERVAL = 3      # segundos entre polls de pantalla de trabajo
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

# Init mínima probada funcional en arranque frío (la init 4D Systems falla en cold boot)
_cmd(0x11); time.sleep_ms(120)
_cmd(0x36, b'\x48')   # MADCTL MX=1 BGR=1
_cmd(0x3A, b'\x55')   # 16-bit color
_cmd(0x29); time.sleep_ms(50)
_cmd(0x21)            # INVON necesario para panel IPS

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

def draw_work_screen(d):
    """Pantalla de trabajo — minimos caracteres para ser rapido con WiFi activo."""
    carro = str(d.get('carro', ''))
    bono  = str(d.get('bono', ''))[:14]
    pkgs  = d.get('paquetes', [])[:5]

    # Carro numero (el dato mas importante) — escala 2, pocas letras
    text(4, Y_TITLE, ('C-' + carro).ljust(8), WHITE, BLACK, scale=2)
    text(4, Y_DATE,  bono.ljust(18),           YELLOW, BLACK, scale=1)
    hline(0, Y_SEP1, 240, DGRAY)

    # 5 paquetes en las mismas filas del panel (sobrescriben PENDIENTES etc.)
    y = Y_ROW1 + 2
    for i, p in enumerate(pkgs):
        etiq  = str(p.get('etiqueta') or '')[:5]
        cod   = str(p.get('cod',  '') or '')[:14]
        color = LGRAY if p.get('bloqueado') else WHITE
        text(4, y, (etiq + ' ' + cod).ljust(22), color, BLACK, scale=1)
        y += 14

    # Limpiar filas sobrantes
    while y < Y_ROW1 + 2 + 5*14:
        text(4, y, ' ' * 22, BLACK, BLACK, scale=1)
        y += 14

    draw_wifi_bar()
    print("work OK carro", carro)

# ── HTTP GET mínimo sin urequests ──────────────────────────────────────────────
def http_get(host, port, path):
    """HTTP/1.0 GET básico, devuelve el body como string o None."""
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(8)
        s.connect(addr)
        # Incluir IP propia para que Flask la registre
        req = f"GET {path}?esp32_ip={wifi_ip} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
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

# ── Servidor HTTP para recibir push del modal (browser → ESP32) ───────────────
def _start_push_server(port=80):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', port))
    s.listen(2)
    s.setblocking(False)
    return s

def _check_push(srv):
    """Non-blocking: acepta una conexion HTTP y devuelve el JSON body o None."""
    try:
        conn, _ = srv.accept()
        conn.settimeout(2)
        req = b''
        try:
            while True:
                d = conn.recv(512)
                if not d: break
                req += d
                if len(req) > 4096: break
        except: pass
        conn.send(b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: POST, OPTIONS\r\n\r\n{"ok":true}')
        conn.close()
        idx = req.find(b'\r\n\r\n')
        if idx >= 0:
            body = req[idx+4:]
            if body:
                return json.loads(body)
    except: pass
    return None

# ── Conectar WiFi ──────────────────────────────────────────────────────────────
def conectar_wifi():
    global wifi_ip
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        for _ in range(20):
            if wlan.isconnected(): break
            time.sleep(0.5)
    if wlan.isconnected():
        wifi_ip = wlan.ifconfig()[0]
        return True
    else:
        wifi_ip = ""
        return False

# ── Arranque: panel primero, WiFi en segundo plano ──────────────────────
draw_panel()
draw_num(Y_ROW1,YELLOW,-1); draw_num(Y_ROW2,ORANGE,-1); draw_num(Y_ROW3,GREEN,-1)
draw_datetime("--/--","--:--")
draw_status("Conectando WiFi...",LGRAY)
draw_wifi_bar()
# Importar network DESPUÉS del primer draw para no ralentizar SoftSPI
import network, socket
conectado = conectar_wifi()   # WiFi DESPUES de dibujar el panel
draw_wifi_bar()               # actualizar indicador con IP o error
draw_status("OK" if conectado else "Sin WiFi", GREEN if conectado else RED)

# Ya no necesitamos servidor HTTP local (usamos PA como relay)
vp=ve=vt=-1
ultimo_ok = 0
ultimo_poll  = time.ticks_ms() - INTERVAL * 1000  # forzar poll inmediato
ultimo_push  = time.ticks_ms() - PUSH_INTERVAL * 1000
ultimo_ts    = ""   # timestamp del último push procesado

while True:
    # ── Poll rápido: pantalla de trabajo vía PA relay (cada 3s) ──────
    if time.ticks_diff(time.ticks_ms(), ultimo_push) >= PUSH_INTERVAL * 1000:
        ultimo_push = time.ticks_ms()
        body = http_get(HOST_IP, PORT, "/api/esp32/current")
        if body:
            try:
                d = json.loads(body)
                if d.get('data') and d.get('ts') != ultimo_ts:
                    ultimo_ts = d['ts']
                    draw_work_screen(d['data'])
                    ultimo_ok = time.ticks_ms()
            except: pass

    # ── Poll periódico: stats generales (cada 30s) ────────────────────
    if not conectado:
        time.sleep(5)
        conectado = conectar_wifi()
        if conectado:
            draw_panel()
            draw_num(Y_ROW1,YELLOW,-1); draw_num(Y_ROW2,ORANGE,-1); draw_num(Y_ROW3,GREEN,-1)
        continue

    if time.ticks_diff(time.ticks_ms(), ultimo_poll) >= INTERVAL * 1000:
        ultimo_poll = time.ticks_ms()
        body = http_get(HOST_IP, PORT, "/api/display")
        if body:
            try:
                d = json.loads(body)
                np=int(d.get('p',-1)); ne=int(d.get('e',-1)); nt=int(d.get('t',-1))
                hora=str(d.get('hora','--:--')); fecha=str(d.get('fecha','--/--'))
                # Solo actualizar panel de stats si no hay pantalla de trabajo activa
                if not ultimo_ts and (np!=vp or ne!=ve or nt!=vt):
                    vp=np; ve=ne; vt=nt
                    draw_panel()
                    draw_num(Y_ROW1,YELLOW,vp); draw_num(Y_ROW2,ORANGE,ve); draw_num(Y_ROW3,GREEN,vt)
                    draw_datetime(fecha,hora)
                draw_status("OK  "+hora,GREEN)
                draw_wifi_bar()
                ultimo_ok = time.ticks_ms()
            except Exception as ex:
                print("JSON err:", ex)
        else:
            draw_status("Sin respuesta",ORANGE)
            draw_wifi_bar()
            if ultimo_ok and time.ticks_diff(time.ticks_ms(), ultimo_ok) > 60000:
                conectado = conectar_wifi()

    time.sleep(0.1)
