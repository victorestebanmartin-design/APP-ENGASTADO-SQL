# main_wifi.py — Pantalla de carro COJOsw vía WiFi (gen4-ESP32-24, ILI9341 240x320)
# Subir con: mpremote connect COM5 cp esp32\micropython\main_wifi.py :main.py + reset
#
# ANTES DE SUBIR: ajusta SSID, PASSWORD y HOST_IP abajo.
#
# Modo de uso:
#   - En reposo muestra "Esperando carro..." con el estado WiFi.
#   - Al abrir el modal de paquetes en el navegador, el ESP32 recibe el carro
#     asignado (orden + codigo) y su lista de paquetes.
#   - Muestra UN paquete a la vez, con la etiqueta bien grande, y va rotando
#     automaticamente cada AUTO_ADVANCE_S segundos. NO hace falta cablear nada.
#   - OPCIONAL: si algun dia se conecta un boton (BUTTON_PIN -> GND), cada
#     pulsacion avanza al siguiente paquete al instante. Sin boton conectado
#     el pin queda en pull-up interno y no afecta en nada.
#
# Rendimiento: SPI por hardware (20 MHz) en vez de SoftSPI (~500 kHz bit-bang).
# Un clear de pantalla completa pasa de varios segundos a ~60 ms, y el texto se
# renderiza por filas en vez de pixel a pixel. Si el SPI hardware fallara en tu
# placa, pon USE_HW_SPI = False para volver al modo lento pero seguro.

import time
import json
from machine import SPI, SoftSPI, Pin
import framebuf
# network y socket se importan tarde, tras el primer draw

# ── CONFIG ────────────────────────────────────────────────────────────────────
SSID     = "MOVISTAR_8A70"
PASSWORD = "tnADEofvTsc8MNGj6PSK"
HOST_IP  = "viktor85.pythonanywhere.com"
PORT     = 80
POLL_INTERVAL = 3      # segundos entre polls de /api/esp32/current
AUTO_ADVANCE_S = 4     # segundos que se muestra cada paquete antes de rotar al siguiente

# Carro asignado a ESTA pantalla. Si lo dejas vacio ("") la pantalla es
# "generica": muestra cualquier carro que se abra en el navegador (como antes).
# Si pones el nombre del carro (ej. "1", "A2"...) SOLO recibira los paquetes
# de ese carro — asi cada carro puede llevar su propia pantalla.
CARRO_ASIGNADO = ""

USE_HW_SPI = True      # False = SoftSPI lento (solo si el HW SPI diera problemas)
SPI_BAUD   = 20_000_000

# Boton OPCIONAL (no hace falta para funcionar): entre BUTTON_PIN y GND
# (pull-up interno, pulsado = 0). Sin nada cableado el pin lee siempre 1.
# Pines OCUPADOS por el display: 4, 7, 12, 13, 14, 21. Evita tambien los de
# strapping del S3 (0, 3, 45, 46).
BUTTON_PIN = 5
# ─────────────────────────────────────────────────────────────────────────────

# ── Pines display ─────────────────────────────────────────────────────────────
Pin(4, Pin.OUT, value=1)   # backlight ON

if USE_HW_SPI:
    try:
        # ESP32-S3: cualquier pin es ruteable al SPI hardware via GPIO matrix
        spi = SPI(1, baudrate=SPI_BAUD, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
    except Exception as e:
        print("HW SPI fallo, uso SoftSPI:", e)
        spi = SoftSPI(baudrate=500_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
else:
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
    chunk = bytes([hi, lo]*256); dc(1)
    n = w*h
    while n >= 256: spi.write(chunk); n -= 256
    if n: spi.write(bytes([hi, lo]*n))

def hline(x, y, w, color): rect(x, y, w, 1, color)

# ── Texto escalado, renderizado por filas (rapido) ────────────────────────────
_glyph = bytearray(8)
_gfb   = framebuf.FrameBuffer(_glyph, 8, 8, framebuf.MONO_VLSB)

def char_big(x, y, ch, fg, bg, scale):
    _gfb.fill(0); _gfb.text(ch, 0, 0, 1)
    cw = 8*scale
    _window(x, y, x+cw-1, y+cw-1)
    dc(1)
    fpx = bytes([fg>>8, fg&0xFF])*scale
    bpx = bytes([bg>>8, bg&0xFF])*scale
    row = bytearray(cw*2)
    s2 = scale*2
    for r in range(8):
        mask = 1 << r
        pos = 0
        for c in range(8):
            row[pos:pos+s2] = fpx if _glyph[c] & mask else bpx
            pos += s2
        for _ in range(scale):
            spi.write(row)
    return cw

def text(x, y, s, fg, bg, scale=1):
    for ch in s:
        x += char_big(x, y, ch, fg, bg, scale) + scale

def text_center(y, s, fg, bg, scale=1):
    w = len(s)*9*scale - scale
    text(max(0, (240 - w)//2), y, s, fg, bg, scale)

BLACK=0x0000; WHITE=0xFFFF; YELLOW=0xFFE0; ORANGE=0xFD20
GREEN=0x07E0; RED=0xF800; DGRAY=0x4208; LGRAY=0x8410

# ── Layout ────────────────────────────────────────────────────────────────────
Y_CARRO=6; Y_ORDEN=38; Y_SEP1=60
PKG_Y0=66; PKG_ETIQ=78; PKG_TAG=170; PKG_ELEM=196; PKG_COD=218; PKG_Y1=250
Y_SEP2=252; Y_FOOT=260; Y_WIFI=296

wifi_ip = ""

def draw_wifi_bar():
    rect(0, Y_WIFI, 240, 20, BLACK)
    if wifi_ip:
        rect(4, Y_WIFI+4, 8, 8, GREEN)
        text(16, Y_WIFI+2, "WiFi "+wifi_ip, GREEN, BLACK, scale=1)
    else:
        rect(4, Y_WIFI+4, 8, 8, RED)
        text(16, Y_WIFI+2, "Sin WiFi", RED, BLACK, scale=1)

def draw_idle(msg=None):
    """Pantalla de reposo: sin contadores, solo identidad y estado."""
    if msg is None:
        msg = "Esperando paquetes..." if CARRO_ASIGNADO else "Esperando carro..."
    rect(0, 0, 240, 320, BLACK)
    text_center(40,  "COJOsw",    WHITE,  BLACK, scale=4)
    text_center(90,  "ENGASTADO", ORANGE, BLACK, scale=2)
    hline(20, 120, 200, DGRAY)
    if CARRO_ASIGNADO:
        # Identificar la pantalla: este es MI carro
        text_center(140, "CARRO", LGRAY, BLACK, scale=2)
        s = max(3, min(8, 232 // (9*len(CARRO_ASIGNADO))))
        text_center(170, CARRO_ASIGNADO, YELLOW, BLACK, scale=s)
    text_center(250, msg, LGRAY, BLACK, scale=1)
    draw_wifi_bar()

# ── Estado de trabajo ─────────────────────────────────────────────────────────
work_pkgs  = []    # lista de paquetes del carro actual
work_idx   = 0     # paquete mostrado
work_fp    = ""    # huella del contenido (para ignorar re-pushes identicos)

def draw_work_header(d):
    """Cabecera fija del carro: se dibuja una sola vez por carro nuevo."""
    carro = str(d.get('carro', ''))[:8]
    orden = str(d.get('orden', '') or d.get('bono', ''))[:13]
    rect(0, 0, 240, PKG_Y0, BLACK)
    rect(0, Y_SEP2, 240, 320-Y_SEP2, BLACK)
    text(4, Y_CARRO, 'CARRO ' + carro, WHITE,  BLACK, scale=3)
    text(4, Y_ORDEN, orden,            YELLOW, BLACK, scale=2)
    hline(0, Y_SEP1, 240, DGRAY)
    hline(0, Y_SEP2, 240, DGRAY)
    draw_wifi_bar()

def draw_progress():
    rect(0, Y_FOOT, 240, 18, BLACK)
    text(4, Y_FOOT, "%d/%d" % (work_idx+1, len(work_pkgs)), LGRAY, BLACK, scale=2)

def draw_package():
    """Dibuja SOLO la zona central con el paquete actual (redibujado parcial)."""
    rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
    if not work_pkgs:
        text_center(140, "Sin paquetes", LGRAY, BLACK, scale=2)
        rect(0, Y_FOOT, 240, 18, BLACK)
        return
    p = work_pkgs[work_idx]
    etiq = str(p.get('etiqueta') if p.get('etiqueta') not in (None, '') else '-')[:4]
    elem = str(p.get('elem') or '')[:13]
    cod  = str(p.get('cod')  or '')[:13]
    bloq = bool(p.get('bloqueado'))

    # Etiqueta gigante, auto-escalada al ancho (1-2 chars → x10, 3 → x8, 4 → x6)
    s = max(2, min(10, 232 // (9*len(etiq))))
    y = PKG_ETIQ + (80 - 8*s)//2
    color = LGRAY if bloq else ORANGE
    text_center(y, etiq, color, BLACK, scale=s)

    if bloq:
        text_center(PKG_TAG, "BLOQUEADO", RED, BLACK, scale=2)
    text_center(PKG_ELEM, elem, WHITE, BLACK, scale=2)
    if cod and cod != elem:
        text_center(PKG_COD, cod, LGRAY, BLACK, scale=2)
    draw_progress()

def next_package():
    global work_idx
    if not work_pkgs: return
    work_idx = (work_idx + 1) % len(work_pkgs)
    draw_package()

def _fingerprint(d):
    pkgs = d.get('paquetes', [])
    return "%s|%s|%s" % (d.get('carro'), d.get('orden'),
                         ",".join(str(p.get('etiqueta')) + str(p.get('elem')) for p in pkgs))

# ── HTTP GET mínimo sin urequests ──────────────────────────────────────────────
def http_get(host, port, path):
    """HTTP/1.0 GET básico, devuelve el body como string o None."""
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(8)
        s.connect(addr)
        sep = '&' if '?' in path else '?'
        req = f"GET {path}{sep}esp32_ip={wifi_ip} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        s.send(req.encode())
        resp = b""
        while True:
            chunk = s.recv(512)
            if not chunk: break
            resp += chunk
        s.close()
        idx = resp.find(b"\r\n\r\n")
        if idx < 0: return None
        return resp[idx+4:].decode('utf-8', 'ignore')
    except Exception as e:
        print("HTTP error:", e)
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

# ── Arranque ──────────────────────────────────────────────────────────────────
btn = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

draw_idle("Conectando WiFi...")
import network, socket
conectado = conectar_wifi()
draw_idle()  # refresca con la barra WiFi actualizada

ultimo_poll  = time.ticks_ms() - POLL_INTERVAL * 1000  # forzar poll inmediato
ultimo_ts    = ""     # timestamp del último push procesado
en_work_mode = False
btn_prev     = 1
btn_last_ms  = 0
ultimo_avance = time.ticks_ms()   # timer de rotacion automatica de paquetes

while True:
    now = time.ticks_ms()

    # ── Boton opcional: flanco de bajada con debounce de 200ms ────────
    b = btn.value()
    if en_work_mode and b == 0 and btn_prev == 1 and time.ticks_diff(now, btn_last_ms) > 200:
        btn_last_ms = now
        ultimo_avance = now
        next_package()
    btn_prev = b

    # ── Rotacion automatica de paquetes (sin boton) ───────────────────
    if en_work_mode and len(work_pkgs) > 1 and time.ticks_diff(now, ultimo_avance) >= AUTO_ADVANCE_S * 1000:
        ultimo_avance = now
        next_package()

    # ── Reconexion WiFi ───────────────────────────────────────────────
    if not conectado and time.ticks_diff(now, ultimo_poll) >= 5000:
        ultimo_poll = now
        conectado = conectar_wifi()
        if not en_work_mode:
            draw_idle()

    # ── Poll de trabajo (cada 3s) ─────────────────────────────────────
    elif conectado and time.ticks_diff(now, ultimo_poll) >= POLL_INTERVAL * 1000:
        ultimo_poll = now
        ruta = "/api/esp32/current"
        if CARRO_ASIGNADO:
            ruta += "?carro=" + CARRO_ASIGNADO
        body = http_get(HOST_IP, PORT, ruta)
        if body:
            try:
                d = json.loads(body)
                wdata = d.get('data')
                if wdata and not wdata.get('clear') and d.get('ts') != ultimo_ts:
                    ultimo_ts = d['ts']
                    fp = _fingerprint(wdata)
                    if fp != work_fp:
                        # Carro/lista nuevos → cabecera + primer paquete
                        work_fp   = fp
                        work_pkgs = wdata.get('paquetes', [])[:40]
                        work_idx  = 0
                        ultimo_avance = now
                        en_work_mode = True
                        draw_work_header(wdata)
                        draw_package()
                        print("work OK carro", wdata.get('carro'), "pkgs", len(work_pkgs))
                elif (not wdata or wdata.get('clear')) and en_work_mode:
                    # Datos expirados o "clear" → volver a reposo
                    en_work_mode = False
                    ultimo_ts = ""
                    work_fp = ""
                    work_pkgs = []
                    draw_idle()
            except Exception as ex:
                print("JSON err:", ex)

    time.sleep_ms(20)
