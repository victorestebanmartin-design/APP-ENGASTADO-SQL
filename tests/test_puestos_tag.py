"""Tarjeta NFC por puesto: alternativa al pulsador de la pantalla del carro."""
import pytest

from app.routes.puestos import normalizar_tag_uid


def _un_puesto(client, n=0):
    return client.get('/api/puestos').get_json()['puestos'][n]


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


# ── Asignación ────────────────────────────────────────────────────────────

def test_puestos_nacen_sin_tarjeta(client):
    assert _un_puesto(client).get('tag_uid') is None


def test_asignar_tarjeta(admin_client, client):
    p = _un_puesto(client)
    r = admin_client.put(f'/api/puestos/{p["id"]}', json={'tag_uid': 'a1:b2:c3:d4'})
    assert r.get_json()['success'], r.get_json()

    # Se guarda normalizado
    assert next(x for x in client.get('/api/puestos').get_json()['puestos']
                if x['id'] == p['id'])['tag_uid'] == 'A1B2C3D4'


def test_quitar_la_tarjeta(admin_client, client):
    p = _un_puesto(client)
    admin_client.put(f'/api/puestos/{p["id"]}', json={'tag_uid': 'A1B2C3D4'})
    assert admin_client.put(f'/api/puestos/{p["id"]}', json={'tag_uid': None}).get_json()['success']

    assert next(x for x in client.get('/api/puestos').get_json()['puestos']
                if x['id'] == p['id'])['tag_uid'] is None


def test_una_tarjeta_no_puede_estar_en_dos_puestos(admin_client, client):
    puestos = client.get('/api/puestos').get_json()['puestos']
    a, b = puestos[0], puestos[1]

    assert admin_client.put(f'/api/puestos/{a["id"]}', json={'tag_uid': 'A1B2C3D4'}).get_json()['success']

    # Da igual el formato en el que se escriba: es la misma tarjeta
    r = admin_client.put(f'/api/puestos/{b["id"]}', json={'tag_uid': 'a1:b2:c3:d4'})
    assert r.status_code == 409
    assert a['nombre'] in r.get_json()['message']


def test_uid_invalido_da_400(admin_client, client):
    p = _un_puesto(client)
    assert admin_client.put(f'/api/puestos/{p["id"]}', json={'tag_uid': 'NOSOYHEX'}).status_code == 400


def test_un_puesto_puede_tener_boton_y_tarjeta(admin_client, client):
    p = _un_puesto(client)
    assert admin_client.put(f'/api/puestos/{p["id"]}',
                            json={'boton': 2, 'tag_uid': 'A1B2C3D4'}).get_json()['success']
    actual = next(x for x in client.get('/api/puestos').get_json()['puestos']
                  if x['id'] == p['id'])
    assert actual['boton'] == 2
    assert actual['tag_uid'] == 'A1B2C3D4'


def test_asignar_tarjeta_requiere_admin(client):
    p = _un_puesto(client)
    assert client.put(f'/api/puestos/{p["id"]}', json={'tag_uid': 'A1B2C3D4'}).status_code == 401


# ── Alta desde el carro (capturar tag) ────────────────────────────────────

def test_tarjeta_no_reconocida_queda_disponible_para_admin(client, admin_client):
    """La pantalla avisa del UID que no conoce; Admin lo recoge para asignarlo."""
    assert client.get('/api/esp32/evento?tipo=tag&uid=a1b2c3d4&id=aabbcc&carro=3').get_json()['success']

    d = admin_client.get('/api/esp32/ultimo-tag').get_json()
    assert d['success']
    assert d['tag']['uid'] == 'A1B2C3D4'
    assert d['tag']['carro'] == '3'
    assert d['tag']['edad_s'] is not None and d['tag']['edad_s'] < 5


def test_ultimo_tag_vacio_si_no_hubo_lecturas(admin_client):
    assert admin_client.get('/api/esp32/ultimo-tag').get_json()['tag'] is None


def test_ultimo_tag_requiere_admin(client):
    assert client.get('/api/esp32/ultimo-tag').status_code == 401


def test_solo_se_guarda_la_ultima_tarjeta(client, admin_client):
    client.get('/api/esp32/evento?tipo=tag&uid=AAAAAAAA')
    client.get('/api/esp32/evento?tipo=tag&uid=BBBBBBBB')
    assert admin_client.get('/api/esp32/ultimo-tag').get_json()['tag']['uid'] == 'BBBBBBBB'
