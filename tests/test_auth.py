"""Tests de la protección por PIN del módulo de administración."""
from tests.conftest import PIN_TEST


def test_admin_sin_sesion_redirige_al_pin(client):
    r = client.get('/admin')
    assert r.status_code == 302
    assert '/admin/pin' in r.headers['Location']


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
