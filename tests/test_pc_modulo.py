"""Identidad del PC por modulo: mangueras y manguitos son equipos, no puestos.

Cubre lo que se pidio al rediseñar el arranque:
  - Un PC se dedica a un modulo. Engastado necesita ademas un puesto;
    mangueras y manguitos no (no existen puestos para ellos).
  - Entrada directa: al identificarse en ese PC se va a su modulo.
  - Los permisos por operario mandan por encima del PC: dedicar un equipo a
    manguitos NO da acceso a manguitos.
"""
import time

import pytest


def _crear_puesto(admin_client, nombre='PUNTERAS'):
    return admin_client.post('/api/puestos', json={'nombre': nombre}).get_json()['puesto']


def _activar_gate(app, activo=True):
    import json
    import os
    with app.app_context():
        ruta = os.path.join(app.config['DATA_DIR'], 'operario_gate.json')
        with open(ruta, 'w') as f:
            json.dump({'enabled': activo}, f)


def _operario_dentro(app, client, nombre, modulos=None, modulo_login=None, puesto_id=None):
    """Crea el operario, le fija permisos y le mete un login vivo adoptado."""
    import uuid
    from datetime import datetime
    from sqlalchemy import text

    op = client.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']
    if modulos is not None:
        client.put(f"/api/operarios/{op['id']}", json={'modulos_permitidos': modulos})

    login_id = str(uuid.uuid4())
    ahora = datetime.now().isoformat()
    with app.app_context():
        db = app.extensions['db']
        with db.engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO operario_logins "
                "(id, operario_nombre, timestamp_login, ultimo_latido, activo, puesto_id, modulo) "
                "VALUES (:id, :n, :t, :t, 1, :p, :m)"
            ), {'id': login_id, 'n': nombre, 't': ahora, 'p': puesto_id, 'm': modulo_login})
            conn.commit()

    with client.session_transaction() as s:
        s['operario_actual'] = nombre
        s['operario_login_id'] = login_id
    return login_id


# ==================== Configurar el equipo ====================

def test_pc_sin_configurar_no_tiene_modulo(client):
    d = client.get('/api/pc').get_json()
    assert d['modulo'] is None
    assert d['configurado'] is False


@pytest.mark.parametrize('modulo,destino', [
    ('mangueras', '/mangueras'),
    ('manguitos', '/manguitos'),
])
def test_configurar_pc_de_modulo_sin_puesto(client, modulo, destino):
    """Mangueras y manguitos NO piden puesto: se configura el PC y ya."""
    r = client.post('/api/pc/configurar', json={'modulo': modulo})
    d = r.get_json()
    assert d['success'], d
    assert d['puesto_id'] is None
    assert d['destino'] == destino

    estado = client.get('/api/pc').get_json()
    assert estado['modulo'] == modulo
    assert estado['puesto_id'] is None
    assert estado['destino'] == destino


def test_configurar_pc_de_engastado_exige_puesto(client):
    r = client.post('/api/pc/configurar', json={'modulo': 'engastado'})
    assert r.status_code == 400
    assert 'puesto' in r.get_json()['error'].lower()


def test_configurar_pc_de_engastado_con_puesto(client, admin_client):
    puesto = _crear_puesto(admin_client)
    d = client.post('/api/pc/configurar',
                    json={'modulo': 'engastado', 'puesto_id': puesto['id']}).get_json()
    assert d['success']
    assert d['puesto_id'] == puesto['id']
    assert d['destino'] == '/v3'      # a engastar, no a la rejilla

    estado = client.get('/api/pc').get_json()
    assert estado['modulo'] == 'engastado'
    assert estado['puesto_nombre'] == 'PUNTERAS'


def test_modulo_invalido_rechazado(client):
    r = client.post('/api/pc/configurar', json={'modulo': 'inventado'})
    assert r.status_code == 400


def test_reconfigurar_un_pc_ya_configurado_exige_pin(client):
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    r = client.post('/api/pc/configurar', json={'modulo': 'mangueras'})
    assert r.status_code == 401
    # y no ha cambiado nada
    assert client.get('/api/pc').get_json()['modulo'] == 'manguitos'


def test_admin_si_puede_reconfigurar(admin_client):
    admin_client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    r = admin_client.post('/api/pc/configurar', json={'modulo': 'mangueras'})
    assert r.get_json()['success']
    assert admin_client.get('/api/pc').get_json()['modulo'] == 'mangueras'


def test_identidad_sobrevive_a_perder_las_cookies(app, client):
    """La IP fija es la identidad principal: borrar la cache no descoloca el PC."""
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    limpio = app.test_client()          # navegador nuevo, sin cookies, misma IP
    assert limpio.get('/api/pc').get_json()['modulo'] == 'manguitos'


def test_liberar_borra_tambien_la_identidad_por_ip(app, admin_client):
    admin_client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    admin_client.post('/api/puesto/pc/liberar')
    assert admin_client.get('/api/pc').get_json()['modulo'] is None
    # y tampoco queda rastro por IP para un navegador limpio
    assert app.test_client().get('/api/pc').get_json()['modulo'] is None


# ==================== Entrada directa + permisos ====================

def test_pc_sin_configurar_manda_a_configurar(app, client):
    _activar_gate(app)
    r = client.get('/manguitos')
    assert r.status_code == 302
    assert '/puesto/seleccionar' in r.headers['Location']


def test_pc_configurado_sin_operario_manda_al_lector(app, client):
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    r = client.get('/manguitos')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_operario_con_permiso_entra_al_modulo(app, client):
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    _operario_dentro(app, client, 'Ana', modulos=['manguitos'], modulo_login='manguitos')
    r = client.get('/manguitos')
    assert r.status_code == 200


def test_operario_sin_permiso_no_entra_aunque_el_pc_sea_de_ese_modulo(app, client):
    """El nucleo del requisito: el PC no es una puerta trasera."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    _operario_dentro(app, client, 'Bea', modulos=['engastado'], modulo_login='manguitos')

    r = client.get('/manguitos')
    assert r.status_code == 403
    cuerpo = r.get_data(as_text=True)
    assert 'No tienes permiso' in cuerpo
    assert 'Bea' in cuerpo
    assert 'administrador' in cuerpo


def test_operario_sin_ningun_modulo_tampoco_entra(app, client):
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'mangueras'})
    _operario_dentro(app, client, 'Caro', modulos=[], modulo_login='mangueras')
    assert client.get('/mangueras').status_code == 403


def test_operario_sin_permisos_explicitos_entra(app, client):
    """modulos_permitidos NULL = todos menos admin (no romper instalaciones)."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'mangueras'})
    _operario_dentro(app, client, 'Dani', modulos=None, modulo_login='mangueras')
    assert client.get('/mangueras').status_code == 200


def test_engastado_tambien_comprueba_permisos(app, client, admin_client):
    _activar_gate(app)
    puesto = _crear_puesto(admin_client)
    client.post('/api/pc/configurar', json={'modulo': 'engastado', 'puesto_id': puesto['id']})
    _operario_dentro(app, client, 'Eva', modulos=['mangueras'], puesto_id=puesto['id'])
    assert client.get('/v3').status_code == 403


def test_con_el_gate_apagado_no_se_restringe_nada(app, client):
    _activar_gate(app, False)
    assert client.get('/manguitos').status_code == 200
    assert client.get('/mangueras').status_code == 200


# ==================== Sondeo de logins por modulo ====================

def test_logins_se_filtran_por_modulo(app, client):
    """El PC de manguitos no debe adoptar el login del lector de mangueras."""
    _operario_dentro(app, client, 'Fran', modulo_login='manguitos')
    _operario_dentro(app, app.test_client(), 'Gema', modulo_login='mangueras')

    solo_manguitos = client.get('/api/operarios/logins?modulo=manguitos').get_json()['logins']
    assert [l['operario'] for l in solo_manguitos] == ['Fran']

    solo_mangueras = client.get('/api/operarios/logins?modulo=mangueras').get_json()['logins']
    assert [l['operario'] for l in solo_mangueras] == ['Gema']


# ==================== El servidor: suite completa, sin tarjeta ====================

def test_configurar_el_pc_como_servidor(client):
    d = client.post('/api/pc/configurar', json={'modulo': 'servidor'}).get_json()
    assert d['success']
    assert d['puesto_id'] is None
    assert d['destino'] == '/modules'


def test_el_servidor_no_pide_tarjeta(app, client):
    """Con el gate activo, el servidor entra igualmente y sin identificarse."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'servidor'})
    assert client.get('/modules').status_code == 200


def test_el_servidor_ve_la_rejilla_entera(app, client):
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'servidor'})
    cuerpo = client.get('/modules').get_data(as_text=True)
    assert 'Iniciar Engastado' in cuerpo
    assert 'Etiquetar' in cuerpo


def test_el_servidor_entra_a_cualquier_modulo_sin_permisos(app, client):
    """No hay operario en sesión y aun así se abre todo."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'servidor'})
    assert client.get('/manguitos').status_code == 200
    assert client.get('/mangueras').status_code == 200
    assert client.get('/v3').status_code == 200


def test_en_el_servidor_cerrar_un_modulo_vuelve_a_la_rejilla(app, client):
    """El servidor sí tiene rejilla a la que volver: no es una salida."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'servidor'})
    cuerpo = client.get('/manguitos').get_data(as_text=True)
    assert 'Volver a módulos' in cuerpo
    assert 'salirModulo' not in cuerpo


def test_la_raiz_en_un_pc_de_planta_lleva_a_su_modulo(app, client):
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    _operario_dentro(app, client, 'Quim', modulos=['manguitos'], modulo_login='manguitos')

    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    r2 = client.get(r.headers['Location'], follow_redirects=False)
    assert r2.headers['Location'].endswith('/manguitos')


def test_la_raiz_en_el_servidor_sigue_siendo_la_home(app, client):
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'servidor'})
    assert client.get('/').status_code == 200


def test_un_pc_de_planta_no_es_servidor(app, client, admin_client):
    _activar_gate(app)
    puesto = _crear_puesto(admin_client)
    client.post('/api/pc/configurar', json={'modulo': 'engastado', 'puesto_id': puesto['id']})
    r = client.get('/modules')
    assert r.status_code == 302        # sigue pidiendo tarjeta
    assert '/login' in r.headers['Location']


# ==================== Salir del modulo en un PC dedicado ====================

def test_pc_de_engastado_cierra_sesion_al_salir_de_v3(app, client, admin_client):
    """En un PC de engastado, cerrar V3 es salir al lector, no ir a la rejilla."""
    _activar_gate(app)
    puesto = _crear_puesto(admin_client)
    client.post('/api/pc/configurar', json={'modulo': 'engastado', 'puesto_id': puesto['id']})
    _operario_dentro(app, client, 'Rosa', modulos=['engastado'], puesto_id=puesto['id'])

    cuerpo = client.get('/v3').get_data(as_text=True)
    assert 'salirModulo' in cuerpo
    assert 'PC_DEDICADO_ENGASTADO = true' in cuerpo



def test_pc_dedicado_ofrece_cerrar_sesion_no_volver_a_modulos(app, client):
    """Cerrar el modulo en su PC es una salida, no un paseo a la rejilla."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    _operario_dentro(app, client, 'Iris', modulos=['manguitos'], modulo_login='manguitos')

    cuerpo = client.get('/manguitos').get_data(as_text=True)
    assert 'Cerrar sesión' in cuerpo
    assert 'salirModulo' in cuerpo
    assert 'Volver a módulos' not in cuerpo


def test_pc_de_engastado_sigue_volviendo_a_la_rejilla(app, client, admin_client):
    """Abrir mangueras desde /modules en un PC de engastado no es una salida."""
    _activar_gate(app)
    puesto = _crear_puesto(admin_client)
    client.post('/api/pc/configurar', json={'modulo': 'engastado', 'puesto_id': puesto['id']})
    _operario_dentro(app, client, 'Jon', modulos=['engastado', 'mangueras'],
                     puesto_id=puesto['id'])

    cuerpo = client.get('/mangueras').get_data(as_text=True)
    assert 'Volver a módulos' in cuerpo
    assert 'salirModulo' not in cuerpo


def test_salir_desactiva_el_login_y_exige_tarjeta_nueva(app, client):
    """El siguiente que llegue al PC no puede heredar la sesion del anterior."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    _operario_dentro(app, client, 'Kira', modulos=['manguitos'], modulo_login='manguitos')
    assert client.get('/manguitos').status_code == 200

    client.post('/api/sesion/operario/salir')

    r = client.get('/manguitos')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']
    # y el login ya no esta vivo, asi que no se puede readoptar sin tarjeta
    assert client.get('/api/operarios/logins?modulo=manguitos').get_json()['logins'] == []


def test_pc_dedicado_no_puede_colarse_en_la_rejilla(app, client):
    """Ir a /modules a mano en un PC de manguitos entra al modulo, no a la rejilla."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    _operario_dentro(app, client, 'Leo', modulos=['manguitos', 'etiquetas'],
                     modulo_login='manguitos')

    r = client.get('/modules')
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/manguitos')


def test_sin_permiso_para_el_modulo_del_pc_no_hay_bucle(app, client):
    """Sin permiso, /modules muestra la rejilla en vez de rebotar a un 403."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    _operario_dentro(app, client, 'Mar', modulos=['etiquetas'], modulo_login='manguitos')
    assert client.get('/modules').status_code == 200


# ==================== Motivo del rechazo en el lector RFID ====================

def _asignar_lector(app, device_id, destino):
    """Asigna el lector desde Admin. destino: id de puesto o 'modulo:manguitos'."""
    import json
    import os
    import time as _time
    with app.app_context():
        ruta = os.path.join(app.config['DATA_DIR'], 'esp32_rfid_devices.json')
        with open(ruta, 'w') as f:
            json.dump({device_id: {}}, f)

    # El endpoint esta protegido por PIN: hace falta sesion de admin.
    admin = app.test_client()
    with admin.session_transaction() as s:
        s['admin_verificado'] = True
        s['admin_verificado_ts'] = _time.time()
    r = admin.post(f'/api/esp32/rfid/devices/{device_id}', json={'puesto_id': destino})
    assert r.get_json()['success'], r.get_json()
    return r


def _pasar_tarjeta(client, uid, device_id='lector01'):
    return client.post('/api/puestos/engastado_v3/entrada',
                       json={'tag_uid': uid, 'device_id': device_id})


def _estado(client, **params):
    from urllib.parse import urlencode
    d = client.get(f'/api/rfid/entrada/estado?{urlencode(params)}').get_json()
    return d['eventos']


def test_pantalla_login_de_un_pc_de_modulo(client):
    """Sin puesto, la pantalla sondea por módulo y sabe a dónde entrar."""
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    cuerpo = client.get('/login').get_data(as_text=True)
    assert 'modulo=' in cuerpo or 'MODULO' in cuerpo
    assert 'Colocación de Manguitos' in cuerpo
    assert 'mostrarMotivo' in cuerpo


def test_pantalla_login_de_un_puesto_de_engastado(client, admin_client):
    puesto = _crear_puesto(admin_client)
    client.post('/api/pc/configurar', json={'modulo': 'engastado', 'puesto_id': puesto['id']})
    cuerpo = client.get('/login').get_data(as_text=True)
    assert 'PUNTERAS' in cuerpo


def test_tarjeta_no_registrada_dice_el_motivo_y_que_hacer(app, client, admin_client):
    puesto = _crear_puesto(admin_client)
    _asignar_lector(app, 'lector01', puesto['id'])

    r = _pasar_tarjeta(client, 'AABBCCDD')
    assert r.status_code == 404

    ev = _estado(client, puesto_id=puesto['id'])[-1]
    assert ev['estado'] == 'rechazo'
    assert ev['error_code'] == 'TAG_NO_REG'
    assert 'no registrada' in ev['motivo']
    assert 'administrador' in ev['consejo']


def test_lector_sin_asignar_avisa_en_todas_las_pantallas(app, client):
    """El lector que nadie ha casado no es de ningún PC: el aviso va a todos."""
    op = client.post('/api/operarios', json={'nombre': 'Nora'}).get_json()['operario']
    client.put(f"/api/operarios/{op['id']}", json={'tag_uid': 'AABBCCDD'})

    _pasar_tarjeta(client, 'AABBCCDD', device_id='huerfano')

    avisos = [e for e in _estado(client, modulo='manguitos')
              if e['error_code'] == 'LECTOR_SIN_ASIGNAR']
    assert avisos, 'el aviso de lector sin asignar debe llegar igualmente'
    assert 'Lectores RFID' in avisos[-1]['consejo']


def test_sin_permiso_se_rechaza_en_el_lector_con_su_motivo(app, client):
    """Mejor rechazar en el lector que crear un login y rebotarlo después."""
    _activar_gate(app)
    _asignar_lector(app, 'lector01', 'modulo:manguitos')
    op = client.post('/api/operarios', json={'nombre': 'Olga'}).get_json()['operario']
    client.put(f"/api/operarios/{op['id']}",
               json={'tag_uid': 'AABBCCDD', 'modulos_permitidos': ['engastado']})

    r = _pasar_tarjeta(client, 'AABBCCDD')
    assert r.status_code == 403
    assert 'no tiene permiso' in r.get_json()['error']

    ev = _estado(client, modulo='manguitos')[-1]
    assert ev['error_code'] == 'SIN_PERMISO'
    assert 'Olga' in ev['motivo']
    assert 'Módulos permitidos' in ev['consejo']

    # y no se ha gastado el login exclusivo del operario
    assert client.get('/api/operarios/logins').get_json()['logins'] == []


def test_con_permiso_si_entra(app, client):
    _activar_gate(app)
    _asignar_lector(app, 'lector01', 'modulo:manguitos')
    op = client.post('/api/operarios', json={'nombre': 'Pau'}).get_json()['operario']
    client.put(f"/api/operarios/{op['id']}",
               json={'tag_uid': 'AABBCCDD', 'modulos_permitidos': ['manguitos']})

    r = _pasar_tarjeta(client, 'AABBCCDD')
    assert r.status_code == 200
    logins = client.get('/api/operarios/logins?modulo=manguitos').get_json()['logins']
    assert [l['operario'] for l in logins] == ['Pau']


def test_los_rechazos_de_otro_puesto_no_ensucian_mi_pantalla(app, client, admin_client):
    p1 = _crear_puesto(admin_client, 'PUESTO UNO')
    p2 = _crear_puesto(admin_client, 'PUESTO DOS')
    _asignar_lector(app, 'lector01', p1['id'])
    _pasar_tarjeta(client, 'AABBCCDD')          # tarjeta desconocida en p1

    ajenos = [e for e in _estado(client, puesto_id=p2['id'])
              if e['error_code'] == 'TAG_NO_REG']
    assert ajenos == []


def test_adoptar_avisa_de_la_falta_de_permisos(app, client):
    """La pantalla de login puede avisar en el acto, sin mandar a un 403."""
    _activar_gate(app)
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'})
    login_id = _operario_dentro(app, client, 'Hugo', modulos=['engastado'],
                                modulo_login='manguitos')

    d = client.post('/api/sesion/operario/adoptar', json={'login_id': login_id}).get_json()
    assert d['success']
    assert d['modulo'] == 'manguitos'
    assert d['permitido'] is False
