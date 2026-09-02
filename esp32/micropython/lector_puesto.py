# lector_puesto.py -- Lector RFID de puesto para gen4-ESP32-24 (ESP32-S3).
#
# Se instala como app.py junto a launcher.py. No comparte el ciclo de carros:
# esta placa solo identifica al operario, muestra el resultado y deja el DB9
# preparado como expansion digital para el futuro multiplexor.

import binascii
import json
import time
import machine
import framebuf
from machine import Pin, SPI, SoftSPI

try:
    import network
except ImportError:
    network = None

try:
    import socket
except ImportError:
    socket = None

from pn532_i2c import PN532

FW_VERSION = "2026-09-02a"

# Estas lineas las inyecta el flasheo USB. No guardar credenciales reales aqui.
SSID = "YOUR_SSID"
PASSWORD = "YOUR_PASSWORD"
STATIC_IP = ""
SUBNET_MASK = "255.255.255.0"
GATEWAY = "192.168.50.5"
DNS = "192.168.50.5"
HOST_IP = "192.168.50.1"
PORT = 5001

ENTRADA_PATH = "/api/puestos/engastado_v3/entrada"

# gen4-Breakout: PN532 en I2C, zumbador y ocho lineas DB9 de expansion.
NFC_SDA_PIN = 6
NFC_SCL_PIN = 5
BUZZER_PIN = 18
BUZZER_PASIVO = False
DB9_PINS = (17, 16, 15, 48, 47, 38, 39, 40)
NFC_POLL_MS = 300
NFC_REPETIR_MS = 3000
NFC_REINTENTO_S = 10
NFC_FALLOS_MAX = 5

DEVICE_ID = binascii.hexlify(machine.unique_id()).decode()
wifi_ip = ""


# --- Display ILI9341 ---------------------------------------------------------
Pin(4, Pin.OUT, value=1)
try:
    spi = SPI(1, baudrate=20_000_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
except Exception:
    spi = SoftSPI(baudrate=500_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
dc = Pin(21, Pin.OUT, value=0)
rst = Pin(7, Pin.OUT, value=1)
rst(0); time.sleep_ms(100); rst(1); time.sleep_ms(250)


def _cmd(command, data=None):
    dc(0)
    spi.write(bytes([command]))
    if data:
        dc(1)
        spi.write(data)


_cmd(0x11); time.sleep_ms(120)
_cmd(0x36, b"\x48")
_cmd(0x3A, b"\x55")
_cmd(0x29); time.sleep_ms(50)
_cmd(0x21)


def _window(x0, y0, x1, y1):
    _cmd(0x2A, bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
    _cmd(0x2B, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
    dc(0)
    spi.write(b"\x2C")


def rect(x, y, width, height, color):
    _window(x, y, x + width - 1, y + height - 1)
    high, low = color >> 8, color & 0xFF
    chunk = bytes([high, low] * 256)
    dc(1)
    pixels = width * height
    while pixels >= 256:
        spi.write(chunk)
        pixels -= 256
    if pixels:
        spi.write(bytes([high, low] * pixels))


_glyph = bytearray(8)
_glyph_buffer = framebuf.FrameBuffer(_glyph, 8, 8, framebuf.MONO_VLSB)


def text(x, y, value, fg, bg, scale=1):
    for character in value:
        _glyph_buffer.fill(0)
        _glyph_buffer.text(character, 0, 0, 1)
        char_width = 8 * scale
        _window(x, y, x + char_width - 1, y + char_width - 1)
        dc(1)
        fg_pixels = bytes([fg >> 8, fg & 0xFF]) * scale
        bg_pixels = bytes([bg >> 8, bg & 0xFF]) * scale
        row = bytearray(char_width * 2)
        step = scale * 2
        for row_index in range(8):
            position = 0
            mask = 1 << row_index
            for column in range(8):
                row[position:position + step] = fg_pixels if _glyph[column] & mask else bg_pixels
                position += step
            for _ in range(scale):
                spi.write(row)
        x += 9 * scale


def text_center(y, value, fg, bg, scale=1):
    width = len(value) * 9 * scale - scale
    text(max(0, (240 - width) // 2), y, value, fg, bg, scale)


BLACK = 0x0000
WHITE = 0xFFFF
GREEN = 0x07E0
RED = 0xF800
ORANGE = 0xFD20
YELLOW = 0xFFE0
GRAY = 0x8410


# --- Buzzer ------------------------------------------------------------------
try:
    if BUZZER_PASIVO:
        from machine import PWM
        buzzer = PWM(Pin(BUZZER_PIN), freq=2400, duty_u16=0)
    else:
        buzzer = Pin(BUZZER_PIN, Pin.OUT, value=0)
except Exception:
    buzzer = None


def beep(duration_ms, frequency=2400):
    if buzzer is None:
        return
    try:
        if BUZZER_PASIVO:
            buzzer.freq(frequency)
            buzzer.duty_u16(32768)
        else:
            buzzer(1)
        time.sleep_ms(duration_ms)
    finally:
        if buzzer is not None:
            if BUZZER_PASIVO:
                buzzer.duty_u16(0)
            else:
                buzzer(0)


def beep_ok():
    beep(60, 2093); time.sleep_ms(35); beep(80, 2637); time.sleep_ms(35); beep(180, 3136)


def beep_rechazo():
    beep(130, 1397); time.sleep_ms(80); beep(130, 1397)


def beep_error():
    for _ in range(3):
        beep(100, 1800)
        time.sleep_ms(80)


# El DB9 no se inicializa como salida todavia: un multiplexor no conectado no
# debe dejar lineas en estados arbitrarios. La definicion fija el pinout para
# cuando se implemente su protocolo.
db9_lines = [Pin(pin, Pin.IN) for pin in DB9_PINS]


def draw_idle():
    rect(0, 0, 240, 320, BLACK)
    text_center(35, "COJOsw", WHITE, BLACK, 4)
    text_center(88, "LECTOR PUESTO", ORANGE, BLACK, 2)
    text_center(138, "PASA TU TARJETA", WHITE, BLACK, 2)
    text_center(196, "NFC " + ("OK" if nfc_estado == "ok" else "NO RESPONDE"),
                GREEN if nfc_estado == "ok" else RED, BLACK, 1)
    text_center(218, "ID " + DEVICE_ID[-4:].upper(), GRAY, BLACK, 1)
    text_center(272, "WiFi " + wifi_ip if wifi_ip else "SIN WIFI",
                GREEN if wifi_ip else RED, BLACK, 1)
    text_center(294, "FW " + FW_VERSION, GRAY, BLACK, 1)


def draw_result(title, detail, color):
    rect(0, 0, 240, 320, BLACK)
    text_center(42, "LECTOR PUESTO", ORANGE, BLACK, 2)
    text_center(115, title, color, BLACK, 2)
    # Limitar longitud evita salirse de los 240 px con la fuente fija.
    text_center(165, (detail or "")[:25].upper(), WHITE, BLACK, 1)
    text_center(272, "PASA TU TARJETA", GRAY, BLACK, 1)


def conectar_wifi():
    global wifi_ip
    if network is None:
        return False
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        try:
            wlan.config(pm=network.WLAN.PM_NONE)
        except Exception:
            pass
        if STATIC_IP:
            wlan.ifconfig((STATIC_IP, SUBNET_MASK, GATEWAY, DNS))
        if not wlan.isconnected():
            wlan.connect(SSID, PASSWORD)
            for _ in range(24):
                if wlan.isconnected():
                    break
                time.sleep_ms(500)
        if wlan.isconnected():
            wifi_ip = wlan.ifconfig()[0]
            return True
    except Exception as error:
        print("WiFi:", error)
    wifi_ip = ""
    return False


def enviar_entrada(tag_uid):
    if socket is None:
        return None, None
    body = json.dumps({"tag_uid": tag_uid, "device_id": DEVICE_ID}).encode("utf-8")
    connection = None
    try:
        address = socket.getaddrinfo(HOST_IP, PORT, 0, socket.SOCK_STREAM)[0][-1]
        connection = socket.socket()
        connection.settimeout(12)
        connection.connect(address)
        request = ("POST %s HTTP/1.0\r\nHost: %s\r\nContent-Type: application/json\r\n"
                   "Content-Length: %d\r\nConnection: close\r\n\r\n" %
                   (ENTRADA_PATH, HOST_IP, len(body))).encode("utf-8")
        connection.write(request)
        connection.write(body)
        response = b""
        while True:
            chunk = connection.read(1024)
            if not chunk:
                break
            response += chunk
        head, raw_body = response.split(b"\r\n\r\n", 1)
        status = int(head.split(b" ")[1])
        return status, json.loads(raw_body)
    except Exception as error:
        print("POST entrada:", error)
        return None, None
    finally:
        try:
            if connection:
                connection.close()
        except Exception:
            pass


def registrar_dispositivo():
    """Actualiza el latido del lector en Admin sin depender del perfil DevKit."""
    if socket is None or not wifi_ip:
        return
    connection = None
    try:
        address = socket.getaddrinfo(HOST_IP, PORT, 0, socket.SOCK_STREAM)[0][-1]
        connection = socket.socket()
        connection.settimeout(8)
        connection.connect(address)
        path = "/api/esp32/rfid/firmware/version?id=%s&ip=%s&fw=%s" % (
            DEVICE_ID, wifi_ip, FW_VERSION)
        connection.write(("GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n" %
                          (path, HOST_IP)).encode("utf-8"))
        while connection.read(256):
            pass
    except Exception as error:
        print("Latido RFID:", error)
    finally:
        try:
            if connection:
                connection.close()
        except Exception:
            pass


def procesar_tarjeta(uid):
    print("Tarjeta:", uid)
    status, response = enviar_entrada(uid)
    if status == 200 and response and response.get("success"):
        nombre = response.get("operario_nombre") or "ENTRADA REGISTRADA"
        draw_result("ACCESO OK", nombre, GREEN)
        beep_ok()
    elif status and 400 <= status < 500:
        draw_result("ACCESO DENEGADO", (response or {}).get("error") or "REVISA TARJETA", RED)
        beep_rechazo()
    else:
        draw_result("ERROR TECNICO", "SIN CONEXION", YELLOW)
        beep_error()
    time.sleep_ms(1800)
    draw_idle()


nfc = PN532(sda=NFC_SDA_PIN, scl=NFC_SCL_PIN)
nfc_estado = "ok" if nfc.reiniciar() else "ko"
nfc_fallos = 0
ultimo_nfc = 0
uid_anterior = ""
uid_anterior_ts = 0
ultimo_wifi = 0
ultimo_latido = 0

beep(80)
conectar_wifi()
registrar_dispositivo()
draw_idle()

while True:
    try:
        now = time.ticks_ms()
        if not wifi_ip and time.ticks_diff(now, ultimo_wifi) > 10_000:
            ultimo_wifi = now
            conectar_wifi()
            registrar_dispositivo()
            draw_idle()

        if wifi_ip and time.ticks_diff(now, ultimo_latido) > 60_000:
            ultimo_latido = now
            registrar_dispositivo()

        if nfc_estado == "ko" and time.ticks_diff(now, ultimo_nfc) >= NFC_REINTENTO_S * 1000:
            ultimo_nfc = now
            nfc_estado = "ok" if nfc.reiniciar() else "ko"
            draw_idle()
        elif nfc_estado == "ok" and time.ticks_diff(now, ultimo_nfc) >= NFC_POLL_MS:
            ultimo_nfc = now
            uid = nfc.leer_uid(timeout_ms=80)
            if uid is None:
                nfc_fallos += 1
                if nfc_fallos >= NFC_FALLOS_MAX and not nfc.vivo():
                    nfc_fallos = 0
                    nfc_estado = "ko"
                    draw_idle()
            else:
                nfc_fallos = 0
                repetida = uid == uid_anterior and time.ticks_diff(now, uid_anterior_ts) < NFC_REPETIR_MS
                uid_anterior = uid
                uid_anterior_ts = now
                if not repetida:
                    procesar_tarjeta(uid)
    except Exception as error:
        print("Bucle:", error)
        time.sleep_ms(250)