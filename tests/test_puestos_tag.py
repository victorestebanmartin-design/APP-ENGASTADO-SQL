"""Normalización de UID de tarjeta NFC y captura de tarjetas nuevas (para Admin).

La tarjeta identifica al OPERARIO, no al puesto (ver tests/test_operarios_tag.py
para la asignación); aquí solo queda lo genérico: la función de normalización
y la ruta de captura /api/esp32/ultimo-tag que usa Admin → Operarios.

La captura SOLO viene de los lectores RFID dedicados de la entrada del puesto
(POST /api/puestos/engastado_v3/entrada) -- el lector NFC de la pantalla del
carro no contribuye a esto, solo identifica en modo trabajo para confirmar
recoger/devolver (ver tests/test_esp32_confirmacion.py).
"""
import pytest

from app.routes.puestos import normalizar_tag_uid


# ── Normalización del UID ─────────────────────────────────────────────────

@pytest.mark.parametrize('crudo,esperado', [
    ('a1b2c3d4', 'A1B2C3D4'),
    ('A1:B2:C3:D4', 'A1B2C3D4'),
    ('a1 b2 c3 d4', 'A1B2C3D4'),
    ('a1-b2-c3-d4', 'A1B2C3D4'),
    ('04A2B3C4D5E680', '04A2B3C4D5E680'),   # UID de 7 bytes (NTAG)
    ('', ''),
    (None, ''),
])
def test_normalizar_uid(crudo, esperado):
    assert normalizar_tag_uid(crudo) == esperado


@pytest.mark.parametrize('malo', [
    'ZZZZZZZZ',        # no es hex
    'A1B2C3',          # menos de 4 bytes
    'A1B2C3D',         # nº impar de dígitos
    'A' * 22,          # más de 10 bytes
])
def test_uid_invalido(malo):
    assert normalizar_tag_uid(malo) is None


# ── Alta desde el lector de la entrada (capturar tag) ─────────────────────

def test_tarjeta_no_reconocida_en_la_entrada_queda_disponible_para_admin(client, admin_client):
    """El lector de la entrada avisa del UID que no conoce; Admin lo recoge."""
    r = client.post('/api/puestos/engastado_v3/entrada',
                     json={'tag_uid': 'a1b2c3d4', 'device_id': 'lector1'})
    assert r.status_code == 404  # tarjeta no registrada como operario

    d = admin_client.get('/api/esp32/ultimo-tag').get_json()
    assert d['success']
    assert d['tag']['uid'] == 'A1B2C3D4'
    assert d['tag']['edad_s'] is not None and d['tag']['edad_s'] < 5


def test_ultimo_tag_vacio_si_no_hubo_lecturas(admin_client):
    assert admin_client.get('/api/esp32/ultimo-tag').get_json()['tag'] is None


def test_ultimo_tag_requiere_admin(client):
    assert client.get('/api/esp32/ultimo-tag').status_code == 401


def test_solo_se_guarda_la_ultima_tarjeta(client, admin_client):
    client.post('/api/puestos/engastado_v3/entrada', json={'tag_uid': 'AAAAAAAA'})
    client.post('/api/puestos/engastado_v3/entrada', json={'tag_uid': 'BBBBBBBB'})
    assert admin_client.get('/api/esp32/ultimo-tag').get_json()['tag']['uid'] == 'BBBBBBBB'


# ── El NFC del carro ya NO alta tarjetas ───────────────────────────────────

def test_tarjeta_leida_en_el_carro_no_alta_para_admin(client, admin_client):
    """El evento tipo=tag (lector del carro) ya no se usa para dar de alta
    tarjetas -- eso es cosa exclusiva del lector de la entrada (arriba)."""
    assert client.get('/api/esp32/evento?tipo=tag&uid=a1b2c3d4&id=aabbcc&carro=3').get_json()['success']
    assert admin_client.get('/api/esp32/ultimo-tag').get_json()['tag'] is None
