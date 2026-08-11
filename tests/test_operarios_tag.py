"""Tarjeta NFC por operario: identidad para el login y las confirmaciones."""


def _crear_operario(client, nombre='OPERARIO TAG'):
    return client.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']


def _buscar_operario(client, op_id):
    ops = client.get('/api/operarios').get_json()['operarios']
    return next(o for o in ops if o['id'] == op_id)


def test_operarios_nacen_sin_tarjeta(client):
    op = _crear_operario(client)
    assert _buscar_operario(client, op['id']).get('tag_uid') is None


def test_asignar_tarjeta_normaliza_uid(client):
    op = _crear_operario(client)
    r = client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': 'a1:b2:c3:d4'})
    assert r.get_json()['success']
    assert _buscar_operario(client, op['id'])['tag_uid'] == 'A1B2C3D4'


def test_quitar_tarjeta(client):
    op = _crear_operario(client)
    client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': 'A1B2C3D4'})
    assert client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': None}).get_json()['success']
    assert _buscar_operario(client, op['id'])['tag_uid'] is None


def test_uid_invalido_rechazado(client):
    op = _crear_operario(client)
    r = client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': 'ZZZZ'})
    assert r.status_code == 400
    assert not r.get_json()['success']


def test_tarjeta_duplicada_rechazada(client):
    a = _crear_operario(client, 'OPERARIO A')
    b = _crear_operario(client, 'OPERARIO B')
    client.put(f'/api/operarios/{a["id"]}', json={'tag_uid': 'A1B2C3D4'})
    r = client.put(f'/api/operarios/{b["id"]}', json={'tag_uid': 'A1B2C3D4'})
    assert r.status_code == 409
    assert not r.get_json()['success']


def test_cambiar_nombre_conserva_tarjeta(client):
    op = _crear_operario(client)
    client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': 'A1B2C3D4'})
    client.put(f'/api/operarios/{op["id"]}', json={'nombre': 'NUEVO NOMBRE'})
    fila = _buscar_operario(client, op['id'])
    assert fila['nombre'] == 'NUEVO NOMBRE'
    assert fila['tag_uid'] == 'A1B2C3D4'
