"""PID del proceso que sirve la app, escrito en disco.

En modo silencioso (`ARRANCAR.vbs`) no hay ventana de consola que cerrar
ni Ctrl+C que pulsar: si la web deja de responder y hay que parar el servidor,
lo unico que queda es el Administrador de tareas -- donde hay que adivinar cual
de los `python.exe` es. Con el PID en un fichero, `detener.bat` lo hace solo.

Nunca lanza: quedarse sin fichero de PID es una molestia, no un motivo para que
la planta se quede sin app.
"""
import os

NOMBRE = 'server.pid'


def ruta(data_dir):
    return os.path.join(data_dir, NOMBRE)


def escribir(data_dir):
    """Deja el PID de este proceso en data/server.pid. Devuelve si pudo."""
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(ruta(data_dir), 'w', encoding='utf-8') as f:
            f.write(str(os.getpid()))
        return True
    except OSError:
        return False


def borrar(data_dir):
    """Quita el fichero de PID. Devuelve si pudo."""
    try:
        os.remove(ruta(data_dir))
        return True
    except OSError:
        return False
