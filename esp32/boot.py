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


def _aplicar_ip_fija(wlan):
    """Fija la IP de esta placa ANTES de conectar (la red no tiene DHCP).

    Sin esto la placa se queda esperando una direccion que nadie reparte y
    no llega al servidor. Si cfg.STATIC_IP esta vacio se deja el DHCP, que
    es lo que quiere una red de pruebas que si lo tenga.
    """
    if not getattr(cfg, "STATIC_IP", ""):
        return
    try:
        wlan.ifconfig((cfg.STATIC_IP,
                       getattr(cfg, "SUBNET_MASK", "255.255.255.0"),
                       getattr(cfg, "GATEWAY", "192.168.50.5"),
                       getattr(cfg, "DNS", "192.168.50.5")))
    except Exception as e:
        print("IP fija no aplicada:", e)


def _desactivar_ahorro_energia(wlan):
    """Sin ahorro de energia: la latencia manda sobre el consumo.

    Por defecto MicroPython deja el ESP32 en WIFI_PS_MIN_MODEM, con la radio
    durmiendo entre balizas del punto de acceso. Mientras duerme, el AP le
    RETIENE los paquetes, asi que cada respuesta del servidor espera a la
    siguiente baliza: cientos de ms, a veces segundos. En un lector que tiene
    que confirmar una tarjeta al instante eso se nota mucho, y el servidor no
    tiene la culpa (responde en menos de 1 ms).
    """
    try:
        wlan.config(pm=network.WLAN.PM_NONE)
    except Exception as e:
        print("Ahorro de energia WiFi no desactivado:", e)


def _conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    _desactivar_ahorro_energia(wlan)
    _aplicar_ip_fija(wlan)
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

# WebREPL: consola de Python remota (puerto 8266) para depurar la placa por
# WiFi en vez de con el cable USB. Es opcional y viene APAGADO: dejar un
# servicio abierto en cada placa que nadie usa no aporta nada. Para activarlo
# en una placa concreta, pon una contrasena en WEBREPL_PASSWORD de su
# wifi_config.py y vuelve a subirlo por USB. No afecta al OTA, que es
# independiente de esto.
if getattr(cfg, "WEBREPL_PASSWORD", ""):
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
