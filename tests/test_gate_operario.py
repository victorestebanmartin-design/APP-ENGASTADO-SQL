"""Tests del gate de login global: permisos por operario, cookie PC<->puesto,
sondeo de logins filtrado por puesto y el interruptor OPERARIO_GATE_ENABLED."""
import json


# ==================== MODULOS_APP / permisos por operario ====================

def test_api_modulos_lista_los_seis_modulos(client):
    d = client.get('/api/modulos').get_json()
    assert d['success']
    slugs = {m['slug'] for m in d['modulos']}
    assert slugs == {'engastado', 'mangueras', 'manguitos', 'produccion', 'visualizacion', 'etiquetas'}


def _crear_operario(client, nombre='Test Op'):
    return client.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']


def test_operario_nuevo_tiene_modulos_permitidos_null(client):
    op = _crear_operario(client)
    d = client.get('/api/operarios').get_json()
    fila = next(o for o in d['operarios'] if o['id'] == op['id'])
    assert fila['modulos_permitidos'] is None  # None = todos los modulos


def test_guardar_modulos_permitidos(client):
    op = _crear_operario(client)
    r = client.put(f"/api/operarios/{op['id']}", json={'modulos_permitidos': ['engastado', 'etiquetas']})
    assert r.get_json()['success']
    fila = next(o for o in client.get('/api/operarios').get_json()['operarios'] if o['id'] == op['id'])
    assert sorted(fila['modulos_permitidos']) == ['engastado', 'etiquetas']


def test_modulo_invalido_rechazado(client):
    op = _crear_operario(client)
    r = client.put(f"/api/operarios/{op['id']}", json={'modulos_permitidos': ['no_existe']})
    assert r.status_code == 400


def test_volver_a_null_permite_todos_de_nuevo(client):
    op = _crear_operario(client)
    client.put(f"/api/operarios/{op['id']}", json={'modulos_permitidos': ['engastado']})
    client.put(f"/api/operarios/{op['id']}", json={'modulos_permitidos': None})
    fila = next(o for o in client.get('/api/operarios').get_json()['operarios'] if o['id'] == op['id'])
    assert fila['modulos_permitidos'] is None


# ==================== Cookie PC <-> puesto ====================

def test_sin_cookie_no_hay_puesto(client):
    d = client.get('/api/puesto/pc').get_json()
    assert d['puesto_id'] is None


def test_fijar_puesto_por_primera_vez_no_requiere_pin(client):
    r = client.post('/api/puesto/pc', json={'puesto_id': 'puesto_001'})
    assert r.get_json()['success']
    assert client.get('/api/puesto/pc').get_json()['puesto_id'] == 'puesto_001'


def test_puesto_invalido_rechazado(client):
    r = client.post('/api/puesto/pc', json={'puesto_id': 'no_existe'})
    assert r.status_code == 404


def test_reasignar_sin_pin_rechazado(client):
    """Con ADMIN_PIN_HASH configurado (fixture de test), reasignar exige PIN."""
    r = client.post('/api/puesto/pc/reasignar', json={'puesto_id': 'puesto_002'})
    assert r.status_code == 401


def test_reasignar_con_pin_funciona(admin_client):
    r = admin_client.post('/api/puesto/pc/reasignar', json={'puesto_id': 'puesto_002'})
    assert r.get_json()['success']
    assert admin_client.get('/api/puesto/pc').get_json()['puesto_id'] == 'puesto_002'


# ==================== Sondeo de logins filtrado por puesto ====================

def _crear_operario_con_tag(client, nombre, tag_uid):
    op = _crear_operario(client, nombre)
    client.put(f"/api/operarios/{op['id']}", json={'tag_uid': tag_uid})
    return op


def test_logins_sin_filtro_ve_todo(client):
    """Compatibilidad: el sondeo de Engastado V3 (sin puesto_id) no cambia."""
    _crear_operario_con_tag(client, 'Op Sin Puesto', 'AAAAAAAA')
    client.post('/api/puestos/engastado_v3/entrada', json={'tag_uid': 'AAAAAAAA'})
    logins = client.get('/api/operarios/logins').get_json()['logins']
    assert len(logins) == 1


def test_logins_filtrado_por_puesto_no_ve_login_de_otro_puesto(client):
    """El fix del race condition: un login sin puesto (o de otro puesto) no
    debe aparecer al sondear con ?puesto_id=X."""
    _crear_operario_con_tag(client, 'Op Generico', 'BBBBBBBB')
    client.post('/api/puestos/engastado_v3/entrada', json={'tag_uid': 'BBBBBBBB'})  # sin device_id -> sin puesto
    logins_filtrados = client.get('/api/operarios/logins?puesto_id=puesto_001').get_json()['logins']
    assert logins_filtrados == []
    logins_todos = client.get('/api/operarios/logins').get_json()['logins']
    assert len(logins_todos) == 1


def test_logins_filtrado_ve_su_propio_login(client, admin_client):
    r = admin_client.post('/api/esp32/rfid/devices/AABBCC', json={'puesto_id': 'puesto_001'})
    assert r.get_json()['success']
    _crear_operario_con_tag(client, 'Op Puesto 1', 'CCCCCCCC')
    client.post('/api/puestos/engastado_v3/entrada', json={'tag_uid': 'CCCCCCCC', 'device_id': 'AABBCC'})
    logins = client.get('/api/operarios/logins?puesto_id=puesto_001').get_json()['logins']
    assert len(logins) == 1
    assert logins[0]['puesto_id'] == 'puesto_001'


# ==================== Sesion de operario (adoptar / consultar / salir) ====================

def test_adoptar_sesion_y_consultarla(client):
    _crear_operario_con_tag(client, 'Op Sesion', 'DDDDDDDD')
    login_id = client.post('/api/puestos/engastado_v3/entrada',
                           json={'tag_uid': 'DDDDDDDD'}).get_json()['login_id']

    r = client.post('/api/sesion/operario/adoptar', json={'login_id': login_id})
    assert r.get_json()['success']

    d = client.get('/api/sesion/operario').get_json()
    assert d['operario_nombre'] == 'Op Sesion'

    client.post('/api/sesion/operario/salir')
    assert client.get('/api/sesion/operario').get_json()['operario_nombre'] is None


def test_adoptar_login_id_inexistente_falla(client):
    r = client.post('/api/sesion/operario/adoptar', json={'login_id': 'no-existe'})
    assert r.status_code == 404


def test_salir_desactiva_el_login_de_verdad(client):
    """Regresion: 'salir' solo borraba la sesion de Flask, no el login del
    servidor -- por eso volver a /login sin escanear te readmitia solo."""
    _crear_operario_con_tag(client, 'Op Sale', '11113333')
    login_id = client.post('/api/puestos/engastado_v3/entrada',
                           json={'tag_uid': '11113333'}).get_json()['login_id']
    client.post('/api/sesion/operario/adoptar', json={'login_id': login_id})

    client.post('/api/sesion/operario/salir')

    # El login ya no aparece como activo en ningun sondeo
    assert client.get('/api/operarios/logins').get_json()['logins'] == []
    d = client.post('/api/sesion/operario/latido').get_json()
    assert d['success'] is False  # ya no hay sesion que latir


def test_latido_de_sesion_mantiene_el_login_vivo(app, client):
    import sqlite3
    from datetime import datetime, timedelta

    _crear_operario_con_tag(client, 'Op Latido', '22224444')
    login_id = client.post('/api/puestos/engastado_v3/entrada',
                           json={'tag_uid': '22224444'}).get_json()['login_id']
    client.post('/api/sesion/operario/adoptar', json={'login_id': login_id})

    # Simular que el login lleva 10 minutos sin latido (fantasma)
    viejo = (datetime.now() - timedelta(minutes=10)).isoformat()
    conn = sqlite3.connect(app.config['DB_PATH'])
    conn.execute("UPDATE operario_logins SET ultimo_latido=? WHERE id=?", (viejo, login_id))
    conn.commit()
    conn.close()

    # El latido de sesion lo revive (rowcount>0 solo si seguia activo)
    d = client.post('/api/sesion/operario/latido').get_json()
    assert d['success']

    # Tras el latido, el login ya no deberia expirar solo
    assert len(client.get('/api/operarios/logins').get_json()['logins']) == 1


def test_login_fantasma_no_reingresa_solo_por_latido(app, client):
    """Si el login ya caduco (fantasma) antes de que el navegador vuelva a
    latir, el latido de sesion debe avisar de que expiro, no revivirlo."""
    import sqlite3
    from datetime import datetime, timedelta

    _crear_operario_con_tag(client, 'Op Fantasma', '33335555')
    login_id = client.post('/api/puestos/engastado_v3/entrada',
                           json={'tag_uid': '33335555'}).get_json()['login_id']
    client.post('/api/sesion/operario/adoptar', json={'login_id': login_id})

    viejo = (datetime.now() - timedelta(minutes=10)).isoformat()
    conn = sqlite3.connect(app.config['DB_PATH'])
    conn.execute("UPDATE operario_logins SET ultimo_latido=? WHERE id=?", (viejo, login_id))
    conn.commit()
    conn.close()

    # Alguien mas sondea la lista general primero: eso expira el fantasma de verdad
    client.get('/api/operarios/logins')

    d = client.post('/api/sesion/operario/latido').get_json()
    assert d['success'] is False
    assert d['expirado'] is True


# ==================== Gate: interruptor + comportamiento end-to-end ====================

def test_gate_desactivado_por_defecto(client):
    assert client.get('/api/sistema/gate_operario').status_code == 401  # requiere PIN para leerlo


def test_gate_off_modules_muestra_todo(client):
    """Sin activar el gate, / y /modules funcionan exactamente como siempre."""
    assert client.get('/').status_code == 200
    r = client.get('/modules')
    assert r.status_code == 200
    assert b'Iniciar Engastado' in r.data
    assert b'Etiquetar' in r.data


def test_gate_on_sin_puesto_redirige_a_seleccionar(admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    r = admin_client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert '/puesto/seleccionar' in r.headers['Location']


def test_gate_on_con_puesto_sin_operario_redirige_a_login(client, admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    client.post('/api/puesto/pc', json={'puesto_id': 'puesto_001'})
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_gate_on_filtra_modulos_por_permiso(client, admin_client):
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    client.post('/api/puesto/pc', json={'puesto_id': 'puesto_001'})

    op = _crear_operario_con_tag(client, 'Op Filtrado', 'EEEEEEEE')
    client.put(f"/api/operarios/{op['id']}", json={'modulos_permitidos': ['engastado']})
    login_id = client.post('/api/puestos/engastado_v3/entrada',
                           json={'tag_uid': 'EEEEEEEE'}).get_json()['login_id']
    client.post('/api/sesion/operario/adoptar', json={'login_id': login_id})

    r = client.get('/modules')
    assert r.status_code == 200
    assert b'Iniciar Engastado' in r.data
    assert b'Etiquetar' not in r.data


def test_gate_desactivar_ignora_sesion_colgada(client, admin_client):
    """Al desactivar el gate, una sesion de operario con permisos limitados
    que quedo en curso no debe seguir filtrando /modules."""
    admin_client.post('/api/sistema/gate_operario', json={'activo': True})
    client.post('/api/puesto/pc', json={'puesto_id': 'puesto_001'})
    op = _crear_operario_con_tag(client, 'Op Colgado', 'FFFFFFFF')
    client.put(f"/api/operarios/{op['id']}", json={'modulos_permitidos': ['engastado']})
    login_id = client.post('/api/puestos/engastado_v3/entrada',
                           json={'tag_uid': 'FFFFFFFF'}).get_json()['login_id']
    client.post('/api/sesion/operario/adoptar', json={'login_id': login_id})

    admin_client.post('/api/sistema/gate_operario', json={'activo': False})
    r = client.get('/modules')
    assert b'Etiquetar' in r.data
