"""Arranque en el PC de fabrica: un servidor solo, y la app en pantalla.

Esto vive en Python y no en el .vbs del icono por una razon concreta: la
directiva de IT de los PCs de la empresa BLOQUEA un script de Windows que
primero hace una peticion HTTP y luego lanza un proceso (es el patron clasico
de un dropper; el bloqueo salta con "This script is blocked by IT policy").
Asi que ARRANCAR.vbs se limita a lanzar run.bat, y todo lo que hay que decidir
-- si ya hay un servidor, cuando esta listo, cuando abrir la ventana -- se
decide aqui.
"""
import os
import socket
import subprocess
import threading
import time

# Que no parpadee una consola al abrir la app. Solo existe en Windows.
_SIN_VENTANA = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def puerto_ocupado(port, host='127.0.0.1', timeout=0.5):
    """¿Hay ya algo escuchando en ese puerto?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.settimeout(timeout)
        return sonda.connect_ex((host, port)) == 0


def esperar_puerto(port, espera_max=60, intervalo=0.5):
    """Espera a que el servidor acepte conexiones. Devuelve si llego a hacerlo.

    Se sondea el puerto en vez de esperar un numero fijo de segundos: en un PC
    lento el arranque tarda mas y abririamos la ventana contra un servidor que
    todavia no responde ("no se puede acceder a este sitio" nada mas arrancar,
    que es justo lo que hace dudar de si la app va o no va).
    """
    limite = time.monotonic() + espera_max
    while time.monotonic() < limite:
        if puerto_ocupado(port):
            return True
        time.sleep(intervalo)
    return False


def abrir_app(url, base_dir):
    """Abre la ventana de COJOsw (PWA instalada, Chrome/Edge o navegador)."""
    bat = os.path.join(base_dir, 'abrir_app.bat')
    try:
        subprocess.Popen(['cmd', '/c', bat, url],
                         cwd=base_dir, creationflags=_SIN_VENTANA)
        return True
    except OSError as e:
        # Quedarse sin ventana es una molestia (se abre a mano por la URL); no
        # es motivo para que el servidor no arranque.
        print(f"No se pudo abrir la ventana de la app: {e}")
        return False


def abrir_app_cuando_listo(port, url, base_dir, espera_max=60):
    """Abre la app en cuanto el servidor responda, sin bloquear el arranque.

    Daemon a proposito: el hilo principal se queda dentro de serve() y este no
    puede impedir que el proceso termine cuando toque apagarlo.
    """
    def _esperar():
        if esperar_puerto(port, espera_max):
            abrir_app(url, base_dir)
        else:
            print(f"El servidor no acepto conexiones en {espera_max}s: no se abre la app.")

    hilo = threading.Thread(target=_esperar, daemon=True)
    hilo.start()
    return hilo
