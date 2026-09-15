"""Tests del apagado del servidor desde el panel de administración.

`os._exit` se parchea SIEMPRE: sin eso, el primer test que llegue al hilo de
apagado mataría al propio pytest sin informe ni resto de la suite.
"""
import os
import threading

import servidor_pid
from app.routes.sistema import CODIGO_SALIDA_APAGADO


def _capturar_exit(monkeypatch):
    """Sustituye os._exit y devuelve (evento, códigos) para esperarlo."""
    llamado = threading.Event()
    codigos = []

    def _falso_exit(codigo):
        codigos.append(codigo)
        llamado.set()

    monkeypatch.setattr(os, '_exit', _falso_exit)
    return llamado, codigos


def test_apagar_sin_sesion_devuelve_401(client, monkeypatch):
    llamado, _ = _capturar_exit(monkeypatch)
    r = client.post('/api/apagar_servidor')
    assert r.status_code == 401
    assert not llamado.wait(2), 'un anónimo no puede apagar el servidor'


def test_apagar_responde_antes_de_salir_con_codigo_43(admin_client, monkeypatch):
    llamado, codigos = _capturar_exit(monkeypatch)

    r = admin_client.post('/api/apagar_servidor')

    # La respuesta llega ANTES de que el proceso muera: si no, el admin vería
    # un error de red y no sabría si se ha apagado.
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    assert not llamado.is_set()

    assert llamado.wait(5), 'el servidor no llegó a apagarse'
    assert codigos == [CODIGO_SALIDA_APAGADO]


def test_apagar_borra_el_fichero_de_pid(app, admin_client, monkeypatch):
    llamado, _ = _capturar_exit(monkeypatch)
    data_dir = app.config['DATA_DIR']
    servidor_pid.escribir(data_dir)
    assert os.path.exists(servidor_pid.ruta(data_dir))

    admin_client.post('/api/apagar_servidor')

    # detener.bat se guía por este fichero: dejarlo apuntando a un proceso
    # muerto haría que intentara matar un PID que ya no es el servidor.
    assert not os.path.exists(servidor_pid.ruta(data_dir))
    llamado.wait(5)


def test_pid_se_escribe_y_se_borra(tmp_path):
    data_dir = str(tmp_path / 'data')
    assert servidor_pid.escribir(data_dir)
    with open(servidor_pid.ruta(data_dir), encoding='utf-8') as f:
        assert f.read().strip() == str(os.getpid())
    assert servidor_pid.borrar(data_dir)
    assert not os.path.exists(servidor_pid.ruta(data_dir))
    # Borrar dos veces no revienta: el arranque puede encontrarlo ya limpio.
    assert not servidor_pid.borrar(data_dir)
