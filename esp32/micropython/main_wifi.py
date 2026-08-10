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
#   - Si VARIOS operarios trabajan el mismo carro (cada uno desde su PC), la
#     pantalla recibe la lista de todos: muestra el NOMBRE del operario debajo
#     del carro y un contador "1/2" a la derecha. El pulsador de la extensora
#     (pad 1 = GND, pad 2 = GPIO17, ver BTN_OP_PIN) salta a los paquetes del
#     siguiente operario, en ciclo.
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
import machine
import binascii
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

# Carro asignado a ESTA pantalla. NORMALMENTE NO HACE FALTA TOCARLO: la
# pantalla se identifica sola en el servidor (por su MAC) y el carro se le
# asigna desde Admin -> Display Carro. Este valor solo sirve como asignacion
# fija de emergencia si no quieres usar el panel de Admin; la asignacion del
# Admin tiene prioridad sobre esta.
CARRO_ASIGNADO = ""

# Identificador unico de esta pantalla (MAC del chip). Los ultimos 4
# caracteres se muestran en la pantalla de reposo ("ID xxxx") para poder
# reconocerla en Admin -> Display Carro.
DEVICE_ID = binascii.hexlify(machine.unique_id()).decode()

USE_HW_SPI = True      # False = SoftSPI lento (solo si el HW SPI diera problemas)
SPI_BAUD   = 20_000_000

# Boton OPCIONAL (no hace falta para funcionar): entre BUTTON_PIN y GND
# (pull-up interno, pulsado = 0). Sin nada cableado el pin lee siempre 1.
# Pines OCUPADOS por el display: 4, 7, 12, 13, 14, 21. Evita tambien los de
# strapping del S3 (0, 3, 45, 46).
BUTTON_PIN = 5

# Pulsador de CAMBIO DE OPERARIO: en la extensora FFC va entre el pad 1
# (GND) y el pad 2, que corresponde al GPIO17 del ESP32-S3. Lee con pull-up
# interno (pulsado = 0). Cada pulsacion muestra los paquetes del siguiente
# operario que este trabajando este carro, en ciclo.
BTN_OP_PIN = 17
# Solo si el pulsador NO va a un GND real: pon aqui un GPIO libre y ese pin
# se pondra como salida a nivel bajo para hacer de GND. Con None no se toca.
BTN_OP_GND = None
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
Y_CARRO=4; Y_OPER=30; Y_ORDEN=50; Y_SEP1=68
PKG_Y0=72; PKG_ETIQ=82; PKG_TAG=170; PKG_ELEM=196; PKG_COD=218; PKG_Y1=250
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

# Carro que sirve esta pantalla: lo decide el servidor (Admin -> Display
# Carro) o, en su defecto, CARRO_ASIGNADO. Se actualiza con cada poll.
mi_carro = CARRO_ASIGNADO

def draw_idle(msg=None):
    """Pantalla de reposo: sin contadores, solo identidad y estado."""
    if msg is None:
        msg = "Esperando paquetes..." if mi_carro else "Esperando carro..."
    rect(0, 0, 240, 320, BLACK)
    text_center(40,  "COJOsw",    WHITE,  BLACK, scale=4)
    text_center(90,  "ENGASTADO", ORANGE, BLACK, scale=2)
    hline(20, 120, 200, DGRAY)
    if mi_carro:
        # Identificar la pantalla: este es MI carro
        text_center(140, "CARRO", LGRAY, BLACK, scale=2)
        s = max(3, min(8, 232 // (9*len(mi_carro))))
        text_center(170, mi_carro, YELLOW, BLACK, scale=s)
    text_center(250, msg, LGRAY, BLACK, scale=1)
    text(4, 274, "ID " + DEVICE_ID[-4:], DGRAY, BLACK, scale=1)
    draw_wifi_bar()

# ── Estado de trabajo ─────────────────────────────────────────────────────────
work_ops   = []    # operarios activos en el carro: [{'operario':.., 'data':..}, ..]
op_idx     = 0     # operario mostrado (el pulsador BTN_OP rota entre ellos)
work_pkgs  = []    # lista de paquetes del operario mostrado
work_idx   = 0     # paquete mostrado
work_fp    = ""    # huella del contenido (para ignorar re-pushes identicos)

def draw_work_header(d, operario='', oi=0, on=1):
    """Cabecera fija del carro + operario: se redibuja al cambiar carro/operario."""
    carro = str(d.get('carro', ''))[:8]
    orden = str(d.get('orden', '') or d.get('bono', ''))[:13]
    rect(0, 0, 240, PKG_Y0, BLACK)
    rect(0, Y_SEP2, 240, 320-Y_SEP2, BLACK)
    text(4, Y_CARRO, 'CARRO ' + carro, WHITE,  BLACK, scale=3)
    # Nombre del operario que esta engastando, debajo del carro
    op = str(operario or '')[:10]
    if op:
        text(4, Y_OPER, op, GREEN, BLACK, scale=2)
    if on > 1:
        # Contador de operarios "1/2" a la derecha: hay mas, rota con BTN_OP
        s = "%d/%d" % (oi + 1, on)
        text(240 - len(s)*18 - 4, Y_OPER, s, LGRAY, BLACK, scale=2)
    text(4, Y_ORDEN, orden, YELLOW, BLACK, scale=2)
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

def mostrar_operario():
    """Carga los paquetes del operario op_idx y redibuja cabecera + paquete."""
    global work_pkgs, work_idx
    o = work_ops[op_idx]
    d = o.get('data') or {}
    work_pkgs = d.get('paquetes', [])[:40]
    if work_idx >= len(work_pkgs):
        work_idx = 0
    draw_work_header(d, o.get('operario', ''), op_idx, len(work_ops))
    draw_package()

def next_operario():
    """Pulsador BTN_OP: salta a los paquetes del siguiente operario, en ciclo."""
    global op_idx, work_idx
    if len(work_ops) < 2: return
    op_idx = (op_idx + 1) % len(work_ops)
    work_idx = 0
    mostrar_operario()

def _fp_op(o):
    d = o.get('data') or {}
    pkgs = d.get('paquetes', [])
    return "%s|%s|%s|%s" % (o.get('operario', ''), d.get('carro'), d.get('orden'),
                            ",".join(str(p.get('etiqueta')) + str(p.get('elem')) + ('B' if p.get('bloqueado') else '') for p in pkgs))

def _fingerprint(ops):
    return "||".join(_fp_op(o) for o in ops)

def _parse_ops(d):
    """Lista de operarios activos de la respuesta del servidor.

    Formato nuevo: d['ops'] = [{'operario':.., 'data':..}, ..]. Si el servidor
    fuera antiguo y no mandara 'ops', se cae al campo unico d['data'].
    """
    ops = d.get('ops')
    if ops is None:
        wdata = d.get('data')
        if wdata and not wdata.get('clear'):
            ops = [{'operario': wdata.get('operario') or '', 'data': wdata}]
        else:
            ops = []
    return [o for o in ops if o.get('data') and not o['data'].get('clear')][:8]

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
def wifi_conectada():
    """True si la WiFi sigue realmente conectada. Nunca lanza excepcion."""
    try:
        return network.WLAN(network.STA_IF).isconnected()
    except Exception:
        return False

def conectar_wifi():
    """UN intento de conexion (bloquea ~12s max). Nunca lanza excepcion.

    Si falla, apaga la radio: el driver WiFi del ESP32 se puede quedar
    colgado tras un intento fallido (sobre todo en arranque frio) y solo
    se recupera reiniciando la interfaz.
    """
    global wifi_ip
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if not wlan.isconnected():
            try:
                wlan.disconnect()
            except Exception:
                pass
            wlan.connect(SSID, PASSWORD)
            for _ in range(24):
                if wlan.isconnected():
                    break
                time.sleep(0.5)
        if wlan.isconnected():
            wifi_ip = wlan.ifconfig()[0]
            return True
        wlan.active(False)
        time.sleep_ms(300)
    except Exception as e:
        print("WiFi err:", e)
        try:
            network.WLAN(network.STA_IF).active(False)
            time.sleep_ms(300)
        except Exception:
            pass
    wifi_ip = ""
    return False

def draw_estado(msg, color=LGRAY):
    """Repinta solo la linea de estado del reposo (sin redibujar la pantalla)."""
    rect(0, 250, 240, 12, BLACK)
    text_center(250, msg, color, BLACK, scale=1)
    draw_wifi_bar()

# ── Arranque ──────────────────────────────────────────────────────────────────
btn = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

# Pulsador de cambio de operario (BTN_OP_PIN -> GND, pull-up interno)
if BTN_OP_GND is not None:
    Pin(BTN_OP_GND, Pin.OUT, value=0)
btn_op = Pin(BTN_OP_PIN, Pin.IN, Pin.PULL_UP)

draw_idle("Conectando WiFi...")
import network, socket
conectado = conectar_wifi()
draw_idle()  # refresca con la barra WiFi actualizada

MAX_INTENTOS_WIFI = 10   # tras estos intentos seguidos sin WiFi, reset completo de la placa

ultimo_poll  = time.ticks_ms() - POLL_INTERVAL * 1000  # forzar poll inmediato
en_work_mode = False
btn_prev     = 1
btn_last_ms  = 0
btn_op_prev  = 1
btn_op_last  = 0
ultimo_avance = time.ticks_ms()   # timer de rotacion automatica de paquetes
intentos_wifi = 0

# El bucle NUNCA debe morir: cualquier excepcion se registra y se sigue.
while True:
  try:
    now = time.ticks_ms()

    # ── Boton opcional: flanco de bajada con debounce de 200ms ────────
    b = btn.value()
    if en_work_mode and b == 0 and btn_prev == 1 and time.ticks_diff(now, btn_last_ms) > 200:
        btn_last_ms = now
        ultimo_avance = now
        next_package()
    btn_prev = b

    # ── Pulsador de operario (pines 1-2): siguiente operario en ciclo ──
    b2 = btn_op.value()
    if b2 != btn_op_prev:
        # Test de cableado: cuadrado amarillo junto a la barra WiFi mientras
        # el pulsador este apretado. Si al pulsar no aparece, la senal no
        # llega al GPIO configurado en BTN_OP_PIN.
        rect(226, Y_WIFI + 4, 10, 10, YELLOW if b2 == 0 else BLACK)
        print("BTN_OP:", "pulsado" if b2 == 0 else "soltado")
    if en_work_mode and b2 == 0 and btn_op_prev == 1 and time.ticks_diff(now, btn_op_last) > 250:
        btn_op_last = now
        ultimo_avance = now
        next_operario()
    btn_op_prev = b2

    # ── Rotacion automatica de paquetes (sin boton) ───────────────────
    if en_work_mode and len(work_pkgs) > 1 and time.ticks_diff(now, ultimo_avance) >= AUTO_ADVANCE_S * 1000:
        ultimo_avance = now
        next_package()

    # ── Deteccion de perdida de WiFi ──────────────────────────────────
    if conectado and not wifi_conectada():
        conectado = False
        wifi_ip = ""
        intentos_wifi = 0
        print("WiFi perdida")
        if en_work_mode:
            draw_wifi_bar()
        else:
            draw_estado("WiFi perdida, reconectando...", ORANGE)

    # ── Reconexion WiFi: reintenta PARA SIEMPRE cada ~5s ──────────────
    if not conectado and time.ticks_diff(now, ultimo_poll) >= 5000:
        ultimo_poll = now
        intentos_wifi += 1
        if not en_work_mode:
            draw_estado("Buscando WiFi... intento %d" % intentos_wifi, ORANGE)
        conectado = conectar_wifi()
        if conectado:
            intentos_wifi = 0
            # Sincronizar YA con la app (poll inmediato en la proxima vuelta)
            ultimo_poll = time.ticks_ms() - POLL_INTERVAL * 1000
            if en_work_mode:
                draw_wifi_bar()
            else:
                draw_idle()
        elif intentos_wifi >= MAX_INTENTOS_WIFI:
            # La radio puede quedarse colgada; un reset limpio la recupera
            if not en_work_mode:
                draw_estado("Sin WiFi: reiniciando pantalla...", RED)
            time.sleep(1)
            machine.reset()

    # ── Poll de trabajo (cada 3s) ─────────────────────────────────────
    elif conectado and time.ticks_diff(now, ultimo_poll) >= POLL_INTERVAL * 1000:
        ultimo_poll = now
        ruta = "/api/esp32/current?id=" + DEVICE_ID
        if CARRO_ASIGNADO:
            ruta += "&carro=" + CARRO_ASIGNADO
        body = http_get(HOST_IP, PORT, ruta)
        if body:
            try:
                d = json.loads(body)
                # Carro que nos asigna el servidor (Admin -> Display Carro)
                ca = d.get('carro_asignado') or CARRO_ASIGNADO
                if ca != mi_carro:
                    mi_carro = ca
                    if not en_work_mode:
                        draw_idle()
                ops = _parse_ops(d)
                fp = _fingerprint(ops)
                if not ops:
                    if en_work_mode:
                        # Datos expirados o "clear" de todos → volver a reposo
                        en_work_mode = False
                        work_fp = ""; work_ops = []; work_pkgs = []; op_idx = 0
                        draw_idle()
                elif fp != work_fp:
                    # Contenido nuevo. Si el operario mostrado sigue activo se
                    # mantiene seleccionado (y su paquete, si su lista no cambio).
                    prev = work_ops[op_idx] if (en_work_mode and op_idx < len(work_ops)) else None
                    work_fp  = fp
                    work_ops = ops
                    op_idx   = 0
                    if prev:
                        for i, o in enumerate(work_ops):
                            if o.get('operario') == prev.get('operario'):
                                op_idx = i
                                break
                        if _fp_op(work_ops[op_idx]) != _fp_op(prev):
                            work_idx = 0
                            ultimo_avance = now
                    else:
                        work_idx = 0
                        ultimo_avance = now
                    en_work_mode = True
                    mostrar_operario()
                    print("work OK ops", len(work_ops), "op", work_ops[op_idx].get('operario'))
            except Exception as ex:
                print("JSON err:", ex)

    time.sleep_ms(20)
  except Exception as ex:
    print("loop err:", ex)
    time.sleep_ms(500)
