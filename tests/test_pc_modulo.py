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
    assert d['destino'] == '/modules'

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
