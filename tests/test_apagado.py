"""Tests del apagado del servidor desde el panel de administración.

`os._exit` se parchea SIEMPRE: sin eso, el primer test que llegue al hilo de
apagado mataría al propio pytest sin informe ni resto de la suite.
"""
import os
import threading

import pytest

import servidor_pid
from app.routes import sistema
from app.routes.sistema import CODIGO_SALIDA_APAGADO


@pytest.fixture(autouse=True)
def _apagado_rapido(monkeypatch):
    """El segundo de cortesia antes de morir no hace falta esperarlo aqui."""
    monkeypatch.setattr(sistema, 'ESPERA_APAGADO_S', 0.05)


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
    assert not llamado.wait(0.5), 'un anónimo no puede apagar el servidor'


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


# ── Reiniciar ────────────────────────────────────────────────────────────────

def test_reiniciar_sin_sesion_devuelve_401(client, monkeypatch):
    llamado, _ = _capturar_exit(monkeypatch)
    r = client.post('/api/reiniciar_servidor')
    assert r.status_code == 401
    assert not llamado.wait(0.5), 'un anónimo no puede reiniciar el servidor'


def test_reiniciar_responde_antes_de_salir_con_codigo_45(app, admin_client, monkeypatch):
    llamado, codigos = _capturar_exit(monkeypatch)
    data_dir = app.config['DATA_DIR']
    servidor_pid.escribir(data_dir)

    r = admin_client.post('/api/reiniciar_servidor')

    assert r.status_code == 200
    assert r.get_json()['success'] is True
    assert not llamado.is_set()
    # El proceso nuevo escribe el suyo; el viejo no puede dejar el de un muerto.
    assert not os.path.exists(servidor_pid.ruta(data_dir))

    assert llamado.wait(5), 'el servidor no llegó a reiniciarse'
    assert codigos == [sistema.CODIGO_SALIDA_REINICIO]
    # Ni el código de apagar (no relanza) ni el de la OTA (dice otra cosa en el log).
    assert sistema.CODIGO_SALIDA_REINICIO not in (CODIGO_SALIDA_APAGADO, 42)


def test_run_bat_relanza_con_el_codigo_de_reinicio():
    ruta = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'run.bat')
    with open(ruta, encoding='utf-8', errors='replace') as f:
        bat = f.read()
    codigo = sistema.CODIGO_SALIDA_REINICIO
    bloque = bat.split(f'if !EXIT_CODE! == {codigo} (', 1)
    assert len(bloque) == 2, f'run.bat no trata el código {codigo}'
    assert 'goto INICIO' in bloque[1].split(')', 1)[0]
