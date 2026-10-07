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


def _registrar_lector_online(app, device_id='lector1', fw='2026-10-07a'):
    with app.app_context():
        from app.routes.sistema import _rfid_registrar_dispositivo
        _rfid_registrar_dispositivo(device_id, fw=fw)


def test_captura_rfid_solo_se_entrega_al_lector_elegido(app, admin_client):
    op = _crear_operario(admin_client)
    _registrar_lector_online(app)
    inicio = admin_client.post(
        f'/api/operarios/{op["id"]}/rfid/captura', json={'device_id': 'lector1'})
    assert inicio.status_code == 200
    token = inicio.get_json()['token']

    assert admin_client.get(
        '/api/esp32/rfid/operario/captura?device_id=otrolector'
    ).get_json()['captura'] is None
    captura = admin_client.get(
        '/api/esp32/rfid/operario/captura?device_id=lector1').get_json()['captura']
    assert captura['token'] == token
    assert captura['operario'] == op['nombre']


def test_sondeo_pick_to_light_tambien_entrega_captura_operario(app, admin_client):
    op = _crear_operario(admin_client)
    _registrar_lector_online(app)
    inicio = admin_client.post(
        f'/api/operarios/{op["id"]}/rfid/captura', json={'device_id': 'lector1'}
    ).get_json()

    orden = admin_client.get(
        '/api/esp32/rfid/gaveta/orden?device_id=lector1').get_json()
    assert orden['operario_captura']['token'] == inicio['token']


def test_captura_rfid_guarda_uid_y_consume_token(app, admin_client):
    op = _crear_operario(admin_client)
    _registrar_lector_online(app)
    inicio = admin_client.post(
        f'/api/operarios/{op["id"]}/rfid/captura', json={'device_id': 'lector1'}
    ).get_json()

    equivocada = admin_client.post('/api/esp32/rfid/operario/captura', json={
        'device_id': 'otrolector', 'token': inicio['token'], 'uid': 'a1:b2:c3:d4',
    })
    assert equivocada.status_code == 409
    assert _buscar_operario(admin_client, op['id'])['tag_uid'] is None

    guardada = admin_client.post('/api/esp32/rfid/operario/captura', json={
        'device_id': 'lector1', 'token': inicio['token'], 'uid': 'a1:b2:c3:d4',
    })
    assert guardada.get_json() == {
        'success': True, 'uid': 'A1B2C3D4', 'operario': op['nombre']}
    assert _buscar_operario(admin_client, op['id'])['tag_uid'] == 'A1B2C3D4'
    assert admin_client.get(
        '/api/esp32/rfid/operario/captura?device_id=lector1'
    ).get_json()['captura'] is None


def test_captura_rfid_no_permite_uid_duplicado(app, admin_client):
    asignado = _crear_operario(admin_client, 'YA ASIGNADO')
    destino = _crear_operario(admin_client, 'DESTINO')
    admin_client.put(f'/api/operarios/{asignado["id"]}', json={'tag_uid': 'A1B2C3D4'})
    _registrar_lector_online(app)
    inicio = admin_client.post(
        f'/api/operarios/{destino["id"]}/rfid/captura', json={'device_id': 'lector1'}
    ).get_json()

    respuesta = admin_client.post('/api/esp32/rfid/operario/captura', json={
        'device_id': 'lector1', 'token': inicio['token'], 'uid': 'A1B2C3D4',
    })
    assert respuesta.status_code == 409
    assert _buscar_operario(admin_client, destino['id'])['tag_uid'] is None
    estado = admin_client.get(
        f'/api/operarios/{destino["id"]}/rfid/captura/{inicio["token"]}'
    ).get_json()
    assert estado['estado'] == 'error'
    assert 'YA ASIGNADO' in estado['mensaje']


def test_captura_rfid_rechaza_lector_con_firmware_antiguo(app, admin_client):
    op = _crear_operario(admin_client)
    _registrar_lector_online(app, fw='2026-10-06a')

    respuesta = admin_client.post(
        f'/api/operarios/{op["id"]}/rfid/captura', json={'device_id': 'lector1'})
    assert respuesta.status_code == 409
    assert 'firmware' in respuesta.get_json()['error'].lower()


def test_cancelar_captura_rfid_desarma_el_lector(app, admin_client):
    op = _crear_operario(admin_client)
    _registrar_lector_online(app)
    inicio = admin_client.post(
        f'/api/operarios/{op["id"]}/rfid/captura', json={'device_id': 'lector1'}
    ).get_json()

    cancelada = admin_client.delete(
        f'/api/operarios/{op["id"]}/rfid/captura/{inicio["token"]}'
    ).get_json()
    assert cancelada['estado'] == 'cancelada'
    assert admin_client.get(
        '/api/esp32/rfid/operario/captura?device_id=lector1'
    ).get_json()['captura'] is None
