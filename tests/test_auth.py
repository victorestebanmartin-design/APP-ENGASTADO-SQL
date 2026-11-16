"""Tests de la protección por PIN del módulo de administración."""
from tests.conftest import PIN_TEST


def test_admin_sin_sesion_redirige_al_login_personal(client):
    r = client.get('/admin')
    assert r.status_code == 302
    assert '/admin/login' in r.headers['Location']


def test_api_admin_sin_sesion_devuelve_401(client):
    r = client.post('/api/actualizar_sistema')
    assert r.status_code == 401
    r = client.get('/api/comprobar_actualizaciones')
    assert r.status_code == 401
    r = client.post('/api/upload')
    assert r.status_code == 401


def test_pin_correcto_abre_sesion(client):
    r = client.post('/admin/pin', data={'pin': PIN_TEST})
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/admin')
    # Con la sesión abierta, /admin ya no redirige
    r = client.get('/admin')
    assert r.status_code == 200


def test_pin_incorrecto_no_abre_sesion(client):
    r = client.post('/admin/pin', data={'pin': '0000'})
    assert r.status_code == 200
    assert 'PIN incorrecto' in r.get_data(as_text=True)
    r = client.get('/admin')
    assert r.status_code == 302


def test_bloqueo_tras_cinco_intentos_fallidos(client):
    for _ in range(5):
        client.post('/admin/pin', data={'pin': '0000'})
    # Incluso con el PIN correcto, la IP está bloqueada
    r = client.post('/admin/pin', data={'pin': PIN_TEST})
    assert 'Demasiados intentos' in r.get_data(as_text=True)
    r = client.get('/admin')
    assert r.status_code == 302


def _pin_en_fichero(app, pin_hash):
    """Deja el PIN en data/admin_pin.json, como en una instalación sin .env."""
    import json
    import os
    app.config['ADMIN_PIN_HASH'] = ''
    with open(os.path.join(app.config['DATA_DIR'], 'admin_pin.json'), 'w', encoding='utf-8') as f:
        json.dump({'pin_hash': pin_hash}, f)


def _hash_en_fichero(app):
    import json
    import os
    with open(os.path.join(app.config['DATA_DIR'], 'admin_pin.json'), encoding='utf-8') as f:
        return json.load(f)['pin_hash']


def test_el_pin_nuevo_se_guarda_con_sal(app, client):
    import hashlib
    app.config['ADMIN_PIN_HASH'] = ''
    r = client.post('/admin/pin/configurar', data={'pin': '4821', 'pin2': '4821'})
    assert r.status_code == 302
    guardado = _hash_en_fichero(app)
    assert guardado != hashlib.sha256(b'4821').hexdigest()
    assert '$' in guardado           # método$sal$hash, no un SHA-256 a secas

    otro = app.test_client()
    assert otro.post('/admin/pin', data={'pin': '4821'}).status_code == 302
    assert 'PIN incorrecto' in app.test_client().post(
        '/admin/pin', data={'pin': '4822'}).get_data(as_text=True)


def test_un_pin_antiguo_sigue_entrando_y_se_renueva(app, client):
    """Instalaciones ya en marcha: no se les puede pedir que fijen el PIN otra vez."""
    import hashlib
    antiguo = hashlib.sha256(b'4821').hexdigest()
    _pin_en_fichero(app, antiguo)

    assert 'PIN incorrecto' in client.post('/admin/pin', data={'pin': '0000'}).get_data(as_text=True)
    assert _hash_en_fichero(app) == antiguo      # un fallo no renueva nada

    assert client.post('/admin/pin', data={'pin': '4821'}).status_code == 302
    assert _hash_en_fichero(app) != antiguo
    assert app.test_client().post('/admin/pin', data={'pin': '4821'}).status_code == 302


def test_el_pin_del_env_antiguo_sigue_valiendo_y_no_se_toca(app, client):
    """El de conftest es un SHA-256 en ADMIN_PIN_HASH: entra y no escribe nada."""
    import os
    assert client.post('/admin/pin', data={'pin': PIN_TEST}).status_code == 302
    assert not os.path.exists(os.path.join(app.config['DATA_DIR'], 'admin_pin.json'))


def test_cambiar_el_pin_desde_admin_lo_deja_con_sal(app, admin_client):
    import hashlib
    _pin_en_fichero(app, hashlib.sha256(b'4821').hexdigest())
    r = admin_client.post('/api/sistema/admin_pin', json={
        'pin_actual': '4821', 'pin_nuevo': '9517', 'pin_nuevo_confirmar': '9517'})
    assert r.get_json()['success'], r.get_json()
    assert '$' in _hash_en_fichero(app)
    assert app.test_client().post('/admin/pin', data={'pin': '9517'}).status_code == 302


def test_un_hash_ilegible_no_tumba_el_login(app, client):
    _pin_en_fichero(app, 'esto-no-es-un-hash')
    r = client.post('/admin/pin', data={'pin': '4821'})
    assert r.status_code == 200
    assert 'PIN incorrecto' in r.get_data(as_text=True)


def test_logout_cierra_sesion(admin_client):
    assert admin_client.get('/admin').status_code == 200
    admin_client.get('/admin/logout')
    assert admin_client.get('/admin').status_code == 302


def test_respuestas_incluyen_cabeceras_de_seguridad(client):
    r = client.get('/health')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'DENY'
    assert r.headers['Referrer-Policy'] == 'same-origin'
    assert r.headers['Permissions-Policy'] == (
        'camera=(), microphone=(), geolocation=(), payment=()'
    )
    assert 'Strict-Transport-Security' not in r.headers


def test_cookie_de_sesion_es_httponly_y_samesite(client):
    r = client.post('/admin/pin', data={'pin': PIN_TEST})
    cookie = r.headers['Set-Cookie']
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie


def crear_admin_personal(app, permisos='["admin"]'):
    from sqlalchemy import text
    from werkzeug.security import generate_password_hash
    from app.routes.base import db
    with db.engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO operarios (id, nombre, modulos_permitidos, clave_personal_hash) "
            "VALUES ('responsable', 'Responsable', :permisos, :clave)"
        ), {'permisos': permisos, 'clave': generate_password_hash('personal123')})


def test_admin_personal_abre_todo_el_panel(client, app):
    crear_admin_personal(app)
    respuesta = client.post('/admin/login', data={'operario_id': 'responsable', 'clave': 'personal123'})
    assert respuesta.status_code == 302
    assert client.get('/admin').status_code == 200
    with client.session_transaction() as sesion:
        assert sesion['admin_operario_id'] == 'responsable'
    client.get('/admin/logout')
    assert client.get('/admin').status_code == 302


def test_admin_personal_no_concede_admin_por_defecto(client, app):
    crear_admin_personal(app, permisos=None)
    client.post('/admin/login', data={'operario_id': 'responsable', 'clave': 'personal123'})
    assert client.get('/admin').status_code == 302
    assert client.put('/api/operarios/responsable', json={'modulos_permitidos': ['admin']}).status_code == 401


def test_revocar_permiso_invalida_sesion_admin(client, app):
    from sqlalchemy import text
    from app.routes.base import db
    crear_admin_personal(app)
    client.post('/admin/login', data={'operario_id': 'responsable', 'clave': 'personal123'})
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE operarios SET modulos_permitidos='[]' WHERE id='responsable'"))
    assert client.get('/admin').status_code == 302


def test_pin_recuperacion_no_puede_resolver_propuestas(admin_client):
    respuesta = admin_client.post('/api/mangueras/propuestas/1/resolver', json={
        'accion': 'aprobar', 'motivo': 'Revision conforme',
    })
    assert respuesta.status_code == 401
