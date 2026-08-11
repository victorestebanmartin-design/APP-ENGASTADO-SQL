"""Tests del login exclusivo de operarios en el módulo de engastado."""
import sqlite3
from datetime import datetime, timedelta


def _login(client, nombre='PEPE'):
    return client.post('/api/operarios/login', json={'nombre': nombre})


def test_login_devuelve_login_id(client):
    d = _login(client).get_json()
    assert d['success'], d
    assert d['login_id']


def test_no_permite_dos_logins_del_mismo_operario(client):
    assert _login(client).get_json()['success']
    r = _login(client)
    assert r.status_code == 409
    d = r.get_json()
    assert not d['success']
    assert 'ya está dentro' in d['error']


def test_operarios_distintos_pueden_entrar_a_la_vez(client):
    assert _login(client, 'PEPE').get_json()['success']
    assert _login(client, 'MARIA').get_json()['success']


def test_logout_libera_el_login(client):
    login_id = _login(client).get_json()['login_id']
    assert client.post('/api/operarios/logout', json={'login_id': login_id}).get_json()['success']
    # Tras el logout se puede volver a entrar con el mismo operario
    assert _login(client).get_json()['success']


def test_latido_mantiene_el_login_vivo(client):
    login_id = _login(client).get_json()['login_id']
    d = client.post('/api/operarios/login/latido', json={'login_id': login_id}).get_json()
    assert d['success']


def test_login_sin_latido_caduca_solo(app, client):
    login_id = _login(client).get_json()['login_id']

    # Simular que el navegador murió hace 10 minutos (sin latidos)
    viejo = (datetime.now() - timedelta(minutes=10)).isoformat()
    conn = sqlite3.connect(app.config['DB_PATH'])
    conn.execute("UPDATE operario_logins SET ultimo_latido=? WHERE id=?", (viejo, login_id))
    conn.commit()
    conn.close()

    # El operario puede volver a entrar (el login fantasma se expira)
    assert _login(client).get_json()['success']

    # Y el latido del login viejo avisa de que expiró
    d = client.post('/api/operarios/login/latido', json={'login_id': login_id}).get_json()
    assert not d['success']
    assert d['expirado']


def test_listado_de_logins_activos(client):
    _login(client, 'PEPE')
    _login(client, 'MARIA')
    d = client.get('/api/operarios/logins').get_json()
    assert d['success']
    assert sorted(l['operario'] for l in d['logins']) == ['MARIA', 'PEPE']


def test_liberar_login_requiere_admin(client, admin_client):
    login_id = _login(client).get_json()['login_id']

    # Sin sesión de admin → 401
    r = client.post(f'/api/operarios/logins/{login_id}/liberar')
    assert r.status_code == 401

    # Con sesión de admin → libera y el operario puede volver a entrar
    assert admin_client.post(f'/api/operarios/logins/{login_id}/liberar').get_json()['success']
    assert _login(client).get_json()['success']
