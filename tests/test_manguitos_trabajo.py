import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

CODIGO = 'H0174891-60238442-1'


@pytest.fixture
def operario(client, app):
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("INSERT INTO operarios (id, nombre) VALUES ('op-mg', 'Ana')")
        conn.execute("INSERT INTO operario_logins (id, operario_nombre, timestamp_login, ultimo_latido, activo, modulo) VALUES ('login-mg', 'Ana', datetime('now'), datetime('now'), 1, 'manguitos')")
        conn.execute("INSERT INTO codigos_cortes (codigo, archivo_excel, activo) VALUES ('H0174891', 'corte.xlsx', 1)")
    with client.session_transaction() as sesion:
        sesion['operario_actual'] = 'Ana'
        sesion['operario_login_id'] = 'login-mg'
    return client


@pytest.fixture
def reloj(monkeypatch):
    from app.routes import mangueras_trabajo, manguitos_trabajo
    instantes = [datetime(2026, 10, 14, 8, tzinfo=timezone.utc)]

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return instantes[0]

    monkeypatch.setattr(mangueras_trabajo, 'datetime', Reloj)
    monkeypatch.setattr(manguitos_trabajo, 'datetime', Reloj)
    return instantes


def test_sin_mangueras_preparadas_pide_prepararlas_primero(operario, app):
    respuesta = operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO})
    assert respuesta.status_code == 409
    assert 'preparar las mangueras' in respuesta.get_json()['error']
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT count(*) FROM ordenes_produccion').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM manguitos_tramos').fetchone()[0] == 0


def test_con_mangueras_iniciadas_cuenta_el_tiempo_y_termina(operario, app, reloj):
    orden = operario.post('/api/mangueras/trabajo/escanear', json={'codigo': CODIGO}).get_json()['orden']
    operario.post('/api/mangueras/trabajo/' + orden['id'], json={'accion': 'pausar'})
    reloj[0] += timedelta(seconds=10)
    primera = operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO})
    assert primera.status_code == 200
    assert primera.get_json()['orden']['id'] == orden['id']
    reloj[0] += timedelta(seconds=75)
    fin = operario.post('/api/manguitos/trabajo/' + orden['id'], json={'accion': 'terminar'}).get_json()['colocacion']
    assert fin['segundos'] == 75
    assert fin['estado'] == 'terminada'
    assert fin['operarios'] == ['Ana']
    assert operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO}).status_code == 409


def test_cantidad_distinta_no_se_acepta(operario):
    operario.post('/api/mangueras/trabajo/escanear', json={'codigo': CODIGO})
    assert operario.post('/api/manguitos/trabajo/escanear', json={'codigo': 'H0174891-60238442-2'}).status_code == 409


def test_pausar_y_abandono_no_cuentan_tiempo_sin_latidos(operario, reloj):
    orden = operario.post('/api/mangueras/trabajo/escanear', json={'codigo': CODIGO}).get_json()['orden']
    operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO})
    reloj[0] += timedelta(seconds=30)
    operario.post('/api/manguitos/trabajo/' + orden['id'], json={'accion': 'latido'})
    reloj[0] += timedelta(hours=1)
    resumen = operario.get('/api/manguitos/trabajo/' + orden['id']).get_json()['colocacion']
    assert resumen['segundos'] == 30
    assert resumen['estado'] == 'pausada'


def test_cerrar_sesion_cierra_tramo_de_manguitos(operario, app, reloj):
    orden = operario.post('/api/mangueras/trabajo/escanear', json={'codigo': CODIGO}).get_json()['orden']
    operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO})
    reloj[0] += timedelta(seconds=40)
    assert operario.post('/api/sesion/operario/salir').status_code == 200
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT count(*) FROM manguitos_tramos WHERE fin IS NULL').fetchone()[0] == 0


def test_sin_identidad_y_sin_permiso(operario, app):
    assert app.test_client().post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO}).status_code == 401
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("UPDATE operarios SET modulos_permitidos='[]' WHERE id='op-mg'")
    assert operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO}).status_code == 403


def _tramo(conn, tabla, orden_id, login, segundos, fin=True):
    inicio = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)
    conn.execute(
        f"INSERT INTO {tabla} (orden_id, login_id, operario_id, operario_nombre, inicio, ultimo_latido, fin) "
        "VALUES (?, ?, 'op-mg', 'Ana', ?, ?, ?)",
        (orden_id, login, inicio.isoformat(), (inicio + timedelta(seconds=segundos)).isoformat(),
         (inicio + timedelta(seconds=segundos)).isoformat() if fin else None))


def test_tiempos_media_solo_con_fases_acabadas(client, app):
    ruta = app.config['DB_PATH']
    inicio = '2026-10-14T08:00:00+00:00'
    with sqlite3.connect(ruta) as conn:
        conn.execute("INSERT INTO bonos (id, nombre) VALUES ('b1', 'BONO1')")
        # A: mangueras y manguitos terminados por el operario (100 s y 50 s)
        # B: mangueras a medias, sin engastado -> no entra
        # C: mangueras a medias pero el bono ya engasto algo en su carro -> entra
        # D: de antes del sistema (sin filas) -> no sale
        for oid, numero, cantidad, bono in (('a', '1', 2, None), ('b', '2', 1, None), ('c', '3', 1, 'b1'), ('d', '4', 1, None)):
            conn.execute("INSERT INTO ordenes_produccion (id, codigo_corte, numero, cantidad, bono_id) VALUES (?, 'H1', ?, ?, ?)",
                         (oid, numero, cantidad, bono))
        for oid, fin in (('a', inicio), ('b', None), ('c', None)):
            conn.execute('INSERT INTO mangueras_preparaciones (orden_id, inicio, fin) VALUES (?, ?, ?)', (oid, inicio, fin))
        conn.execute('INSERT INTO manguitos_colocaciones (orden_id, inicio, fin) VALUES (?, ?, ?)', ('a', inicio, inicio))
        _tramo(conn, 'mangueras_tramos', 'a', 'l1', 100)
        _tramo(conn, 'mangueras_tramos', 'b', 'l2', 999)
        _tramo(conn, 'mangueras_tramos', 'c', 'l3', 200)
        _tramo(conn, 'manguitos_tramos', 'a', 'l4', 50)
    with open(os.path.join(app.config['DATA_DIR'], 'progreso_bono_BONO1.json'), 'w', encoding='utf-8') as f:
        json.dump({'T1': {'carros_completados': [1]}}, f)

    datos = client.get('/api/ordenes/tiempos').get_json()
    por_numero = {o['numero']: o for o in datos['ordenes']}
    assert set(por_numero) == {'1', '2', '3'}
    assert por_numero['1']['mangueras']['estado'] == 'terminada'
    assert por_numero['2']['mangueras']['estado'] == 'pausada'
    assert por_numero['2']['mangueras']['cuenta'] is False
    assert por_numero['3']['mangueras']['estado'] == 'terminada_auto'
    assert por_numero['3']['engastado_iniciado'] is True
    assert por_numero['3']['manguitos'] is None
    mangueras = datos['medias']['mangueras']
    assert mangueras['ordenes'] == 2
    assert mangueras['media_segundos'] == 150
    assert mangueras['segundos_por_unidad'] == 100  # 300 s entre 3 unidades
    assert datos['medias']['manguitos']['media_segundos'] == 50
    assert datos['medias']['total'] == {'ordenes': 1, 'media_segundos': 150}


def test_pagina_de_tiempos_carga(client):
    assert client.get('/ordenes/tiempos').status_code == 200


def test_pausa_por_inactividad_descuenta_los_minutos_sin_actividad(operario, reloj):
    orden = operario.post('/api/mangueras/trabajo/escanear', json={'codigo': CODIGO}).get_json()['orden']
    operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO})
    for _ in range(20):  # la pagina late cada 30 s mientras el reloj corre
        reloj[0] += timedelta(seconds=30)
        operario.post('/api/manguitos/trabajo/' + orden['id'], json={'accion': 'latido'})
    resumen = operario.post('/api/manguitos/trabajo/' + orden['id'],
                            json={'accion': 'pausar', 'inactivo_segundos': 320}).get_json()['colocacion']
    assert resumen['segundos'] == 280
    # Un descuento mayor que el propio tramo nunca da tiempo negativo
    operario.post('/api/manguitos/trabajo/escanear', json={'codigo': CODIGO})
    reloj[0] += timedelta(seconds=30)
    resumen = operario.post('/api/manguitos/trabajo/' + orden['id'],
                            json={'accion': 'pausar', 'inactivo_segundos': 3000}).get_json()['colocacion']
    assert resumen['segundos'] == 280
