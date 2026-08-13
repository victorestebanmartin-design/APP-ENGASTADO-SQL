"""El NFC del carro deja de servir para entrar al módulo (login): solo
identifica, ya dentro y en modo trabajo, para confirmar recogidas/devoluciones
-- igual que el botón de puesto. Entrar al módulo es cosa del lector RFID
dedicado de la entrada (ver test_gate_operario.py) o de la selección manual.
"""


def _operario_con_tag(client, nombre, tag):
    op = client.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']
    client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': tag})
    return op


def test_tarjeta_en_el_carro_no_crea_ningun_login(client):
    """Pasar la tarjeta en el carro (fuera de modo trabajo) ya no autentica:
    solo queda registrada como 'última tarjeta vista' para Admin."""
    _operario_con_tag(client, 'ANA', 'A1B2C3D4')
    r = client.get('/api/esp32/evento?tipo=tag&uid=A1B2C3D4&carro=7')
    assert r.get_json()['success']
    assert 'login' not in r.get_json()

    assert client.get('/api/operarios/logins').get_json()['logins'] == []

    tag = client.get('/api/esp32/ultimo-tag')
    # requiere admin normalmente, pero comprobamos que no rompe el evento
    assert tag.status_code in (200, 401)


def test_current_ya_no_expone_banner_de_login(client):
    d = client.get('/api/esp32/current?carro=7').get_json()
    assert 'login' not in d


def test_endpoints_de_login_por_tarjeta_ya_no_existen(client):
    assert client.post('/api/operarios/login/solicitar', json={'carro': '7'}).status_code == 404
    assert client.post('/api/operarios/login/solicitar/estado', json={'request_id': 'x'}).status_code == 404
    assert client.post('/api/operarios/login/solicitar/cancelar', json={'request_id': 'x'}).status_code == 404
    assert client.get('/api/esp32/lectores').status_code == 404
