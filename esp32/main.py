# main.py -- Placa lectora RFID de entrada a Engastado V3 (ESP32 DevKit V1
# Type-C + RC522). Se ejecuta despues de boot.py (que ya conecto el WiFi).
#
# Este fichero SI se actualiza por OTA (ver ota_update.py): sube la version
# aqui, publicalo con el deploy habitual del repo y la placa se autoactualiza
# sola en su siguiente comprobacion (arranque o periodica).
FW_VERSION = "2026-08-12a"

import time
from machine import Pin
from mfrc522 import MFRC522

import http_client
import ota_update
import wifi_config as cfg

HOST = cfg.BACKEND_HOST
PORT = cfg.BACKEND_PORT
USE_SSL = cfg.BACKEND_USE_SSL
ENTRADA_PATH = "/api/puestos/engastado_v3/entrada"

# ── Hardware ─────────────────────────────────────────────────────────────────
# MFRC522 crea su propio SPI interno (ver esp32/lib/mfrc522.py); solo hacen
# falta los pines.
rfid = MFRC522(cfg.SPI_CLK_PIN, cfg.SPI_MOSI_PIN, cfg.SPI_MISO_PIN,
               cfg.SPI_RST_PIN, cfg.SPI_CS_PIN)
buzzer = Pin(cfg.BUZZER_PIN, Pin.OUT)
led = Pin(cfg.LED_PIN, Pin.OUT)


def beep(times=1, duration_ms=100):
    for _ in range(times):
        buzzer.on()
        time.sleep_ms(duration_ms)
        buzzer.off()
        time.sleep_ms(50)


def uid_to_hex(uid):
    """UID (bytes) -> string hex, p.ej. 'A1B2C3D4'."""
    return "".join("%02X" % b for b in uid[:4])


def enviar_entrada(tag_uid):
    """POST del UID leido al backend. Beep segun resultado."""
    status, data = http_client.post_json(
        HOST, ENTRADA_PATH, {"tag_uid": tag_uid}, port=PORT, use_ssl=USE_SSL)

    if status == 200 and data and data.get("success"):
        print("OK:", data.get("operario_nombre"))
        beep(2, 100)
        led.on(); time.sleep(1); led.off()
        return True

    if status in (400, 404, 409):
        print("Rechazado (%s):" % status, (data or {}).get("error"))
        beep(1, 150)
        return False

    print("Error de red o servidor (status=%s)" % status)
    beep(5, 100)
    return False


def bucle_principal():
    print("Placa RFID Engastado V3 - version", FW_VERSION)
    print("Esperando lectura de tarjeta...")

    # Confirma que este main.py arranco bien: resetea el contador de fallos
    # que usa ota_update para decidir si hace rollback.
    ota_update.marcar_arranque_ok()

    last_scan_ms = 0
    last_ota_check_ms = time.ticks_ms()
    debounce = cfg.DEBOUNCE_MS
    ota_interval = getattr(cfg, "OTA_CHECK_INTERVAL_MS", None)

    while True:
        (stat, _tag_type) = rfid.request(rfid.REQIDL)
        if stat == rfid.OK:
            (stat, raw_uid) = rfid.anticoll()
            if stat == rfid.OK:
                now = time.ticks_ms()
                if time.ticks_diff(now, last_scan_ms) > debounce:
                    tag_uid = uid_to_hex(raw_uid)
                    print("Tarjeta detectada:", tag_uid)
                    enviar_entrada(tag_uid)
                    last_scan_ms = now
                rfid.select_tag(raw_uid)  # cierra el ciclo de seleccion del chip

        # Comprobacion periodica de OTA (ademas de la que ya hace boot.py al
        # arrancar). Si hay version nueva, check_and_apply() reinicia sola.
        if ota_interval:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_ota_check_ms) > ota_interval:
                last_ota_check_ms = now
                try:
                    ota_update.check_and_apply()
                except Exception as e:
                    print("OTA periodica fallo:", e)

        time.sleep_ms(150)


bucle_principal()
