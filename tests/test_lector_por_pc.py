"""Dos PCs dedicados al mismo modulo, cada uno con su lector RFID.

Asignando el lector solo al modulo, los dos PCs sondeaban lo mismo y adoptaban
los dos el login de cualquiera de los lectores: se abrian las dos pantallas
con el mismo operario. Ahora el lector se casa con la IP de su PC.
"""
from conftest import admin_de

PC1, PC2 = '10.0.0.11', '10.0.0.12'
MODULO = 'manguitos_mangueras'


def _pc(app, ip):
    cliente = app.test_client()
    cliente.environ_base['REMOTE_ADDR'] = ip
    assert cliente.post('/api/pc/configurar', json={'modulo': MODULO}).get_json()['success']
    return cliente


def _operario(client, nombre, uid):
    admin = admin_de(client)
    op = admin.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']
    admin.put(f"/api/operarios/{op['id']}", json={'tag_uid': uid})


def _asignar(admin_client, device_id, destino):
    return admin_client.post(f'/api/esp32/rfid/devices/{device_id}', json={'puesto_id': destino})


def _pasar(cliente, uid, device_id):
    return cliente.post('/api/puestos/engastado_v3/entrada',
                        json={'tag_uid': uid, 'device_id': device_id})


def _logins(cliente):
    datos = cliente.get(f'/api/operarios/logins?modulo={MODULO}').get_json()
    return [l['operario'] for l in datos['logins']]


def _codigos(cliente):
    datos = cliente.get(f'/api/rfid/entrada/estado?modulo={MODULO}').get_json()
    return [e['error_code'] for e in datos['eventos']]


def _dos_puestos(app, admin_client):
    pc1, pc2 = _pc(app, PC1), _pc(app, PC2)
    assert _asignar(admin_client, 'lector01', f'pc:{PC1}').get_json()['success']
    assert _asignar(admin_client, 'lector02', f'pc:{PC2}').get_json()['success']
    return pc1, pc2


def test_admin_ofrece_cada_pc_del_modulo(app, admin_client):
    _pc(app, PC1)
    _pc(app, PC2)
    _asignar(admin_client, 'lector01', f'pc:{PC2}')

    datos = admin_client.get('/api/esp32/rfid/devices').get_json()
    opciones = {o['id'] for o in datos['puestos']}
    assert {f'pc:{PC1}', f'pc:{PC2}'} <= opciones
    lector = next(d for d in datos['devices'] if d['id'] == 'lector01')
    assert lector['puesto_id'] == f'pc:{PC2}'


def _bautizar_pc(app, ip, nombre):
    """Como ponerle nombre al PC en Admin -> IPs (tipo 'PC de puesto')."""
    from sqlalchemy import text
    with app.app_context():
        with app.extensions['db'].engine.connect() as conn:
            conn.execute(text("INSERT INTO esp32_ips (device_id, tipo, nombre, ip) "
                              "VALUES (:d, 'pc', :n, :ip)"),
                         {'d': 'pc' + ip.replace('.', ''), 'n': nombre, 'ip': ip})
            conn.commit()


def test_todas_las_opciones_dicen_su_ip_y_el_nombre_del_pc(app, admin_client):
    puesto = admin_client.post('/api/puestos', json={'nombre': 'AMP'}).get_json()['puesto']
    engastado = app.test_client()
    engastado.environ_base['REMOTE_ADDR'] = '10.0.0.20'
    engastado.post('/api/pc/configurar', json={'modulo': 'engastado', 'puesto_id': puesto['id']})
    _pc(app, PC1)
    _pc(app, PC2)
    _bautizar_pc(app, PC1, 'PC MANGUERAS 1')
    _bautizar_pc(app, '10.0.0.20', 'PC AMP')

    opciones = {o['id']: o['nombre'] for o in
                admin_client.get('/api/esp32/rfid/devices').get_json()['puestos']}
    assert '10.0.0.20 (PC AMP)' in opciones[puesto['id']]
    assert 'PC MANGUERAS 1' in opciones[f'pc:{PC1}'] and PC1 in opciones[f'pc:{PC1}']
    assert PC2 in opciones[f'pc:{PC2}']
    # El modulo completo dice a que PCs llega: a los dos
    compartido = opciones[f'modulo:{MODULO}']
    assert f'{PC1} (PC MANGUERAS 1)' in compartido and PC2 in compartido
    assert 'sin PC configurado' in opciones['modulo:mangueras']


def test_la_ip_vieja_de_un_puesto_sale_marcada(app, admin_client):
    """Un PC al que se le cambio la IP deja su identidad vieja en pc_equipos:
    sale en el desplegable, pero avisando de que no se conecta."""
    import json
    import os
    from datetime import datetime
    puesto = admin_client.post('/api/puestos', json={'nombre': 'PUNTERAS'}).get_json()['puesto']
    for ip in ('10.0.0.10', '10.0.0.14'):
        pc = app.test_client()
        pc.environ_base['REMOTE_ADDR'] = ip
        pc.post('/api/pc/configurar', json={'modulo': 'engastado', 'puesto_id': puesto['id']})
    with open(os.path.join(app.config['DATA_DIR'], 'pcs_vistos.json'), 'w', encoding='utf-8') as f:
        json.dump({'10.0.0.14': {'last_seen': datetime.now().isoformat()}}, f)

    texto = {o['id']: o['nombre'] for o in
             admin_client.get('/api/esp32/rfid/devices').get_json()['puestos']}[puesto['id']]
    assert '10.0.0.10 ⚠ sin conectarse' in texto
    assert '10.0.0.14 ⚠' not in texto


def test_cada_tarjeta_abre_solo_el_pc_de_su_lector(app, client, admin_client):
    pc1, pc2 = _dos_puestos(app, admin_client)
    _operario(client, 'Ana', 'AABBCCDD')
    _operario(client, 'Luis', '11223344')

    assert _pasar(pc1, 'AABBCCDD', 'lector01').status_code == 200
    assert _logins(pc1) == ['Ana']
    assert _logins(pc2) == []

    assert _pasar(pc2, '11223344', 'lector02').status_code == 200
    assert _logins(pc1) == ['Ana']
    assert _logins(pc2) == ['Luis']


def test_un_pc_no_puede_adoptar_el_login_del_otro(app, client, admin_client):
    pc1, pc2 = _dos_puestos(app, admin_client)
    _operario(client, 'Ana', 'AABBCCDD')
    login_id = _pasar(pc1, 'AABBCCDD', 'lector01').get_json()['login_id']

    r = pc2.post('/api/sesion/operario/adoptar', json={'login_id': login_id})
    assert r.status_code == 403
    assert pc1.post('/api/sesion/operario/adoptar', json={'login_id': login_id}).get_json()['success']


def test_los_rechazos_solo_salen_en_el_pc_de_su_lector(app, client, admin_client):
    pc1, pc2 = _dos_puestos(app, admin_client)
    assert _pasar(pc1, 'DEADBEEF', 'lector01').status_code == 404

    assert 'TAG_NO_REG' in _codigos(pc1)
    assert 'TAG_NO_REG' not in _codigos(pc2)


def test_la_misma_tarjeta_en_el_otro_pc_avisa_de_donde_esta(app, client, admin_client):
    pc1, pc2 = _dos_puestos(app, admin_client)
    _operario(client, 'Ana', 'AABBCCDD')
    _pasar(pc1, 'AABBCCDD', 'lector01')

    r = _pasar(pc2, 'AABBCCDD', 'lector02')
    assert r.status_code == 409
    assert PC1 in r.get_json()['error']
    assert _logins(pc2) == []


def test_no_se_puede_asignar_un_pc_que_no_es_del_modulo(app, admin_client):
    r = _asignar(admin_client, 'lector01', 'pc:10.0.0.99')
    assert r.status_code == 404
    assert 'no está configurado' in r.get_json()['message']


def test_lector_asignado_solo_al_modulo_sigue_como_antes(app, client, admin_client):
    """Sin PC elegido el login es de todo el modulo: desplegar no cambia nada."""
    pc1, pc2 = _pc(app, PC1), _pc(app, PC2)
    _asignar(admin_client, 'lector01', f'modulo:{MODULO}')
    _operario(client, 'Ana', 'AABBCCDD')

    assert _pasar(pc1, 'AABBCCDD', 'lector01').status_code == 200
    assert _logins(pc1) == ['Ana']
    assert _logins(pc2) == ['Ana']


def test_cambiar_el_lector_a_modulo_olvida_el_pc(app, admin_client):
    _pc(app, PC1)
    _asignar(admin_client, 'lector01', f'pc:{PC1}')
    _asignar(admin_client, 'lector01', f'modulo:{MODULO}')

    datos = admin_client.get('/api/esp32/rfid/devices').get_json()
    lector = next(d for d in datos['devices'] if d['id'] == 'lector01')
    assert lector['puesto_id'] == f'modulo:{MODULO}'
