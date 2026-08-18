# main_wifi.py — Pantalla de carro COJOsw vía WiFi (gen4-ESP32-24, ILI9341 240x320)
# Subir con: mpremote connect COM5 cp esp32\micropython\main_wifi.py :main.py + reset
#
# ANTES DE SUBIR: ajusta SSID, PASSWORD y HOST_IP abajo con los valores
# REALES en tu copia local, pero NO subas ese cambio a git con las
# credenciales reales dentro (este fichero se versiona con valores de
# ejemplo a proposito; ver el mismo aviso en esp32/wifi_config.py).
#
# Modo de uso:
#   - En reposo muestra "Esperando carro..." con el estado WiFi.
#   - Al abrir el modal de paquetes en el navegador, el ESP32 recibe el carro
#     asignado (orden + codigo) y su lista de paquetes.
#   - Muestra UN paquete a la vez, con la etiqueta bien grande, y va rotando
#     automaticamente cada AUTO_ADVANCE_S segundos. NO hace falta cablear nada.
#   8 PULSADORES: 1-7 = PUESTOS, 8 = OK
#   Cada puesto tiene asignado un boton en Admin -> Puestos. El operario que
#   llega al carro pulsa el boton de SU puesto y la pantalla le muestra lo suyo;
#   como nunca hay dos operarios en el mismo puesto, el boton identifica sin
#   ambiguedad quien esta delante. El boton 8 (OK) confirma.
#
#   CICLO COMPLETO (trazabilidad)
#     1. En el PC se elige terminal y carro. El modal muestra el grupo de
#        paquetes con el boton "Tengo estos N, empezar" BLOQUEADO.
#     2. La pantalla del carro lista los puestos que tienen algo pendiente:
#        "[3] AMP-02  RECOGER 5". Avisa con un sonido cada pocos segundos.
#     3. El operario pulsa el boton de su puesto -> la pantalla le muestra sus
#        paquetes. Los coge y pulsa OK -> se manda la confirmacion al servidor.
#     4. El PC desbloquea el boton y el operario trabaja el grupo.
#     5. Al terminar el grupo (o el carro), el PC pide DEVOLVER: la pantalla
#        vuelve a listar ese puesto, ahora en modo "DEVOLVER".
#     6. El operario pulsa su boton, deja los paquetes y pulsa OK. La pantalla
#        muestra ya el grupo siguiente (o "CARRO FINALIZADO") y se vuelve al
#        paso 3.
#   Si la pantalla del carro no responde, el PC ofrece confirmar manualmente
#   (queda registrado como manual): nunca se bloquea el trabajo del todo.
#
#   - Los paquetes bloqueados salen en gris con "BLOQUEADO" y debajo el
#     puesto/maquina que los esta trabajando.
#   - ZUMBADOR opcional en el pad 3 de la extensora (GPIO18, ver BUZZER_PIN):
#     cada evento tiene su patron de ritmo/textura (ver seccion Zumbador).
#     Sin zumbador soldado no afecta en nada.
#   - Los paquetes del puesto mostrado rotan solos cada AUTO_ADVANCE_S; tras
#     VOLVER_LISTA_S sin tocar nada, la pantalla vuelve sola a la lista.
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
# Version del firmware de aplicacion. SUBELA en cada release: el servidor la lee
# para saber si una pantalla esta al dia y el OTA por WiFi la usa como identidad.
FW_VERSION = "2026-08-18b"

SSID     = "YOUR_SSID"
PASSWORD = "YOUR_PASSWORD"
# IP fija de ESTA pantalla. La red de planta (192.168.50.0/24) no tiene DHCP,
# asi que sin esto la pantalla se queda esperando una direccion que nadie
# reparte. La rellena el servidor al flashear por USB (Admin -> Display Carro
# -> "Subir firmware por USB", campo "IP estatica") y se conserva en los OTA
# por WiFi (ver _reinyectar_wifi). Vacia = DHCP.
# Mascara y puerta de enlace son fijas para toda la instalacion (GATEWAY = el
# TL-WR802N, que hace tambien de DNS).
STATIC_IP   = ""
SUBNET_MASK = "255.255.255.0"
GATEWAY     = "192.168.50.5"
DNS         = "192.168.50.5"
# Servidor LOCAL (planta, sin internet): IP fija del PC servidor + puerto
# de run_sql.py (5001). Alternativa remota: "viktor85.pythonanywhere.com"
# con PORT = 443 (requiere que la placa tenga salida a internet).
#
# El servidor INYECTA aqui el host configurado en Admin (tanto al flashear
# por USB como al servir el OTA), asi que este valor es solo el de por
# defecto para un flasheo a mano con mpremote.
HOST_IP  = "192.168.50.1"
PORT     = 5001
POLL_INTERVAL = 1      # segundos entre polls de /api/esp32/current. Es el techo
                       # de lo que tarda en aparecer un paquete: el servidor
                       # responde en <1 ms y aguanta 600+ req/s, asi que bajarlo
                       # de 3s a 1s no le supone nada y se nota de inmediato.
AUTO_ADVANCE_S = 4     # segundos que se muestra cada paquete antes de rotar al siguiente
LONG_PRESS_MS = 1000   # umbral de pulsacion larga (los dos pulsadores)
OTA_HOLD_MS = 5000     # mantener OK (boton 8) 5s EN REPOSO = actualizar por WiFi
AVISO_PENDIENTE_S = 25 # cada cuanto recuerda con un pitido que hay un grupo
                       # esperando a que alguien vaya al carro a confirmarlo
AVISO_MAX = 6          # y cuantas veces como mucho: pasados estos avisos se
                       # calla (el aviso sigue en pantalla). Sin tope, un
                       # puesto colgado dejaria el zumbador pitando sin fin.
VOLVER_LISTA_S = 30    # sin tocar nada, el detalle de un puesto vuelve solo a
                       # la lista (deja la pantalla libre para el siguiente)

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

# ── Los 8 pulsadores ─────────────────────────────────────────────────────────
# Todos van entre su pad de la extensora y GND, con pull-up interno
# (reposo = 1, pulsado = 0). Pines OCUPADOS por el display: 4, 7, 12, 13, 14,
# 21; evita tambien los de strapping del S3 (0, 3, 45, 46).
#
# Botones 1-7: identifican un PUESTO. En Admin -> Puestos se asigna a cada
# puesto su numero de boton; el operario pulsa el suyo al llegar al carro y la
# pantalla le muestra sus paquetes.
#   boton 1 -> pad 2  (GPIO17)      boton 5 -> pad 7  (GPIO47)
#   boton 2 -> pad 4  (GPIO16)      boton 6 -> pad 8  (GPIO38)
#   boton 3 -> pad 5  (GPIO15)      boton 7 -> pad 9  (GPIO39)
#   boton 4 -> pad 6  (GPIO48)
BTN_PUESTO_PINS = [17, 16, 15, 48, 47, 38, 39]

# Boton 8 (pad 10, GPIO40): OK. Confirma lo que la pantalla este pidiendo
# (que has recogido los paquetes, o que los has devuelto).
BTN_OK_PIN = 40

# ── Lector NFC (PN532 "NFC MODULE V3" en modo I2C) ───────────────────────────
# La tarjeta identifica al OPERARIO (no al puesto), SOLO para confirmar en modo
# trabajo: pasar la tarjeta = pulsar el boton de su puesto (muestra sus
# paquetes); el OK (boton 8) confirma. Igual que con el boton, funciona con o
# sin tarjeta asignada -- el NFC es solo una forma alternativa de identificarse
# ante el carro, nunca hace falta para entrar al modulo (eso es el lector
# dedicado de la entrada del puesto, o la seleccion manual en el PC).
# Cada operario tiene su tarjeta asignada en Admin -> Operarios. Sin lector
# conectado no pasa nada: los pulsadores siguen funcionando igual.
#   SDA -> pad 11 (GPIO6)    VCC -> pad 20 (3.3V)
#   SCL -> pad 12 (GPIO5)    GND -> pad 21, 25 o 30
NFC_SDA_PIN = 6        # None en cualquiera de los dos = NFC desactivado
NFC_SCL_PIN = 5
NFC_POLL_MS = 300      # cada cuanto se pregunta si hay una tarjeta delante
NFC_REPETIR_MS = 3000  # ignorar la misma tarjeta si sigue apoyada en el lector
NFC_REINTENTO_S = 10   # si el lector no responde, cada cuanto se reintenta
NFC_FALLOS_MAX = 5     # lecturas fallidas seguidas antes de darlo por colgado
                       # y recuperar el bus I2C. El lector NUNCA se abandona:
                       # si lo enchufas con la pantalla en marcha, entra solo.

# Zumbador: patilla + al pad 3 de la extensora (GPIO18), patilla - a GND.
# None = sin zumbador (todo funciona igual, en silencio).
BUZZER_PIN = 18
# False = zumbador ACTIVO de 3.3V (suena solo al dar tension, lo normal).
# True  = piezo PASIVO: el tono se genera por PWM (pitidos con distinta nota).
BUZZER_PASIVO = False
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
def vline(x, y, h, color): rect(x, y, 1, h, color)

def hrect(x, y, w, h, color):
    """Rectangulo hueco (solo el borde)."""
    hline(x, y, w, color); hline(x, y+h-1, w, color)
    vline(x, y, h, color); vline(x+w-1, y, h, color)

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

# ── Zumbador ──────────────────────────────────────────────────────────────────
_bz = None
if BUZZER_PIN is not None:
    try:
        if BUZZER_PASIVO:
            from machine import PWM
            _bz = PWM(Pin(BUZZER_PIN), freq=2400, duty_u16=0)
        else:
            _bz = Pin(BUZZER_PIN, Pin.OUT, value=0)
    except Exception as e:
        print("Buzzer no disponible:", e)

# El zumbador ACTIVO suena siempre a su frecuencia de fabrica: pedirle notas
# distintas no sirve de nada (todas suenan igual). Por eso los avisos se
# distinguen por RITMO y por TEXTURA:
#   - tono:  sonido liso y continuo
#   - trino: cortes rapidos on/off, suena rasposo/vibrado, claramente distinto
# Con un piezo PASIVO (BUZZER_PASIVO = True) ademas suenan las notas reales,
# asi que los mismos patrones se convierten en pequenas melodias.

def _on(freq):
    if _bz is None: return
    if BUZZER_PASIVO:
        _bz.freq(freq); _bz.duty_u16(32768)
    else:
        _bz(1)

def _off():
    if _bz is None: return
    if BUZZER_PASIVO:
        _bz.duty_u16(0)
    else:
        _bz(0)

def tono(ms, freq=2400):
    """Sonido liso de ms milisegundos."""
    if _bz is None: return
    try:
        _on(freq); time.sleep_ms(ms); _off()
    except Exception:
        try: _off()
        except Exception: pass

def trino(ms, freq=2400, corte=14):
    """Textura rasposa: el zumbador se corta cada 'corte' ms. Suena a vibrado
    y se distingue de un tono liso incluso con zumbador activo."""
    if _bz is None: return
    try:
        fin = time.ticks_add(time.ticks_ms(), ms)
        while time.ticks_diff(fin, time.ticks_ms()) > 0:
            _on(freq); time.sleep_ms(corte)
            _off();    time.sleep_ms(corte)
    except Exception:
        try: _off()
        except Exception: pass

def pausa(ms):
    if ms: time.sleep_ms(ms)

# Notas (solo se oyen con piezo pasivo; con el activo marcan el ritmo)
_DO=2093; _MI=2637; _SOL=3136; _DO8=4186; _LA=1760; _FA=1397

def beep(ms=60, freq=2400):
    """Compatibilidad: un pitido suelto."""
    tono(ms, freq)

# ── El "idioma" de la pantalla ────────────────────────────────────────────────
# Cada evento tiene un patron reconocible sin mirar la pantalla.

def bip_arranque():
    """Arranque: trino corto + nota. 'La pantalla esta viva'."""
    trino(90, _MI); pausa(40); tono(110, _SOL)

def bip_update():
    """Contenido actualizado: casi imperceptible."""
    tono(14, _DO8)

def bip_atencion():
    """Hay un grupo esperando a que vayas al carro: llamada insistente pero
    corta. Tres golpes iguales y separados; se oye desde lejos."""
    for _ in range(3):
        tono(70, _SOL); pausa(90)

def bip_recogido():
    """OK a una RECOGIDA: fanfarria ascendente, el sonido de 'empieza'."""
    tono(70, _DO); pausa(35)
    tono(70, _MI); pausa(35)
    tono(190, _SOL)

def bip_devuelto():
    """OK a una DEVOLUCION: descendente, suena a 'cerrado'. Se distingue del
    de recogida aunque el zumbador sea de una sola nota, por el ritmo."""
    tono(70, _SOL); pausa(35)
    tono(70, _MI); pausa(35)
    tono(190, _DO)

def bip_seleccion():
    """Has pulsado el boton de tu puesto: dos ticks rapidos."""
    tono(25, _SOL); pausa(45); tono(25, _SOL)

def bip_nuevos():
    """Llegan paquetes estando en reposo: la llamada mas larga y llamativa."""
    tono(60, _DO); pausa(45)
    tono(60, _MI); pausa(45)
    tono(60, _SOL); pausa(45)
    tono(240, _DO8)

def bip_error():
    """Gesto no valido (p.ej. pulsar cuando no hay nada que revelar):
    dos zumbidos rasposos y graves, inconfundiblemente 'no'."""
    trino(90, _FA, 22); pausa(70); trino(90, _FA, 22)

# ── Layout ────────────────────────────────────────────────────────────────────
Y_CARRO=4; Y_OPER=30; Y_ORDEN=50; Y_SEP1=68
PKG_Y0=72; PKG_ETIQ=82; PKG_TAG=170; PKG_ELEM=196; PKG_COD=218; PKG_Y1=250
Y_SEP2=252; Y_FOOT=260; Y_WIFI=296
# Vista de lista de puestos ("pulsa tu puesto")
LISTA_TIT=78; LISTA_Y0=110; LISTA_ALTO=44; LISTA_MAX=4

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
    text_center(244, msg, LGRAY, BLACK, scale=1)
    # Estado del firmware: verde al dia, rojo desactualizada (OK 5s para actualizar)
    try:
        if _desactualizada():
            text_center(262, "ACTUALIZAR: OK 5s", RED, BLACK, scale=1)
        else:
            text_center(262, "Firmware al dia", GREEN, BLACK, scale=1)
    except NameError:
        pass
    text(4, 284, "ID " + DEVICE_ID[-4:], DGRAY, BLACK, scale=1)
    # Estado del lector NFC: poder verlo de un vistazo evita tener que
    # enchufar el cable serie para saber si el lector va o no.
    try:
        if nfc_estado == 'ok':
            text(120, 284, "NFC ok", GREEN, BLACK, scale=1)
        elif nfc_estado == 'ko':
            text(120, 284, "NFC no responde", RED, BLACK, scale=1)
    except NameError:
        pass       # aun no se ha inicializado (primer draw del arranque)
    draw_wifi_bar()

def draw_reposo():
    """Reposo: pantalla idle. El NFC del carro ya no sirve para entrar al
    modulo (eso es cosa del lector dedicado de la entrada, o de la seleccion
    manual en el PC) -- aqui solo identifica para confirmar recogidas, igual
    que un boton de puesto, y eso no necesita banner en reposo."""
    draw_idle()

# ── Estado de trabajo ─────────────────────────────────────────────────────────
# work_ops: lo que el servidor dice que hay ahora mismo en este carro, una
# entrada por PUESTO: [{'operario': <clave>, 'data': {...}}, ...]
# En 'data' viaja todo lo que manda el PC: puesto_id, puesto_nombre, boton,
# operario, fase, lote, grupo, grupos, carro, orden y paquetes.
work_ops   = []
work_fp    = ""    # huella del contenido (para ignorar re-pushes identicos)

# Vista actual: 'lista' (que puestos tienen algo) o 'detalle' (un puesto)
vista      = 'lista'
sel_clave  = ''    # puesto que se esta mirando en detalle ('' = ninguno)
work_pkgs  = []    # paquetes del puesto mostrado en detalle
work_idx   = 0     # paquete mostrado dentro de esa lista

# Lo ya confirmado en esta pantalla: clave de puesto -> "lote|fase"
confirmados = {}

# Version que anuncia el servidor: para pintar en reposo si estamos al dia.
fw_servidor = ''
fw_servidor_shown = ''

def _desactualizada():
    """True si el servidor anuncia una version distinta a la que corre aqui."""
    return bool(fw_servidor) and fw_servidor != FW_VERSION

# Fases que manda el PC en cada push
FASE_RECOGER  = 'recoger'    # hay que coger estos paquetes del carro
FASE_TRABAJO  = 'trabajando' # ya confirmado, el operario los tiene
FASE_DEVOLVER = 'devolver'   # hay que devolverlos al carro
FASE_FIN      = 'fin'        # carro terminado para ese puesto

def _d(o):
    return o.get('data') or {}

def _clave(o):
    """Identidad del puesto dentro del canal (lo que el servidor usa de clave)."""
    return _d(o).get('puesto_id') or o.get('operario', '')

def _boton_de(o):
    try:
        return int(_d(o).get('boton') or 0)
    except (TypeError, ValueError):
        return 0

def _fase_de(o):
    return _d(o).get('fase') or FASE_RECOGER

def _sello(o):
    """Lo que identifica una accion concreta: mismo lote + misma fase."""
    return "%s|%s" % (_d(o).get('lote') or '', _fase_de(o))

def _pide_accion(o):
    """True si este puesto espera que alguien vaya al carro y pulse OK."""
    if _fase_de(o) not in (FASE_RECOGER, FASE_DEVOLVER):
        return False
    return confirmados.get(_clave(o)) != _sello(o)

def hay_pendiente():
    """True si algun puesto del carro espera una accion fisica."""
    return any(_pide_accion(o) for o in work_ops)

def _tag_de(o):
    """UID de la tarjeta del OPERARIO de esa entrada, normalizado (hex mayus).

    La identidad ahora es del operario, no del puesto: el PC manda 'operario_tag'
    en el payload. Se mantiene 'tag_uid' como respaldo por compatibilidad."""
    raw = _d(o).get('operario_tag') or _d(o).get('tag_uid') or ''
    return str(raw).replace(':', '').replace(' ', '').upper()

def _op_por_boton(n):
    for o in work_ops:
        if _boton_de(o) == n:
            return o
    return None

def _op_por_tag(uid):
    if not uid:
        return None
    for o in work_ops:
        if _tag_de(o) == uid:
            return o
    return None

def _op_sel():
    """El puesto que se esta viendo en detalle. Se guarda por clave de puesto y
    no por numero de boton: con tarjeta NFC puede no haber boton."""
    if not sel_clave:
        return None
    for o in work_ops:
        if _clave(o) == sel_clave:
            return o
    return None

# ── Dibujo: cabecera comun ────────────────────────────────────────────────────

def draw_work_header(d, titulo='', extra=''):
    """Cabecera fija: carro, puesto y orden."""
    carro = str(d.get('carro', ''))[:8]
    orden = str(d.get('orden', '') or d.get('bono', ''))[:13]
    rect(0, 0, 240, PKG_Y0, BLACK)
    rect(0, Y_SEP2, 240, 320-Y_SEP2, BLACK)
    text(4, Y_CARRO, 'CARRO ' + carro, WHITE, BLACK, scale=3)
    if titulo:
        text(4, Y_OPER, str(titulo)[:10], GREEN, BLACK, scale=2)
    if extra:
        e = str(extra)[:6]
        text(240 - len(e)*18 - 4, Y_OPER, e, LGRAY, BLACK, scale=2)
    text(4, Y_ORDEN, orden, YELLOW, BLACK, scale=2)
    hline(0, Y_SEP1, 240, DGRAY)
    hline(0, Y_SEP2, 240, DGRAY)
    draw_wifi_bar()

# ── Vista LISTA: que puestos tienen algo pendiente ────────────────────────────

def draw_lista():
    """Pantalla por defecto en modo trabajo: quien tiene que venir al carro."""
    rect(0, 0, 240, 320, BLACK)
    text(4, Y_CARRO, 'CARRO ' + str(mi_carro or '')[:8], WHITE, BLACK, scale=3)
    hline(0, Y_SEP1, 240, DGRAY)
    if nfc is not None:
        text_center(LISTA_TIT, "PASA TU TARJETA", ORANGE, BLACK, scale=2)
    else:
        text_center(LISTA_TIT, "PULSA TU PUESTO", ORANGE, BLACK, scale=2)

    # Los que piden accion primero: son los que tienen que venir
    ops = sorted(work_ops, key=lambda o: (not _pide_accion(o), _boton_de(o)))
    y = LISTA_Y0
    for o in ops[:LISTA_MAX]:
        d = _d(o)
        n = _boton_de(o)
        fase = _fase_de(o)
        npk = len(d.get('paquetes', []) or [])
        nombre = str(d.get('puesto_nombre') or d.get('operario') or '')[:9]

        if fase == FASE_DEVOLVER and _pide_accion(o):
            etiq, color = "DEVOLVER", RED
        elif fase == FASE_RECOGER and _pide_accion(o):
            etiq, color = "RECOGER", GREEN
        elif fase == FASE_FIN:
            etiq, color = "FIN", LGRAY
        else:
            etiq, color = "en curso", DGRAY

        # Como se identifica ese puesto: numero de boton, o tarjeta NFC
        hrect(4, y - 2, 26, 24, color)
        if n:
            text(10, y + 2, str(n), color, BLACK, scale=2)
        elif _tag_de(o):
            text(10, y + 4, "NFC", color, BLACK, scale=1)
        text(36, y + 2, nombre, WHITE if color != DGRAY else LGRAY, BLACK, scale=2)
        text(36, y + 22, etiq + ("" if fase == FASE_FIN else " %d" % npk),
             color, BLACK, scale=1)
        y += LISTA_ALTO

    if not work_ops:
        text_center(LISTA_Y0 + 20, "Sin trabajo", LGRAY, BLACK, scale=2)

    text(4, 274, "8 = OK", DGRAY, BLACK, scale=1)
    draw_wifi_bar()

# ── Vista DETALLE: lo que tiene que hacer un puesto ───────────────────────────

def draw_progress():
    rect(0, Y_FOOT, 240, 18, BLACK)
    if work_pkgs:
        text(4, Y_FOOT, "%d/%d" % (work_idx+1, len(work_pkgs)), LGRAY, BLACK, scale=2)

def draw_pie(msg, color):
    """Linea de instruccion bajo el separador inferior."""
    rect(60, Y_FOOT, 180, 18, BLACK)
    text(240 - len(msg)*9 - 4, Y_FOOT, msg, color, BLACK, scale=1)

def draw_package():
    """Zona central con el paquete actual (redibujado parcial)."""
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
        por = str(p.get('por') or '')[:13]
        if por:
            # Puesto/maquina que esta trabajando este paquete
            text_center(PKG_ELEM, por, YELLOW, BLACK, scale=2)
            text_center(PKG_COD, elem, LGRAY, BLACK, scale=2)
            draw_progress()
            return
    text_center(PKG_ELEM, elem, WHITE, BLACK, scale=2)
    if cod and cod != elem:
        text_center(PKG_COD, cod, LGRAY, BLACK, scale=2)
    draw_progress()

def draw_fin(d):
    """El PC dice que este puesto ha terminado el carro."""
    rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
    text_center(110, "CARRO", GREEN, BLACK, scale=3)
    text_center(150, "FINALIZADO", GREEN, BLACK, scale=3)
    text_center(200, "Nada mas que coger", LGRAY, BLACK, scale=1)
    rect(0, Y_FOOT, 240, 18, BLACK)

def draw_detalle():
    """Dibuja lo que toca del puesto seleccionado segun su fase."""
    global work_pkgs, work_idx
    o = _op_sel()
    if o is None:
        mostrar_lista()
        return
    d = _d(o)
    work_pkgs = d.get('paquetes', [])[:40]
    if work_idx >= len(work_pkgs):
        work_idx = 0
    fase = _fase_de(o)
    grupo = str(d.get('grupo') or '')
    grupos = str(d.get('grupos') or '')
    extra = (grupo + "/" + grupos) if (grupo and grupos and grupos != '1') else grupo

    draw_work_header(d, d.get('puesto_nombre') or d.get('operario') or '', extra)

    if fase == FASE_FIN:
        draw_fin(d)
        draw_pie("8=OK", DGRAY)
        return

    draw_package()
    if _pide_accion(o):
        if fase == FASE_DEVOLVER:
            draw_pie("8=OK ya los deje", RED)
        else:
            draw_pie("8=OK ya los tengo", GREEN)
    else:
        draw_pie("en curso", DGRAY)

def next_package():
    global work_idx
    if not work_pkgs: return
    work_idx = (work_idx + 1) % len(work_pkgs)
    draw_package()

# ── Navegacion ────────────────────────────────────────────────────────────────

def mostrar_lista():
    global vista, sel_clave, work_pkgs
    vista = 'lista'
    sel_clave = ''
    work_pkgs = []
    if work_ops:
        draw_lista()
    else:
        draw_idle()

def _abrir_detalle(o):
    """Muestra lo de ese puesto. Da igual si se identifico con boton o tarjeta."""
    global vista, sel_clave, work_idx
    vista = 'detalle'
    sel_clave = _clave(o)
    work_idx = 0
    draw_detalle()
    bip_seleccion()

def _sin_trabajo_aqui(titulo):
    """Ese puesto existe pero no tiene nada en este carro."""
    rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
    text_center(130, titulo, LGRAY, BLACK, scale=3)
    text_center(175, "sin trabajo aqui", LGRAY, BLACK, scale=2)
    bip_error()
    time.sleep_ms(900)
    mostrar_lista()

def seleccionar_puesto(n):
    """Pulsado el boton n (1-7): mostrar lo de ese puesto, si tiene algo."""
    o = _op_por_boton(n)
    if o is None:
        _sin_trabajo_aqui("PUESTO %d" % n)
        return
    _abrir_detalle(o)

def seleccionar_por_tag(uid):
    """Pasada una tarjeta por el lector: mismo efecto que pulsar tu boton.

    La tarjeta identifica al OPERARIO. Si el UID no corresponde a ningun
    operario con trabajo en este carro puede ser porque no tiene nada aqui o
    porque la tarjeta no esta dada de alta -- eso se hace en Admin con el
    lector RFID dedicado de la entrada del puesto, no con este lector del
    carro (que solo confirma, nunca identifica de alta).
    """
    o = _op_por_tag(uid)
    if o is not None:
        _abrir_detalle(o)
        return
    rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
    text_center(110, "TARJETA", ORANGE, BLACK, scale=3)
    text_center(150, "SIN TRABAJO AQUI", ORANGE, BLACK, scale=1)
    text_center(180, uid[:20], LGRAY, BLACK, scale=2)
    bip_error()
    time.sleep_ms(1600)
    mostrar_lista()

# ── Eventos hacia el servidor ─────────────────────────────────────────────────
# Se mandan desde el bucle principal (no en el momento del pulsador) para que
# la pantalla nunca se congele si la WiFi esta caida: se reintentan hasta salir.
eventos_pend = []

def _urlenc(s):
    """Percent-encoding minimo para meter texto en una query string."""
    out = ""
    for ch in str(s):
        if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') or ch in '-_.':
            out += ch
        else:
            for b in ch.encode('utf-8'):
                out += '%%%02X' % b
    return out

def _encolar_evento(params):
    eventos_pend.append(params)
    while len(eventos_pend) > 10:
        eventos_pend.pop(0)

def _flush_eventos():
    """Intenta mandar los eventos encolados. Para al primer fallo de red."""
    while eventos_pend:
        ruta = "/api/esp32/evento?id=" + DEVICE_ID
        for k, v in eventos_pend[0].items():
            ruta += "&" + k + "=" + _urlenc(v)
        if http_get(HOST_IP, PORT, ruta) is None:
            return False
        eventos_pend.pop(0)
    return True

def confirmar_ok():
    """Boton 8: confirmar lo que la pantalla esta pidiendo al puesto mostrado."""
    o = _op_sel()
    if o is None:
        avisar_pulsa_puesto()
        return
    if not _pide_accion(o):
        # Ese puesto no tiene nada que confirmar ahora mismo
        rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
        text_center(140, "NADA QUE", LGRAY, BLACK, scale=2)
        text_center(170, "CONFIRMAR", LGRAY, BLACK, scale=2)
        bip_error()
        time.sleep_ms(900)
        mostrar_lista()
        return
    d = _d(o)
    fase = _fase_de(o)
    confirmados[_clave(o)] = _sello(o)

    rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
    final = fase == FASE_DEVOLVER and bool(d.get('final'))
    if final:
        # Era la ultima devolucion del carro: rematar con el mensaje de cierre
        text_center(110, "DEVUELTOS", GREEN, BLACK, scale=2)
        text_center(150, "CARRO", GREEN, BLACK, scale=3)
        text_center(190, "FINALIZADO", GREEN, BLACK, scale=3)
    elif fase == FASE_DEVOLVER:
        text_center(130, "DEVUELTOS", GREEN, BLACK, scale=3)
    else:
        text_center(130, "RECOGIDOS", GREEN, BLACK, scale=3)
    nombre = str(d.get('puesto_nombre') or '')[:13]
    if nombre and not final:
        text_center(180, nombre, WHITE, BLACK, scale=2)
    if fase == FASE_DEVOLVER:
        bip_devuelto()
    else:
        bip_recogido()
    time.sleep_ms(1600 if final else 500)

    _encolar_evento({
        'tipo': 'confirmacion',
        'fase': fase,
        'carro': str(d.get('carro', '') or ''),
        'puesto': str(d.get('puesto_id') or ''),
        'operario': str(d.get('operario') or ''),
        'lote': str(d.get('lote') or ''),
        'grupo': str(d.get('grupo') or ''),
    })
    print("OK", fase, "puesto", d.get('puesto_id'), "lote", d.get('lote'))
    # Confirmado = el operario ya se los ha llevado (o los ha dejado): quitar
    # los paquetes de la pantalla y dejarla libre para el siguiente puesto.
    mostrar_lista()

def liberar_puesto(n):
    """Pulsacion LARGA de un boton de puesto: soltar ese puesto del carro.

    Salida de emergencia para un puesto que se quedo colgado (el PC se cerro
    de golpe, se fue la red al cancelar...). Lo quita de la pantalla y se lo
    dice al servidor para que no vuelva en el siguiente poll.
    """
    global work_ops, work_fp
    o = _op_por_boton(n)
    if o is None:
        bip_error()
        return
    d = _d(o)
    _encolar_evento({
        'tipo': 'liberar',
        'carro': str(d.get('carro', '') or ''),
        'puesto': str(d.get('puesto_id') or ''),
        'operario': str(d.get('operario') or ''),
    })
    confirmados.pop(_clave(o), None)
    work_ops = [x for x in work_ops if x is not o]
    work_fp = _fingerprint(work_ops)
    rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
    text_center(130, "PUESTO %d" % n, YELLOW, BLACK, scale=3)
    text_center(175, "LIBERADO", YELLOW, BLACK, scale=2)
    bip_devuelto()
    time.sleep_ms(1000)
    print("LIBERADO puesto", d.get('puesto_id'))
    if work_ops:
        mostrar_lista()
    else:
        globals()['en_work_mode'] = False
        mostrar_lista()

def avisar_pulsa_puesto():
    """OK pulsado sin haber elegido puesto: decir que hay que identificarse."""
    rect(0, PKG_Y0, 240, PKG_Y1-PKG_Y0, BLACK)
    text_center(120, "PULSA ANTES", ORANGE, BLACK, scale=2)
    text_center(155, "TU PUESTO", ORANGE, BLACK, scale=3)
    bip_error()
    time.sleep_ms(1100)
    mostrar_lista()

# ── Huella del contenido ──────────────────────────────────────────────────────

def _fp_op(o):
    d = _d(o)
    pkgs = d.get('paquetes', [])
    # Lote y fase entran en la huella: cualquier cambio de estado redibuja
    return "%s|%s|%s|%s|%s|%s" % (_clave(o), d.get('carro'), d.get('orden'),
                                  d.get('lote') or '', _fase_de(o),
                                  ",".join(str(p.get('etiqueta')) + str(p.get('elem'))
                                           + ('B' + str(p.get('por') or '') if p.get('bloqueado') else '')
                                           for p in pkgs))

def _fingerprint(ops):
    return "||".join(_fp_op(o) for o in ops)

def _parse_ops(d):
    """Lista de puestos activos de la respuesta del servidor.

    Formato nuevo: d['ops'] = [{'operario': <clave>, 'data':..}, ..]. Si el
    servidor fuera antiguo y no mandara 'ops', se cae al campo unico d['data'].
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

# ── OTA de aplicacion por WiFi ────────────────────────────────────────────────
# Descarga app.py (+libs) del servidor, verifica sha256 y reinicia. El lanzador
# (main.py) NO se toca: si el nuevo app.py fallara al arrancar, se revierte solo.

def _marcar_arranque_ok():
    """Pone a 0 el contador de arranques fallidos (lo lee el lanzador main.py).
    Se llama al entrar en el bucle: probar que el fichero carga bien evita que un
    corte de WiFi que reinicie la placa se confunda con un OTA defectuoso."""
    try:
        with open("boot_fails.txt", "w") as f:
            f.write("0")
    except Exception:
        pass

def _sha256_hex(data):
    import uhashlib, ubinascii
    return ubinascii.hexlify(uhashlib.sha256(data).digest()).decode()

def _reinyectar_wifi(texto):
    """Mete el SSID/PASSWORD y la IP fija de ESTA pantalla en el app.py
    descargado, para que el OTA nunca cambie la red con la que ya esta
    conectada ni le quite la IP que tiene asignada (la red no tiene DHCP:
    perderla la dejaria incomunicada y sin forma de recuperarse por WiFi)."""
    lineas = texto.split("\n")
    for i, ln in enumerate(lineas):
        st = ln.lstrip()
        if st.startswith("SSID") and "=" in ln:
            lineas[i] = "SSID     = " + repr(SSID)
        elif st.startswith("PASSWORD") and "=" in ln:
            lineas[i] = "PASSWORD = " + repr(PASSWORD)
        elif st.startswith("STATIC_IP") and "=" in ln:
            lineas[i] = "STATIC_IP   = " + repr(STATIC_IP)
    return "\n".join(lineas)

def http_get_bytes(host, port, path):
    """GET que devuelve el body como bytes crudos (para descargar el firmware)."""
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(15)
        s.connect(addr)
        req = "GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n" % (path, host)
        s.send(req.encode())
        resp = b""
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            resp += chunk
        s.close()
        idx = resp.find(b"\r\n\r\n")
        if idx < 0:
            return None
        head, body = resp[:idx], resp[idx+4:]
        clen = None
        for line in head.split(b"\r\n"):
            if line[:15].lower() == b"content-length:":
                try:
                    clen = int(line.split(b":", 1)[1].strip())
                except Exception:
                    clen = None
        if clen is not None and len(body) != clen:
            print("OTA: body incompleto", len(body), "!=", clen)
            return None
        return body
    except Exception as e:
        print("HTTP bytes error:", e)
        return None

def _ota_fallo(msg):
    print("OTA fallo:", msg)
    rect(0, 240, 240, 44, BLACK)
    text_center(255, ("OTA fallo: " + msg)[:24], RED, BLACK, scale=1)
    time.sleep_ms(1800)   # no se ha tocado nada: se sigue con el firmware actual

def hacer_ota(ota):
    """Aplica una actualizacion: descarga+verifica TODO y solo entonces
    intercambia y reinicia. Ante cualquier fallo, no toca nada."""
    import os
    files = ota.get('files') or []
    version = ota.get('version') or ''
    if not files:
        return
    rect(0, 0, 240, 320, BLACK)
    text_center(120, "ACTUALIZANDO", ORANGE, BLACK, scale=2)
    text_center(160, "NO APAGAR", RED, BLACK, scale=2)
    if version:
        text_center(210, version[:18], LGRAY, BLACK, scale=1)

    descargados = {}
    for f in files:
        nombre = f.get('name')
        if not nombre:
            return _ota_fallo("nombre")
        data = http_get_bytes(HOST_IP, PORT,
                              "/api/esp32/firmware/file?name=" + _urlenc(nombre))
        if data is None:
            return _ota_fallo("descarga")
        size = f.get('size')
        if size is not None and len(data) != size:
            return _ota_fallo("tam " + nombre)
        sha = f.get('sha256')
        if sha and _sha256_hex(data) != sha:
            return _ota_fallo("sha " + nombre)
        if nombre == "app.py":
            try:
                data = _reinyectar_wifi(data.decode("utf-8")).encode("utf-8")
            except Exception as e:
                print("OTA reinyeccion:", e)
        descargados[nombre] = data

    # Escribir a *.new (todavia no se pisa el firmware en uso)
    for nombre, data in descargados.items():
        try:
            with open(nombre + ".new", "wb") as fp:
                fp.write(data)
        except Exception as e:
            print("OTA write:", e)
            return _ota_fallo("escritura")

    # Copia de seguridad del app.py actual (para el rollback del lanzador)
    try:
        with open("app.py", "rb") as fp:
            actual = fp.read()
        with open("app_prev.py", "wb") as fp:
            fp.write(actual)
    except OSError:
        pass

    # Intercambio: borrar el original y renombrar el .new encima
    for nombre in descargados:
        try:
            os.remove(nombre)
        except OSError:
            pass
        try:
            os.rename(nombre + ".new", nombre)
        except OSError as e:
            print("OTA rename:", e)

    text_center(250, "OK, reiniciando...", GREEN, BLACK, scale=1)
    time.sleep_ms(700)
    machine.reset()

def actualizar_por_ok():
    """OTA lanzado a mano desde reposo (pulsacion larga de OK, boton 8).
    Pide el manifiesto al servidor y aplica el OTA; si no hay novedad o red,
    avisa y vuelve a reposo."""
    rect(0, 0, 240, 320, BLACK)
    text_center(130, "BUSCANDO", ORANGE, BLACK, scale=2)
    text_center(165, "ACTUALIZACION", ORANGE, BLACK, scale=2)
    body = http_get(HOST_IP, PORT, "/api/esp32/firmware/version")
    info = None
    if body:
        try:
            info = json.loads(body)
        except Exception:
            info = None
    if info and (info.get('version') or '') and info.get('version') != FW_VERSION:
        hacer_ota({'files': info.get('files') or [], 'version': info.get('version')})
    else:
        _ota_fallo("sin novedad" if info else "sin red")
    if not en_work_mode:
        draw_reposo()

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
        # Sin ahorro de energia. Por defecto MicroPython deja el ESP32 en
        # WIFI_PS_MIN_MODEM: la radio duerme entre balizas del punto de acceso
        # y este le RETIENE los paquetes hasta que despierta. Eso mete cientos
        # de ms (a veces segundos) en CADA respuesta del servidor -- se nota en
        # todo: paquetes que tardan en salir, confirmaciones lentas. El
        # servidor responde en menos de 1 ms, asi que la espera era esta.
        # A cambio sube algo el consumo (esta pantalla va con power bank).
        try:
            wlan.config(pm=network.WLAN.PM_NONE)
        except Exception as e:
            print("Ahorro de energia WiFi no desactivado:", e)
        if STATIC_IP:
            # ANTES del connect: la red no reparte IPs, si no se fija aqui
            # la pantalla no llega al servidor.
            try:
                wlan.ifconfig((STATIC_IP, SUBNET_MASK, GATEWAY, DNS))
            except Exception as e:
                print("IP fija no aplicada:", e)
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
# Botones 1-7 (puestos) y boton 8 (OK), todos a GND con pull-up interno
btns_puesto = [Pin(p, Pin.IN, Pin.PULL_UP) for p in BTN_PUESTO_PINS]
btn_ok      = Pin(BTN_OK_PIN, Pin.IN, Pin.PULL_UP)

# ── Lector NFC: opcional y supervisado ───────────────────────────────────────
# Totalmente opcional: sin lector, los pulsadores hacen lo mismo. Y si esta
# pero se cuelga, NO se abandona: se reintenta cada NFC_REINTENTO_S para
# siempre, igual que se hace con la WiFi. Un lector muerto hasta reflashear no
# es aceptable en produccion.
#   'off' = desactivado por configuracion
#   'ok'  = responde
#   'ko'  = deberia estar ahi pero no contesta (se sigue reintentando)
nfc = None
nfc_estado = 'off'
nfc_fallos = 0

if NFC_SDA_PIN is not None and NFC_SCL_PIN is not None:
    try:
        from pn532_i2c import PN532
        nfc = PN532(sda=NFC_SDA_PIN, scl=NFC_SCL_PIN)
        nfc_estado = 'ok' if nfc.reiniciar() else 'ko'
        print("NFC:", nfc_estado, nfc.version)
    except Exception as e:
        nfc, nfc_estado = None, 'off'
        print("Sin lector NFC:", e)

def nfc_reintentar():
    """Vuelve a levantar el lector (recupera el bus I2C y lo reconfigura)."""
    global nfc_estado, nfc_fallos
    if nfc is None:
        return
    nfc_fallos = 0
    nuevo = 'ok' if nfc.reiniciar() else 'ko'
    if nuevo != nfc_estado:
        print("NFC ->", nuevo)
        nfc_estado = nuevo
        if not en_work_mode:
            draw_reposo()
    else:
        nfc_estado = nuevo

bip_arranque()   # confirma que el zumbador esta vivo tras flashear

draw_idle("Conectando WiFi...")
import network, socket
conectado = conectar_wifi()
draw_idle()  # refresca con la barra WiFi actualizada

MAX_INTENTOS_WIFI = 10   # tras estos intentos seguidos sin WiFi, reset completo de la placa

ultimo_poll  = time.ticks_ms() - POLL_INTERVAL * 1000  # forzar poll inmediato
en_work_mode = False
btns_prev    = [1] * len(BTN_PUESTO_PINS)   # estado anterior de cada boton 1-7
btns_last    = [0] * len(BTN_PUESTO_PINS)   # ultimo flanco (antirrebote)
btns_t0      = [0] * len(BTN_PUESTO_PINS)   # inicio de la pulsacion en curso
btns_armado  = [False] * len(BTN_PUESTO_PINS)
avisos_dados = 0                  # recordatorios sonoros ya dados de este estado
btn_ok_prev  = 1
btn_ok_last  = 0
btn_ok_t0    = 0                  # inicio de la pulsacion de OK (para la larga)
btn_ok_ota_hecho = False          # ya se lanzo el OTA en esta pulsacion larga
btn_ok_hold_shown = -1            # segundo mostrado en la cuenta atras (-1 = ninguno)
ultimo_avance = time.ticks_ms()   # timer de rotacion automatica de paquetes
ultimo_envio  = 0                 # ultimo intento de mandar eventos pendientes
ultimo_aviso  = 0                 # ultimo recordatorio sonoro de accion pendiente
ultima_accion = time.ticks_ms()   # ultima pulsacion (para volver solo a la lista)
ultimo_nfc    = 0                 # ultima consulta al lector NFC
nfc_uid_prev  = ''                # ultima tarjeta leida (anti-repeticion)
nfc_uid_ts    = 0                 # cuando se leyo
intentos_wifi = 0
arranque_marcado = False   # se pone a True tras la 1a vuelta (arranque valido)

# El bucle NUNCA debe morir: cualquier excepcion se registra y se sigue.
while True:
  try:
    now = time.ticks_ms()

    # Primer ciclo completo: el fichero carga bien -> limpiar contador de fallos
    if not arranque_marcado:
        arranque_marcado = True
        _marcar_arranque_ok()

    # ── Botones 1-7: corta = ver mi puesto, larga = liberarlo ─────────
    for i, bp_ in enumerate(btns_puesto):
        bv = bp_.value()
        if bv != btns_prev[i]:
            # Test de cableado: cuadradito junto a la barra WiFi al pulsar.
            # Si no aparece, la senal no llega a ese GPIO.
            rect(226 - i*12, Y_WIFI + 4, 10, 10, YELLOW if bv == 0 else BLACK)
            print("BTN", i + 1, "pulsado" if bv == 0 else "soltado")
        if bv == 0 and btns_prev[i] == 1 and time.ticks_diff(now, btns_last[i]) > 250:
            # Flanco de bajada: armar y esperar a ver si es corta o larga
            btns_t0[i] = now
            btns_armado[i] = en_work_mode
            ultima_accion = now
        if bv == 0 and btns_armado[i] and time.ticks_diff(now, btns_t0[i]) >= LONG_PRESS_MS:
            # Mantenido: liberar ese puesto (se quedo colgado)
            btns_armado[i] = False
            btns_last[i] = now
            ultima_accion = now
            ultimo_avance = now
            liberar_puesto(i + 1)
        if bv == 1 and btns_prev[i] == 0:
            if btns_armado[i]:
                # Soltado antes del umbral: abrir el detalle de ese puesto
                btns_armado[i] = False
                btns_last[i] = now
                ultima_accion = now
                ultimo_avance = now
                seleccionar_puesto(i + 1)
        btns_prev[i] = bv

    # ── Lector NFC caido: reintentar (para siempre, como con la WiFi) ─
    if nfc is not None and nfc_estado == 'ko' \
            and time.ticks_diff(now, ultimo_nfc) >= NFC_REINTENTO_S * 1000:
        ultimo_nfc = now
        nfc_reintentar()

    # ── Lector NFC: pasar la tarjeta = pulsar el boton de tu puesto ───
    elif nfc is not None and nfc_estado == 'ok' \
            and time.ticks_diff(now, ultimo_nfc) >= NFC_POLL_MS:
        ultimo_nfc = now
        uid = nfc.leer_uid(timeout_ms=80)
        if uid is None:
            # No hay tarjeta... o el modulo se ha colgado. Solo tras varios
            # fallos seguidos se comprueba de verdad (un ping por lectura
            # seria carisimo, y no leer nada es lo normal).
            nfc_fallos += 1
            if nfc_fallos >= NFC_FALLOS_MAX:
                nfc_fallos = 0
                if not nfc.vivo():
                    print("NFC no responde: recuperando bus")
                    nfc_estado = 'ko'
                    if not en_work_mode:
                        draw_reposo()
        else:
            nfc_fallos = 0
        if uid:
            # Ignorar la misma tarjeta si se queda apoyada en el lector
            repetida = (uid == nfc_uid_prev and
                        time.ticks_diff(now, nfc_uid_ts) < NFC_REPETIR_MS)
            nfc_uid_prev = uid
            nfc_uid_ts = now
            # El NFC del carro SOLO identifica en modo trabajo (confirmar
            # recoger/devolver). En reposo se ignora sin mas: ni entra al
            # modulo ni sirve para "Capturar tag" en Admin -- eso es cosa del
            # lector RFID dedicado de la entrada del puesto (ver
            # app/routes/operarios.py:api_engastado_v3_entrada). Se sigue
            # leyendo el chip igualmente (arriba) para poder detectar si el
            # lector se ha colgado.
            if not repetida and en_work_mode:
                print("NFC:", uid)
                ultima_accion = now
                ultimo_avance = now
                seleccionar_por_tag(uid)

    # ── Boton 8 (OK): confirmar lo que pide la pantalla ───────────────
    b_ok = btn_ok.value()
    if b_ok != btn_ok_prev:
        rect(212 - 6*12, Y_WIFI + 4, 10, 10, GREEN if b_ok == 0 else BLACK)
        print("BTN_OK:", "pulsado" if b_ok == 0 else "soltado")
        if b_ok == 0:
            btn_ok_t0 = now
            btn_ok_ota_hecho = False
            btn_ok_hold_shown = -1
        elif btn_ok_hold_shown >= 0 and not en_work_mode:
            btn_ok_hold_shown = -1
            draw_reposo()          # soltado antes de los 5s: restaurar reposo
    # Pulsacion LARGA de OK, SOLO en reposo y con firmware desactualizado:
    # actualizar por WiFi. Nunca en modo trabajo (ahi OK solo confirma).
    if b_ok == 0 and not en_work_mode \
            and _desactualizada() and not btn_ok_ota_hecho:
        falta = OTA_HOLD_MS - time.ticks_diff(now, btn_ok_t0)
        if falta <= 0:
            btn_ok_ota_hecho = True
            btn_ok_hold_shown = -1
            actualizar_por_ok()
        else:
            seg = falta // 1000 + 1
            if seg != btn_ok_hold_shown:
                btn_ok_hold_shown = seg
                rect(0, 262, 240, 18, BLACK)
                text_center(262, "ACTUALIZAR EN %d" % seg, ORANGE, BLACK, scale=1)
    if b_ok == 0 and btn_ok_prev == 1 and time.ticks_diff(now, btn_ok_last) > 250:
        btn_ok_last = now
        ultima_accion = now
        ultimo_avance = now
        if en_work_mode and vista == 'detalle':
            confirmar_ok()
        elif en_work_mode:
            # OK sin haberse identificado: NUNCA adivinar de quien es. Cada
            # confirmacion tiene que llevar detras el boton de un puesto.
            avisar_pulsa_puesto()
    btn_ok_prev = b_ok

    # ── Volver solo a la lista tras un rato sin tocar nada ────────────
    if en_work_mode and vista == 'detalle' \
            and time.ticks_diff(now, ultima_accion) >= VOLVER_LISTA_S * 1000:
        ultima_accion = now
        mostrar_lista()

    # ── Eventos pendientes de contar al servidor (reintento cada 3s) ──
    if eventos_pend and conectado and time.ticks_diff(now, ultimo_envio) >= 3000:
        ultimo_envio = now
        _flush_eventos()

    # ── Recordatorio sonoro: alguien tiene que venir al carro ─────────
    # Con tope: si nadie viene, deja de sonar. El aviso sigue en pantalla,
    # pero un zumbador pitando sin parar en el taller es insufrible (y si algo
    # se queda colgado, no puede convertirse en una mosca eterna).
    if en_work_mode and hay_pendiente() and avisos_dados < AVISO_MAX:
        if time.ticks_diff(now, ultimo_aviso) >= AVISO_PENDIENTE_S * 1000:
            ultimo_aviso = now
            avisos_dados += 1
            bip_atencion()

    # ── Rotacion automatica de paquetes del puesto que se esta viendo ─
    if en_work_mode and vista == 'detalle' and len(work_pkgs) > 1 \
            and time.ticks_diff(now, ultimo_avance) >= AUTO_ADVANCE_S * 1000:
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
        ruta = "/api/esp32/current?id=" + DEVICE_ID + "&nfc=" + nfc_estado + "&fw=" + FW_VERSION
        if CARRO_ASIGNADO:
            ruta += "&carro=" + CARRO_ASIGNADO
        body = http_get(HOST_IP, PORT, ruta)
        if body:
            try:
                d = json.loads(body)
                # OTA por WiFi: si el servidor ofrece otra version, actualizar
                # y reiniciar (hacer_ota no retorna si tiene exito).
                _ota = d.get('ota')
                if _ota and _ota.get('update') and _ota.get('version') \
                        and _ota.get('version') != FW_VERSION:
                    hacer_ota(_ota)
                # Version del servidor: para el estado de firmware en reposo
                fw_servidor = d.get('fw_server') or ''
                # Carro que nos asigna el servidor (Admin -> Display Carro)
                ca = d.get('carro_asignado') or CARRO_ASIGNADO
                if ca != mi_carro:
                    mi_carro = ca
                    if not en_work_mode:
                        draw_reposo()
                        fw_servidor_shown = fw_servidor
                ops = _parse_ops(d)
                fp = _fingerprint(ops)
                if not ops:
                    if en_work_mode:
                        # Datos expirados o "clear" de todos → volver a reposo
                        en_work_mode = False
                        work_fp = ""; work_ops = []; work_pkgs = []
                        vista = 'lista'; sel_clave = ''
                        confirmados.clear()
                        draw_reposo()
                        fw_servidor_shown = fw_servidor
                    elif fw_servidor_shown != fw_servidor:
                        # En reposo: cambio el estado de firmware
                        draw_reposo()
                        fw_servidor_shown = fw_servidor
                elif fp != work_fp:
                    # Contenido nuevo del servidor
                    habia = en_work_mode
                    antes_pendiente = hay_pendiente()
                    work_fp  = fp
                    work_ops = ops
                    en_work_mode = True
                    # Olvidar confirmaciones de puestos que ya no estan
                    vivos = set(_clave(o) for o in work_ops)
                    for k in list(confirmados):
                        if k not in vivos:
                            del confirmados[k]
                    # Si estabamos viendo un puesto que sigue ahi, mantenerlo;
                    # si desaparecio, volver a la lista.
                    if vista == 'detalle' and _op_sel() is not None:
                        work_idx = 0
                        ultimo_avance = now
                        draw_detalle()
                    else:
                        mostrar_lista()
                    # Aviso sonoro segun lo que ha pasado. Estado nuevo =
                    # vuelve a contar desde cero el tope de recordatorios.
                    avisos_dados = 0
                    if hay_pendiente() and not antes_pendiente:
                        ultimo_aviso = now
                        avisos_dados = 1
                        bip_atencion()
                    elif not habia:
                        bip_nuevos()
                    else:
                        bip_update()
                    print("work OK ops", len(work_ops))
            except Exception as ex:
                print("JSON err:", ex)

    time.sleep_ms(20)
  except Exception as ex:
    print("loop err:", ex)
    time.sleep_ms(500)
