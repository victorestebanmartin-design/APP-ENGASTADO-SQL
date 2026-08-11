"""Login por tarjeta con lector compartido en el carro."""


def _operario_con_tag(client, nombre, tag):
    op = client.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']
    client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': tag})
    return op


def _leer_tarjeta(client, carro, uid):
    """Simula la lectura del lector NFC del ESP32 (llega por GET)."""
    return client.get(f'/api/esp32/evento?tipo=tag&uid={uid}&carro={carro}')


def _solicitar(client, carro='7'):
    return client.post('/api/operarios/login/solicitar', json={'carro': carro})


def _estado(client, req_id):
    return client.post('/api/operarios/login/solicitar/estado',
                       json={'request_id': req_id}).get_json()


def test_solicitar_devuelve_codigo(client):
    d = _solicitar(client).get_json()
    assert d['success'] and d['request_id']
    assert len(d['codigo']) == 4 and d['codigo'].isdigit()


def test_solo_una_peticion_pendiente_por_carro(client):
    _solicitar(client, '7')
    r = _solicitar(client, '7')
    assert r.status_code == 409
    assert r.get_json().get('ocupado')


def test_otro_carro_no_bloquea(client):
    _solicitar(client, '7')
    assert _solicitar(client, '8').status_code == 200


def test_tarjeta_resuelve_login(client):
    _operario_con_tag(client, 'ANA', 'A1B2C3D4')
    req = _solicitar(client, '7').get_json()['request_id']
    _leer_tarjeta(client, '7', 'a1:b2:c3:d4')
    d = _estado(client, req)
    assert d['estado'] == 'resuelto'
    assert d['operario'] == 'ANA' and d['login_id']
    # Queda registrado como login activo del módulo
    logins = client.get('/api/operarios/logins').get_json()['logins']
    assert any(l['operario'] == 'ANA' for l in logins)


def test_tarjeta_desconocida_no_consume_peticion(client):
    req = _solicitar(client, '7').get_json()['request_id']
    _leer_tarjeta(client, '7', 'FFFFFFFF')
    assert _estado(client, req)['estado'] == 'pendiente'


def test_operario_ya_dentro_es_rechazado(client):
    _operario_con_tag(client, 'ANA', 'A1B2C3D4')
    # Ana entra en el carro 7
    req7 = _solicitar(client, '7').get_json()['request_id']
    _leer_tarjeta(client, '7', 'A1B2C3D4')
    assert _estado(client, req7)['estado'] == 'resuelto'
    # Intenta entrar también en el carro 8: rechazado
    req8 = _solicitar(client, '8').get_json()['request_id']
    _leer_tarjeta(client, '8', 'A1B2C3D4')
    d = _estado(client, req8)
    assert d['estado'] == 'rechazado' and d['error']


def test_banner_login_visible_para_pantalla(client):
    _solicitar(client, '7')
    d = client.get('/api/esp32/current?carro=7').get_json()
    assert d['login'] and d['login']['esperando']
    assert len(d['login']['codigo']) == 4


def test_cancelar_libera_el_carro(client):
    req = _solicitar(client, '7').get_json()['request_id']
    client.post('/api/operarios/login/solicitar/cancelar', json={'request_id': req})
    # El carro vuelve a admitir peticiones
    assert _solicitar(client, '7').status_code == 200
    assert client.get('/api/esp32/current?carro=7').get_json()['login'] is not None
