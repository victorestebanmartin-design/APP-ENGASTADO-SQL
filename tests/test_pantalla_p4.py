"""Grabar la pantalla grande (P4) desde Admin: compilar el .ino y subirlo.

Ningún test lanza arduino-cli: se sustituye pantalla_p4._ejecutar.
"""
import os

import pytest

from app import pantalla_p4

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def con_cli(monkeypatch):
    """arduino-cli 'instalado' y un registro de los comandos lanzados."""
    monkeypatch.setattr(pantalla_p4, 'buscar_arduino_cli', lambda: 'arduino-cli')
    monkeypatch.setattr(pantalla_p4, '_estado', {'fase': 'libre'})
    lanzados = []
    respuestas = {'compile': 0, 'upload': 0}

    def falso(comando, timeout, al_linea):
        lanzados.append(comando)
        al_linea(f'{comando[1]} simulado')
        return respuestas[comando[1]], False

    monkeypatch.setattr(pantalla_p4, '_ejecutar', falso)
    return lanzados, respuestas


def _esperar():
    if pantalla_p4._hilo:
        pantalla_p4._hilo.join(timeout=5)


def test_fqbn_sale_de_compilar_sh():
    """Una sola verdad: el mismo FQBN que usa compilar.sh a mano."""
    f = pantalla_p4.fqbn(BASE_DIR)
    assert f and f.startswith('esp32:esp32:esp32p4_4ds_mipi:')
    assert 'esp32p4_101ct_clb' in f


def test_version_del_banner():
    assert pantalla_p4.version_firmware(BASE_DIR).startswith('v')


def test_requiere_pin(client):
    assert client.get('/api/pantalla_p4/estado').status_code == 401
    assert client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6'}).status_code == 401


def test_rechaza_puerto_invalido(admin_client, con_cli):
    r = admin_client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6 & del *'})
    assert r.status_code == 400
    assert not con_cli[0]


def test_rechaza_variante_invalida(admin_client, con_cli):
    r = admin_client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6', 'variante': 'debug'})
    assert r.status_code == 400


def test_sin_arduino_cli_lo_dice(admin_client, monkeypatch):
    monkeypatch.setattr(pantalla_p4, 'buscar_arduino_cli', lambda: None)
    r = admin_client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6'})
    d = r.get_json()
    assert r.status_code == 200 and not d['success']
    assert 'arduino-cli' in d['message']
    assert admin_client.get('/api/pantalla_p4/estado').get_json()['disponible'] is False


def test_compila_y_sube(admin_client, con_cli, app):
    lanzados, _ = con_cli
    r = admin_client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6', 'variante': 'notouch'})
    assert r.get_json()['success']
    _esperar()

    assert [c[1] for c in lanzados] == ['compile', 'upload']
    compilar, subir = lanzados
    assert 'compiler.cpp.extra_flags=-DHAS_TOUCH=0' in compilar
    assert subir[subir.index('-p') + 1] == 'COM6'
    # La subida usa justo lo que acaba de compilar, y dentro de DATA_DIR.
    build = compilar[compilar.index('--build-path') + 1]
    assert subir[subir.index('--input-dir') + 1] == build
    assert build.startswith(app.config['DATA_DIR'])

    t = admin_client.get('/api/pantalla_p4/estado').get_json()['trabajo']
    assert t['fase'] == 'ok'
    assert 'upload simulado' in t['log']


def test_si_no_compila_no_toca_la_pantalla(admin_client, con_cli):
    lanzados, respuestas = con_cli
    respuestas['compile'] = 1
    admin_client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6'})
    _esperar()
    assert [c[1] for c in lanzados] == ['compile']
    t = admin_client.get('/api/pantalla_p4/estado').get_json()['trabajo']
    assert t['fase'] == 'error' and 'No compila' in t['mensaje']


def test_fallo_al_subir_da_consejo(admin_client, con_cli, monkeypatch):
    lanzados, respuestas = con_cli
    respuestas['upload'] = 2
    admin_client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6'})
    _esperar()
    t = admin_client.get('/api/pantalla_p4/estado').get_json()['trabajo']
    assert t['fase'] == 'error' and t.get('consejo')


def test_solo_compilar_no_sube_ni_pide_puerto(admin_client, con_cli):
    lanzados, _ = con_cli
    r = admin_client.post('/api/pantalla_p4/grabar', json={'solo_compilar': True})
    assert r.get_json()['success']
    _esperar()
    assert [c[1] for c in lanzados] == ['compile']


def test_una_grabacion_a_la_vez(admin_client, con_cli, monkeypatch):
    monkeypatch.setattr(pantalla_p4, '_estado', {'fase': 'compilando', 'log': []})
    r = admin_client.post('/api/pantalla_p4/grabar', json={'puerto': 'COM6'})
    assert r.status_code == 409
    assert not con_cli[0]


@pytest.mark.parametrize('salida, palabra', [
    ('could not open port COM6: PermissionError', 'cogido'),
    ('A fatal error occurred: Failed to connect to ESP32-P4', 'BOOT'),
])
def test_consejo_segun_error(salida, palabra):
    assert palabra in pantalla_p4._consejo_subida([salida])
