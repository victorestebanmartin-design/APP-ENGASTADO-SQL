# boot.py -- Arranque de la placa lectora RFID (Engastado V3). Se ejecuta
# SIEMPRE antes que main.py (convencion de MicroPython) y NUNCA se toca por
# OTA: conecta el WiFi, arranca WebREPL y lanza la comprobacion de
# actualizacion. Si algo de esto fallara, main.py sigue arrancando igual
# (todo va en try/except) para que la placa nunca se quede muerta.
#
# Solo se sube por USB, una vez (o cuando cambie esta logica base). Sube
# tambien wifi_config.py con tus credenciales reales ANTES de este fichero.

import time
import network

import wifi_config as cfg


def _conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        try:
            wlan.disconnect()
        except Exception:
            pass
        wlan.connect(cfg.SSID, cfg.PASSWORD)
        for _ in range(24):
            if wlan.isconnected():
                break
            time.sleep(0.5)
    return wlan.isconnected()


print("Conectando WiFi...")
conectado = _conectar_wifi()
if conectado:
    print("WiFi OK:", network.WLAN(network.STA_IF).ifconfig())
else:
    print("WiFi: no se pudo conectar (se sigue arrancando igual; main.py reintentara solo)")

# WebREPL: solo sirve desde redes que permitan salida al puerto 8266 (no la
# corporativa); util para depurar desde otro sitio. No afecta al OTA por
# HTTPS, que es independiente de esto.
try:
    import webrepl
    webrepl.start(password=cfg.WEBREPL_PASSWORD)
except Exception as e:
    print("WebREPL no arrancado:", e)

# OTA: si hay una version nueva publicada en el servidor, se aplica aqui,
# ANTES de que arranque main.py (asi la placa siempre entra en el bucle
# principal ya actualizada). rollback_si_procede() va primero: si el ultimo
# main.py fallo varias veces seguidas al arrancar, lo revierte.
if conectado:
    try:
        import ota_update
        ota_update.rollback_si_procede()
        ota_update.check_and_apply()  # si actualiza, reinicia la placa aqui mismo
    except Exception as e:
        print("OTA en arranque fallo (se sigue con el firmware actual):", e)
