import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def preparador(client, app):
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("INSERT INTO operarios (id, nombre) VALUES ('op-mg', 'Ana')")
        conn.execute("INSERT INTO operario_logins (id, operario_nombre, timestamp_login, ultimo_latido, activo, modulo) VALUES ('login-mg', 'Ana', datetime('now'), datetime('now'), 1, 'mangueras')")
        conn.execute("INSERT INTO codigos_cortes (codigo, archivo_excel, activo) VALUES ('H0174891', 'corte.xlsx', 1)")
    with client.session_transaction() as sesion:
        sesion['operario_actual'] = 'Ana'
        sesion['operario_login_id'] = 'login-mg'
    return client


def test_escaneo_registra_orden_y_relectura_no_duplica(preparador, app):
    primera = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'})
    assert primera.status_code == 200
    datos = primera.get_json()
    assert datos['orden']['numero'] == '60238442'
    assert datos['orden']['cantidad'] == 1
    segunda = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'})
    assert segunda.get_json()['orden']['id'] == datos['orden']['id']
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT count(*) FROM ordenes_produccion').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM mangueras_tramos').fetchone()[0] == 1


@pytest.fixture
def reloj(monkeypatch):
    from app.routes import mangueras_trabajo
    instantes = [datetime(2026, 10, 14, 8, tzinfo=timezone.utc)]

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return instantes[0]

    monkeypatch.setattr(mangueras_trabajo, 'datetime', Reloj)
    return instantes


def test_reentrada_suma_solo_trabajo_y_finaliza_sin_sacar_del_pool(preparador, app, reloj):
    orden = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-3'}).get_json()['orden']
    reloj[0] += timedelta(seconds=60)
    assert preparador.post('/api/sesion/operario/salir').status_code == 200
    reloj[0] += timedelta(hours=1)
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("UPDATE operario_logins SET activo=1 WHERE id='login-mg'")
    with preparador.session_transaction() as sesion:
        sesion['operario_actual'] = 'Ana'
        sesion['operario_login_id'] = 'login-mg'
    assert preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-3'}).status_code == 200
    reloj[0] += timedelta(seconds=90)
    fin = preparador.post('/api/mangueras/trabajo/' + orden['id'], json={'accion': 'terminar'}).get_json()['preparacion']
    assert fin['segundos'] == 150
    assert fin['estado'] == 'terminada'
    assert len(fin['tramos']) == 2
    assert fin['fin'] == reloj[0].isoformat()
    # Terminada: deja volver a entrar, con aviso y sin abrir tramo nuevo.
    otra = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-3'})
    assert otra.status_code == 200
    assert 'ya estaba terminada' in otra.get_json()['aviso']
    assert otra.get_json()['preparacion']['estado'] == 'terminada'
    assert len(otra.get_json()['preparacion']['tramos']) == 2
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT estado FROM ordenes_produccion').fetchone()[0] == 'pendiente'


def test_distintos_operarios_conservan_sus_tramos(preparador, app, reloj):
    orden = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'}).get_json()['orden']
    reloj[0] += timedelta(seconds=30)
    preparador.post('/api/mangueras/trabajo/' + orden['id'], json={'accion': 'pausar'})
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("INSERT INTO operarios (id, nombre) VALUES ('op-luis', 'Luis')")
        conn.execute("INSERT INTO operario_logins (id, operario_nombre, timestamp_login, ultimo_latido, activo) VALUES ('login-luis', 'Luis', datetime('now'), datetime('now'), 1)")
    with preparador.session_transaction() as sesion:
        sesion['operario_actual'] = 'Luis'
        sesion['operario_login_id'] = 'login-luis'
    preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'})
    reloj[0] += timedelta(seconds=50)
    fin = preparador.post('/api/mangueras/trabajo/' + orden['id'], json={'accion': 'terminar'}).get_json()['preparacion']
    assert fin['operarios'] == ['Ana', 'Luis']
    assert [tramo['segundos'] for tramo in fin['tramos']] == [30, 50]


@pytest.mark.parametrize('codigo', ['H0174891', 'H0174891-60238442-0', 'H0174891-60238442--1', 'H0174891-60238442-1.5', 'DESCONOCIDO-60238442-1', None])
def test_codigo_invalido_no_registra_orden(preparador, app, codigo):
    assert preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': codigo}).status_code == 400
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT count(*) FROM ordenes_produccion').fetchone()[0] == 0


def test_conflicto_no_sobrescribe_orden(preparador, app):
    preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'})
    assert preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-2'}).status_code == 409
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT cantidad FROM ordenes_produccion').fetchone()[0] == 1


def test_sin_identidad_no_registra_orden(client):
    assert client.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'}).status_code == 401


def test_abandono_no_cuenta_tiempo_sin_latidos(preparador, reloj):
    orden = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'}).get_json()['orden']
    reloj[0] += timedelta(seconds=30)
    preparador.post('/api/mangueras/trabajo/' + orden['id'], json={'accion': 'latido'})
    reloj[0] += timedelta(hours=1)
    resumen = preparador.get('/api/mangueras/trabajo/' + orden['id']).get_json()['preparacion']
    assert resumen['segundos'] == 30
    assert resumen['estado'] == 'pausada'


def test_cambiar_orden_cierra_tramo_anterior(preparador, reloj):
    orden = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'}).get_json()['orden']
    reloj[0] += timedelta(seconds=20)
    assert preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238443-1'}).status_code == 200
    resumen = preparador.get('/api/mangueras/trabajo/' + orden['id']).get_json()['preparacion']
    assert resumen['segundos'] == 20
    assert resumen['estado'] == 'pausada'


def test_liberar_login_cierra_tramo(preparador, admin_client, reloj):
    orden = preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'}).get_json()['orden']
    reloj[0] += timedelta(seconds=45)
    assert admin_client.post('/api/operarios/logins/login-mg/liberar').status_code == 200
    reloj[0] += timedelta(hours=1)
    resumen = admin_client.get('/api/mangueras/trabajo/' + orden['id']).get_json()['preparacion']
    assert resumen['segundos'] == 45
    assert resumen['estado'] == 'pausada'


def test_permiso_y_origen_protegen_el_registro(preparador, app):
    assert preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'},
                          headers={'Origin': 'https://otro-sitio.invalid'}).status_code == 403
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("UPDATE operarios SET modulos_permitidos='[]' WHERE id='op-mg'")
    assert preparador.post('/api/mangueras/trabajo/escanear', json={'codigo': 'H0174891-60238442-1'}).status_code == 403