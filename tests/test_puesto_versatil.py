"""Puestos versatiles: el boton de flechas de la pantalla de login pasa un
puesto de engastado a manguitos y mangueras, y vuelta.

El modo se guarda en el puesto (BD), no en el navegador: quien decide a donde
va una tarjeta es el servidor al leer el lector, y el PC y su lector tienen
que estar de acuerdo.
"""
from conftest import admin_de

IP_PUESTO = '10.0.0.30'
IP_MANGUITOS = '10.0.0.31'
COMPARTIDO = 'manguitos_mangueras'


def _puesto(app, admin_client, nombre='MECATRACTION'):
    puesto = admin_client.post('/api/puestos', json={'nombre': nombre}).get_json()['puesto']
    pc = app.test_client()
    pc.environ_base['REMOTE_ADDR'] = IP_PUESTO
    assert pc.post('/api/pc/configurar',
                   json={'modulo': 'engastado', 'puesto_id': puesto['id']}).get_json()['success']
    assert admin_client.post('/api/esp32/rfid/devices/lectorP',
                             json={'puesto_id': puesto['id']}).get_json()['success']
    return puesto, pc


def _operario(client, nombre, uid, modulos=None):
    admin = admin_de(client)
    op = admin.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']
    datos = {'tag_uid': uid}
    if modulos is not None:
        datos['modulos_permitidos'] = modulos
    admin.put(f"/api/operarios/{op['id']}", json=datos)


def _pasar(cliente, uid, device_id='lectorP'):
    return cliente.post('/api/puestos/engastado_v3/entrada',
                        json={'tag_uid': uid, 'device_id': device_id})


def _cambiar(pc, modo=None):
    return pc.post('/api/puesto/pc/modo', json={'modo': modo} if modo else {})


def test_el_boton_alterna_y_el_modo_se_queda(app, admin_client):
    puesto, pc = _puesto(app, admin_client)
    assert pc.get('/api/pc').get_json()['modulo'] == 'engastado'

    r = _cambiar(pc)
    assert r.status_code == 200
    assert r.get_json()['modo'] == COMPARTIDO
    ident = pc.get('/api/pc').get_json()
    assert ident['modulo'] == COMPARTIDO
    # Sigue siendo el mismo puesto
    assert ident['puesto_id'] == puesto['id']

    # Otro navegador del mismo PC (misma IP) lo ve igual: vive en la BD
    otro = app.test_client()
    otro.environ_base['REMOTE_ADDR'] = IP_PUESTO
    assert otro.get('/api/pc').get_json()['modulo'] == COMPARTIDO

    assert _cambiar(pc).get_json()['modo'] == 'engastado'
    assert pc.get('/api/pc').get_json()['modulo'] == 'engastado'


def test_no_hace_falta_pin(app, admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    _, pc = _puesto(app, admin_client)
    assert _cambiar(pc).status_code == 200


def test_un_pc_sin_puesto_no_tiene_modo(app):
    pc = app.test_client()
    pc.environ_base['REMOTE_ADDR'] = IP_MANGUITOS
    pc.post('/api/pc/configurar', json={'modulo': COMPARTIDO})
    assert _cambiar(pc).status_code == 400


def test_modo_no_valido(app, admin_client):
    _, pc = _puesto(app, admin_client)
    assert _cambiar(pc, 'servidor').status_code == 400


def test_la_tarjeta_en_modo_manguitos_entra_en_manguitos(app, client, admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    puesto, pc = _puesto(app, admin_client)
    _operario(client, 'Ana', 'AABBCCDD', ['manguitos', 'mangueras'])
    _cambiar(pc)

    r = _pasar(pc, 'AABBCCDD')
    assert r.status_code == 200
    login_id = r.get_json()['login_id']

    # El PC del puesto lo ve por su puesto_id, como siempre
    logins = pc.get(f"/api/operarios/logins?puesto_id={puesto['id']}").get_json()['logins']
    assert [l['operario'] for l in logins] == ['Ana']
    assert logins[0]['modulo'] == COMPARTIDO

    adoptado = pc.post('/api/sesion/operario/adoptar', json={'login_id': login_id}).get_json()
    assert adoptado['permitido'] is True
    # Y entra en la rejilla de manguitos y mangueras, no en engastado
    rejilla = pc.get('/modules')
    assert rejilla.status_code == 200


def test_sin_permiso_de_manguitos_rechaza_con_consejo(app, client, admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    puesto, pc = _puesto(app, admin_client)
    _operario(client, 'Luis', '11223344', ['engastado'])
    _cambiar(pc)

    r = _pasar(pc, '11223344')
    assert r.status_code == 403
    assert 'Manguitos y Mangueras' in r.get_json()['error']
    eventos = pc.get(f"/api/rfid/entrada/estado?puesto_id={puesto['id']}").get_json()['eventos']
    rechazo = eventos[-1]
    assert rechazo['error_code'] == 'SIN_PERMISO'
    assert rechazo['consejo']


def test_en_engastado_sigue_como_siempre(app, client, admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    puesto, pc = _puesto(app, admin_client)
    _operario(client, 'Luis', '11223344', ['engastado'])

    assert _pasar(pc, '11223344').status_code == 200
    logins = pc.get(f"/api/operarios/logins?puesto_id={puesto['id']}").get_json()['logins']
    assert logins[0]['modulo'] == 'engastado'


def test_otro_pc_de_manguitos_no_coge_el_login_del_puesto(app, client, admin_client):
    """El login es del puesto aunque diga manguitos: un PC dedicado a
    manguitos que sondea por modulo no lo puede adoptar."""
    _, pc = _puesto(app, admin_client)
    manguitos = app.test_client()
    manguitos.environ_base['REMOTE_ADDR'] = IP_MANGUITOS
    manguitos.post('/api/pc/configurar', json={'modulo': COMPARTIDO})
    _operario(client, 'Ana', 'AABBCCDD')
    _cambiar(pc)

    assert _pasar(pc, 'AABBCCDD').status_code == 200
    assert _pasar(pc, 'DEADBEEF').status_code == 404

    logins = manguitos.get(f'/api/operarios/logins?modulo={COMPARTIDO}').get_json()['logins']
    assert logins == []
    eventos = manguitos.get(f'/api/rfid/entrada/estado?modulo={COMPARTIDO}').get_json()['eventos']
    assert eventos == []


def test_no_se_cambia_con_alguien_dentro(app, client, admin_client):
    _, pc = _puesto(app, admin_client)
    _operario(client, 'Ana', 'AABBCCDD')
    _pasar(pc, 'AABBCCDD')

    r = _cambiar(pc)
    assert r.status_code == 409
    assert 'Ana' in r.get_json()['error']
    assert pc.get('/api/pc').get_json()['modulo'] == 'engastado'


def test_la_pantalla_de_login_ensena_el_boton_y_el_modo(app, admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    _, pc = _puesto(app, admin_client)

    html = pc.get('/login').get_data(as_text=True)
    assert 'id="btn-cambiar-modo"' in html
    assert 'Pasar a Manguitos y Mangueras' in html

    _cambiar(pc)
    html = pc.get('/login').get_data(as_text=True)
    assert 'MECATRACTION · Manguitos y Mangueras' in html
    assert 'Pasar a Engastado' in html


def test_un_pc_de_manguitos_no_ensena_el_boton(app):
    pc = app.test_client()
    pc.environ_base['REMOTE_ADDR'] = IP_MANGUITOS
    pc.post('/api/pc/configurar', json={'modulo': COMPARTIDO})
    assert 'id="btn-cambiar-modo"' not in pc.get('/login').get_data(as_text=True)
