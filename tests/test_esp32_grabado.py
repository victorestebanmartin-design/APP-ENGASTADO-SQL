"""Tests del grabado de MicroPython y los drivers USB (Admin -> ESP32).

Cubren sobre todo que no se pueda grabar algo inseguro: rutas fuera de las
carpetas de firmware, offsets de flash equivocados (que dejarían la placa sin
arrancar) y puertos con caracteres raros.
"""
import io
import os

import pytest

from app.routes.sistema import (
    _OFFSET_POR_CHIP,
    _chip_desde_binario,
    _chip_desde_nombre,
    _ruta_firmware_segura,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_FIRMWARE = os.path.join(BASE_DIR, 'esp32', 'firmware')


def _imagen_esp(chip_id, relleno=1024):
    """Una imagen ESP mínima: magic 0xE9 y el chip_id en los bytes 12-13."""
    cab = bytearray(b'\x00' * 16)
    cab[0] = 0xE9
    cab[12:14] = chip_id.to_bytes(2, 'little')
    return bytes(cab) + b'\x00' * relleno


# ---------------------------------------------------------------- deducción de chip

@pytest.mark.parametrize('nombre, esperado', [
    ('ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin', 'esp32s3'),
    ('ESP32_GENERIC_S3-20260406-v1.28.0.bin',            'esp32s3'),
    ('ESP32_GENERIC-20260406-v1.28.0.bin',               'esp32'),
    ('ESP32_GENERIC_C3-20260406-v1.28.0.bin',            'esp32c3'),
    ('ESP32_GENERIC_S2-20260406-v1.28.0.bin',            'esp32s2'),
    ('cualquier_cosa.bin',                                None),
])
def test_chip_desde_nombre(nombre, esperado):
    assert _chip_desde_nombre(nombre) == esperado


def test_offset_correcto_por_chip():
    """El ESP32 clásico va en 0x1000 y los S3/C3 en 0x0.

    Grabar en el offset equivocado deja la placa sin arrancar, así que esto
    se fija explícitamente en un test.
    """
    assert _OFFSET_POR_CHIP['esp32'] == '0x1000'
    assert _OFFSET_POR_CHIP['esp32s3'] == '0x0'
    assert _OFFSET_POR_CHIP['esp32c3'] == '0x0'


# ---------------------------------------------------------------- chip desde la cabecera

@pytest.mark.parametrize('fichero, esperado', [
    ('ESP32_GENERIC-20260406-v1.28.0.bin',               'esp32'),
    ('ESP32_GENERIC_S3-20260406-v1.28.0.bin',            'esp32s3'),
    ('ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin', 'esp32s3'),
])
def test_chip_de_los_firmwares_del_repo(fichero, esperado):
    """Los .bin versionados se identifican por su cabecera, no por su nombre."""
    ruta = os.path.join(DIR_FIRMWARE, fichero)
    if not os.path.exists(ruta):
        pytest.skip(f'{fichero} no está en el repo')
    assert _chip_desde_binario(ruta) == esperado


def test_chip_desde_binario_ignora_el_nombre(tmp_path):
    """Un .bin mal etiquetado se identifica por su cabecera, no por su nombre.

    Caso real: alguien renombra o confunde el fichero del ESP32 clásico con
    el del S3. El nombre dice S3, la cabecera dice clásico, y manda la cabecera.
    """
    ruta = tmp_path / 'ESP32_GENERIC_S3-mal-etiquetado.bin'
    ruta.write_bytes(_imagen_esp(0x0000))               # cabecera de ESP32 clásico
    assert _chip_desde_nombre(ruta.name) == 'esp32s3'   # el nombre engaña
    assert _chip_desde_binario(str(ruta)) == 'esp32'    # la cabecera acierta


def test_chip_desde_binario_rechaza_no_imagen(tmp_path):
    ruta = tmp_path / 'basura.bin'
    ruta.write_bytes(b'esto no es una imagen ESP')
    assert _chip_desde_binario(str(ruta)) is None


# ---------------------------------------------------------------- ruta segura

def test_ruta_firmware_rechaza_traversal(app):
    with app.app_context():
        assert _ruta_firmware_segura('../../etc/passwd') is None
        assert _ruta_firmware_segura('../secreto.bin') is None
        assert _ruta_firmware_segura('') is None
        assert _ruta_firmware_segura('no_es_bin.txt') is None


def test_ruta_firmware_acepta_fichero_real(app):
    with app.app_context():
        carpeta = os.path.join(app.config['DATA_DIR'], 'firmware')
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, 'ESP32_GENERIC-v1.bin'), 'wb') as f:
            f.write(b'\x00' * 1024)
        assert _ruta_firmware_segura('ESP32_GENERIC-v1.bin') is not None


# ---------------------------------------------------------------- endpoints

def test_firmwares_requiere_pin(client):
    assert client.get('/api/esp32/firmwares').status_code == 401


def test_grabar_requiere_pin(client):
    r = client.post('/api/esp32/grabar_micropython',
                    json={'puerto': 'COM3', 'firmware': 'x.bin'})
    assert r.status_code == 401


def test_grabar_rechaza_puerto_invalido(admin_client):
    r = admin_client.post('/api/esp32/grabar_micropython',
                          json={'puerto': 'COM3; rm -rf /', 'firmware': 'x.bin'})
    assert r.status_code == 400
    assert 'Puerto no válido' in r.get_json()['message']


def test_grabar_rechaza_firmware_inexistente(admin_client):
    r = admin_client.post('/api/esp32/grabar_micropython',
                          json={'puerto': 'COM3', 'firmware': 'no_existe.bin'})
    assert r.status_code == 400
    assert not r.get_json()['success']


def test_grabar_rechaza_chip_desconocido(admin_client, app):
    """Un .bin que no es una imagen ESP no se graba a ciegas."""
    carpeta = os.path.join(app.config['DATA_DIR'], 'firmware')
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, 'raro.bin'), 'wb') as f:
        f.write(b'no soy una imagen ESP' * 100)

    r = admin_client.post('/api/esp32/grabar_micropython',
                          json={'puerto': 'COM3', 'firmware': 'raro.bin'})
    assert r.status_code == 400
    assert 'chip' in r.get_json()['message'].lower()


def test_grabar_rechaza_chip_que_no_coincide_con_el_binario(admin_client, app):
    """La protección que evita ladrillos: pedir un chip distinto al del .bin.

    Grabar una imagen de ESP32 clásico como si fuera S3 la escribiría en el
    offset 0x0 en vez de 0x1000 y la placa no arrancaría.
    """
    carpeta = os.path.join(app.config['DATA_DIR'], 'firmware')
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, 'clasico.bin'), 'wb') as f:
        f.write(_imagen_esp(0x0000))          # ESP32 clásico

    r = admin_client.post('/api/esp32/grabar_micropython',
                          json={'puerto': 'COM3', 'firmware': 'clasico.bin', 'chip': 'esp32s3'})
    assert r.status_code == 400
    msg = r.get_json()['message']
    assert 'esp32' in msg and 'esp32s3' in msg
    assert 'sin arrancar' in msg


def test_subir_firmware_rechaza_extension(admin_client):
    r = admin_client.post('/api/esp32/firmwares',
                          data={'firmware': (io.BytesIO(b'x' * 100), 'virus.exe')},
                          content_type='multipart/form-data')
    assert r.status_code == 400
    assert '.bin' in r.get_json()['message']


def test_subir_firmware_rechaza_fichero_diminuto(admin_client):
    """Una página de error HTML guardada por error no debe colarse como firmware."""
    r = admin_client.post('/api/esp32/firmwares',
                          data={'firmware': (io.BytesIO(b'<html>404</html>'), 'ESP32_GENERIC.bin')},
                          content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'no parece un firmware' in r.get_json()['message']


def test_subir_firmware_valido(admin_client, app):
    r = admin_client.post('/api/esp32/firmwares',
                          data={'firmware': (io.BytesIO(b'\x00' * (128 * 1024)),
                                             'ESP32_GENERIC-20260406-v1.28.0.bin')},
                          content_type='multipart/form-data')
    assert r.status_code == 200
    d = r.get_json()
    assert d['success']
    nombres = [f['nombre'] for f in d['firmwares']]
    assert 'ESP32_GENERIC-20260406-v1.28.0.bin' in nombres
    # Y se le ha deducido el chip y el offset correctos
    fw = next(f for f in d['firmwares'] if f['nombre'] == 'ESP32_GENERIC-20260406-v1.28.0.bin')
    assert fw['chip'] == 'esp32'
    assert fw['offset'] == '0x1000'


def test_firmwares_versionados_explican_el_modelo(admin_client):
    d = admin_client.get('/api/esp32/firmwares').get_json()
    modelos = {firmware['nombre']: firmware['modelo'] for firmware in d['firmwares']}
    assert modelos['ESP32_GENERIC-20260406-v1.28.0.bin'] == 'Lector RFID - ESP32 DevKit + RC522'
    assert modelos['ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin'] == 'Pantalla gen4-ESP32-24'


def test_subir_firmware_traversal_en_nombre(admin_client, app, tmp_path):
    """secure_filename debe impedir que el .bin salga de data/firmware/."""
    centinela = os.path.join(os.path.dirname(app.config['DATA_DIR']), 'escapado.bin')
    admin_client.post('/api/esp32/firmwares',
                      data={'firmware': (io.BytesIO(b'\x00' * (128 * 1024)), '../escapado.bin')},
                      content_type='multipart/form-data')
    assert not os.path.exists(centinela)


# ---------------------------------------------------------------- drivers

def test_drivers_requiere_pin(client):
    assert client.get('/api/esp32/drivers/estado').status_code == 401


def test_drivers_estado_fuera_de_windows(admin_client):
    """En Linux (PythonAnywhere) responde sin romper, avisando de que no aplica."""
    d = admin_client.get('/api/esp32/drivers/estado').get_json()
    assert d['success']
    if not d['windows']:
        assert 'aviso' in d
        assert d['dispositivos'] == []


def test_driver_instalar_rechaza_desconocido(admin_client):
    r = admin_client.post('/api/esp32/drivers/instalar', json={'driver': 'inventado'})
    assert r.status_code == 400


def test_subir_driver_rechaza_nombre_no_reconocido(admin_client):
    r = admin_client.post('/api/esp32/drivers/subir',
                          data={'driver': (io.BytesIO(b'x' * 100), 'cualquiera.exe')},
                          content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'no se reconoce' in r.get_json()['message'].lower()


def test_subir_driver_valido(admin_client, app):
    r = admin_client.post('/api/esp32/drivers/subir',
                          data={'driver': (io.BytesIO(b'x' * 100), 'CH341SER.EXE')},
                          content_type='multipart/form-data')
    assert r.status_code == 200
    assert r.get_json()['success']
    assert os.path.exists(os.path.join(app.config['DATA_DIR'], 'drivers', 'CH341SER.EXE'))
