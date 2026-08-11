# launcher.py -> se sube como main.py (estable, NO se toca por OTA).
# Arranca la aplicacion (app.py) con autorrecuperacion: si app.py no arranca
# varias veces seguidas (p.ej. un OTA defectuoso que no compila), restaura la
# version anterior (app_prev.py) para que la pantalla nunca se quede muerta.
#
# El contador de fallos se pone a 0 desde app.py en cuanto entra en su bucle
# principal (eso prueba que el fichero carga bien); asi un corte de WiFi que
# reinicie la placa NO cuenta como fallo de arranque y no dispara un rollback.
import machine
import time

FAILS = "boot_fails.txt"
UMBRAL_ROLLBACK = 3


def _leer_fails():
    try:
        with open(FAILS) as f:
            return int((f.read() or "0").strip())
    except Exception:
        return 0


def _escribir_fails(v):
    try:
        with open(FAILS, "w") as f:
            f.write(str(v))
    except Exception:
        pass


_n = _leer_fails() + 1
_escribir_fails(_n)

if _n >= UMBRAL_ROLLBACK:
    # Varios arranques fallidos seguidos: volver a la version anterior.
    try:
        with open("app_prev.py") as f:
            _prev = f.read()
        with open("app.py", "w") as f:
            f.write(_prev)
        _escribir_fails(0)
        print("ROLLBACK: app.py restaurado desde app_prev.py")
    except OSError:
        pass

try:
    import app  # ejecuta la aplicacion (su bucle no retorna)
except Exception as e:
    # Fallo al cargar/arrancar app.py: reiniciar para reintentar (y, tras
    # varios intentos, el bloque de arriba hara el rollback).
    print("APP crash en arranque:", e)
    time.sleep(2)
    machine.reset()
