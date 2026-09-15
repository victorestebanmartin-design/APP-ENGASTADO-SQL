"""Tests del arranque local: no duplicar servidor y abrir la app a tiempo."""
import socket
import threading
import time

import arranque_local


def _puerto_escuchando():
    """Abre un socket real y devuelve (puerto, cerrar)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    s.listen(1)
    return s.getsockname()[1], s.close


def _puerto_libre():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


def test_puerto_ocupado_detecta_un_servidor_en_marcha():
    puerto, cerrar = _puerto_escuchando()
    try:
        assert arranque_local.puerto_ocupado(puerto) is True
    finally:
        cerrar()


def test_puerto_ocupado_es_falso_si_no_hay_nadie():
    assert arranque_local.puerto_ocupado(_puerto_libre()) is False


def test_esperar_puerto_se_rinde_y_no_se_queda_colgado():
    t0 = time.monotonic()
    assert arranque_local.esperar_puerto(_puerto_libre(), espera_max=1, intervalo=0.1) is False
    # Sin tope, el hilo que abre la app esperaria eternamente a un servidor
    # que no va a arrancar.
    assert time.monotonic() - t0 < 5


def test_esperar_puerto_vuelve_en_cuanto_el_servidor_responde():
    puerto = _puerto_libre()
    servidor = []

    def _levantar_tarde():
        time.sleep(0.6)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', puerto))
        s.listen(1)
        servidor.append(s)

    hilo = threading.Thread(target=_levantar_tarde)
    hilo.start()
    try:
        assert arranque_local.esperar_puerto(puerto, espera_max=10, intervalo=0.1) is True
    finally:
        hilo.join()
        for s in servidor:
            s.close()
