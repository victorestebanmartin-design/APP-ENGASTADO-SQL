# ota_update.py -- Actualizacion por WiFi de la placa lectora RFID (Engastado V3).
#
# Mismo patron que el OTA de la pantalla de carro (main_wifi.py): descarga y
# verifica TODO (tamano + sha256) antes de tocar nada; si algo falla a mitad,
# el firmware actual queda intacto. Solo actualiza main.py (+ ficheros que
# liste el manifiesto del servidor); este fichero, http_client.py, boot.py y
# wifi_config.py NUNCA se tocan por OTA -- se instalan una vez por USB, para
# que un OTA roto no pueda inutilizar el propio mecanismo de OTA.
#
# Uso desde boot.py (tras conectar el WiFi):
#   import ota_update
#   ota_update.rollback_si_procede()   # antes de que arranque main.py
#   ota_update.check_and_apply()       # si hay version nueva, la aplica y reinicia
#
# Uso desde main.py (dentro del bucle principal, una vez arrancado):
#   ota_update.marcar_arranque_ok()    # confirma que este main.py carga bien

import os
import machine

import http_client
import wifi_config as cfg

VERSION_FILE = "version.txt"
BOOT_FAILS_FILE = "boot_fails.txt"
FAIL_ROLLBACK_THRESHOLD = 3  # arranques fallidos seguidos antes de revertir

HOST = cfg.BACKEND_HOST
PORT = getattr(cfg, "BACKEND_PORT", 443)
USE_SSL = getattr(cfg, "BACKEND_USE_SSL", True)
VERSION_PATH = "/api/esp32/rfid/firmware/version"
FILE_PATH = "/api/esp32/rfid/firmware/file"


def _local_version():
    try:
        with open(VERSION_FILE) as f:
            return f.read().strip()
    except Exception:
        return ""


def _set_local_version(v):
    try:
        with open(VERSION_FILE, "w") as f:
            f.write(v)
    except Exception:
        pass


def _urlenc(s):
    out = ""
    for ch in str(s):
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch in "-_.":
            out += ch
        else:
            for b in ch.encode("utf-8"):
                out += "%%%02X" % b
    return out


def _sha256_hex(data):
    import uhashlib
    import ubinascii
    return ubinascii.hexlify(uhashlib.sha256(data).digest()).decode()


def marcar_arranque_ok():
    """Llamar al entrar en el bucle principal de main.py.

    Probar que el fichero carga y llega a su bucle es la prueba de que el
    arranque fue bien; asi un reinicio por corte de WiFi (que no llega a
    tocar main.py) no se confunde nunca con un OTA que no compila.
    """
    try:
        with open(BOOT_FAILS_FILE, "w") as f:
            f.write("0")
    except Exception:
        pass


def _registrar_fallo_arranque():
    try:
        with open(BOOT_FAILS_FILE) as f:
            n = int((f.read() or "0").strip())
    except Exception:
        n = 0
    n += 1
    try:
        with open(BOOT_FAILS_FILE, "w") as f:
            f.write(str(n))
    except Exception:
        pass
    return n


def rollback_si_procede():
    """Llamar desde boot.py, ANTES de que arranque main.py.

    Si main.py ha fallado varias veces seguidas en arrancar (un OTA que no
    compila, por ejemplo), restaura la copia anterior (main_prev.py) para que
    la placa nunca se quede muerta esperando una actualizacion manual.
    """
    n = _registrar_fallo_arranque()
    if n >= FAIL_ROLLBACK_THRESHOLD:
        try:
            with open("main_prev.py") as f:
                prev = f.read()
            with open("main.py", "w") as f:
                f.write(prev)
            with open(BOOT_FAILS_FILE, "w") as f:
                f.write("0")
            print("OTA: rollback aplicado (main_prev.py -> main.py)")
        except OSError:
            pass  # sin copia previa (primera instalacion): nada que revertir


def check_and_apply():
    """Comprueba la version publicada en el servidor y aplica el OTA si hay
    una nueva. Nunca lanza excepcion: cualquier fallo se registra por
    print() y se sigue con el firmware actual. Si aplica una actualizacion,
    reinicia la placa al terminar (no retorna en ese caso).

    Devuelve True si aplico una actualizacion (no debería observarse, porque
    resetea antes), False si no habia nada nuevo o algo fallo.
    """
    try:
        info = http_client.get_json(HOST, VERSION_PATH, port=PORT, use_ssl=USE_SSL)
    except Exception as e:
        print("OTA: no se pudo comprobar version:", e)
        return False
    if not info:
        print("OTA: sin respuesta del servidor")
        return False

    remoto = info.get("version") or ""
    files = info.get("files") or []
    if not remoto or not files:
        return False

    local = _local_version()
    if remoto == local:
        return False  # ya al dia

    print("OTA: version nueva disponible:", remoto, "(actual:", local or "ninguna", ")")

    descargados = {}
    for f in files:
        nombre = f.get("name")
        if not nombre:
            print("OTA: entrada de manifiesto sin nombre, aborto")
            return False
        data = http_client.get_bytes(
            HOST, FILE_PATH + "?name=" + _urlenc(nombre),
            port=PORT, use_ssl=USE_SSL, timeout=20)
        if data is None:
            print("OTA: fallo al descargar", nombre)
            return False
        size = f.get("size")
        if size is not None and len(data) != size:
            print("OTA: tamano no coincide en", nombre)
            return False
        sha = f.get("sha256")
        if sha and _sha256_hex(data) != sha:
            print("OTA: sha256 no coincide en", nombre)
            return False
        descargados[nombre] = data

    # Todo descargado y verificado: escribir a *.new antes de tocar nada real
    for nombre, data in descargados.items():
        try:
            with open(nombre + ".new", "wb") as fp:
                fp.write(data)
        except Exception as e:
            print("OTA: fallo al escribir", nombre, e)
            return False

    # Copia de seguridad del main.py actual, para el rollback de boot.py
    if "main.py" in descargados:
        try:
            with open("main.py", "rb") as fp:
                actual = fp.read()
            with open("main_prev.py", "wb") as fp:
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
            print("OTA: fallo al renombrar", nombre, e)
            return False

    _set_local_version(remoto)
    print("OTA: actualizado a", remoto, "- reiniciando")
    machine.reset()
