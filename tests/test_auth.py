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
