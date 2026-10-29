"""Asistente «Generar bono» (operarios con permiso «bonos») y liberación
automática de carros cuando el bono queda finalizado."""
import json
import sqlite3

import pytest


@pytest.fixture
def operario(client, app):
    """Sesión de operario con el permiso «bonos» y tres órdenes pendientes."""
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("INSERT INTO operarios (id, nombre, modulos_permitidos) "
                     "VALUES ('op-b', 'Bea', ?)", (json.dumps(['mangueras', 'bonos']),))
        conn.execute("INSERT INTO operario_logins (id, operario_nombre, timestamp_login, ultimo_latido, activo, modulo) "
                     "VALUES ('login-b', 'Bea', datetime('now'), datetime('now'), 1, 'mangueras')")
        for i in (1, 2, 3, 4):
            conn.execute("INSERT INTO ordenes_produccion (id, codigo_corte, numero, cantidad, archivo_excel) "
                         "VALUES (?, 'H1', ?, 1, 'corte.xlsx')", (f'o{i}', f'600{i}'))
        # o1..o3 con mangueras y manguitos terminados; o4 sin terminar.
        for i in (1, 2, 3):
            for tabla in ('mangueras_preparaciones', 'manguitos_colocaciones'):
                conn.execute(f"INSERT INTO {tabla} (orden_id, inicio, fin) VALUES (?, 'a', 'b')", (f'o{i}',))
    with client.session_transaction() as sesion:
        sesion['operario_actual'] = 'Bea'
        sesion['operario_login_id'] = 'login-b'
    return client


def _crear(client, pares):
    return client.post('/api/bonos/asistente/crear',
                       json={'carros': [{'carro': c, 'orden_id': o} for c, o in pares]})


def test_sin_permiso_bonos_403_y_nunca_por_defecto(client, app):
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        # Sin permisos explícitos (NULL): tiene todo menos admin y bonos.
        conn.execute("INSERT INTO operarios (id, nombre) VALUES ('op-x', 'Xavi')")
        conn.execute("INSERT INTO operario_logins (id, operario_nombre, timestamp_login, ultimo_latido, activo, modulo) "
                     "VALUES ('login-x', 'Xavi', datetime('now'), datetime('now'), 1, 'mangueras')")
    with client.session_transaction() as sesion:
        sesion['operario_actual'] = 'Xavi'
        sesion['operario_login_id'] = 'login-x'
    r = client.get('/api/bonos/asistente/estado')
    assert r.status_code == 403
    assert r.get_json()['consejo']


def test_sin_sesion_401(client):
    assert client.get('/api/bonos/asistente/estado').status_code == 401


def test_estado_lista_seis_carros_y_nombre(operario):
    d = operario.get('/api/bonos/asistente/estado').get_json()
    assert [c['numero'] for c in d['carros']] == [1, 2, 3, 4, 5, 6]
    assert all(c['libre'] for c in d['carros'])
    assert d['nombre_sugerido'].startswith('0000001_')


def test_orden_codigo_invalido_o_inexistente(operario):
    assert operario.post('/api/bonos/asistente/orden', json={'codigo': 'basura'}).status_code == 400
    r = operario.post('/api/bonos/asistente/orden', json={'codigo': 'H1-9999-1'})
    assert r.status_code == 409 and 'no está registrada' in r.get_json()['error']
    # Misma orden pero cantidad distinta a la registrada
    assert operario.post('/api/bonos/asistente/orden', json={'codigo': 'H1-6001-5'}).status_code == 409
    d = operario.post('/api/bonos/asistente/orden', json={'codigo': 'H1-6001-1'}).get_json()
    assert d['success'] and d['orden']['id'] == 'o1'


def test_crear_bono_ocupa_carros_y_ordenes(operario, app):
    r = _crear(operario, [(2, 'o1'), (5, 'o2')])
    assert r.status_code == 200, r.get_json()
    nombre = r.get_json()['bono']['nombre']
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute("SELECT estado FROM carros WHERE numero IN (2,5)").fetchall() == [('en_proceso',)] * 2
        assert conn.execute("SELECT numeracion_carros FROM bonos WHERE nombre=?", (nombre,)).fetchone() == ('fisica',)
        assert conn.execute("SELECT estado, carro_numero FROM ordenes_produccion WHERE id='o2'").fetchone() == ('en_bono', 5)
    libres = {c['numero']: c['libre'] for c in operario.get('/api/bonos/asistente/estado').get_json()['carros']}
    assert libres == {1: True, 2: False, 3: True, 4: True, 5: False, 6: True}
    # Mismo carro u orden otra vez: 409 con motivo
    assert _crear(operario, [(2, 'o3')]).status_code == 409
    assert _crear(operario, [(3, 'o1')]).status_code == 409


def test_crear_valida_la_peticion(operario):
    assert _crear(operario, []).status_code == 400
    assert _crear(operario, [(7, 'o1')]).status_code == 400
    assert _crear(operario, [(1, 'o1'), (1, 'o2')]).status_code == 400
    assert _crear(operario, [(1, 'o1'), (2, 'o1')]).status_code == 400


def test_finalizar_el_bono_libera_los_carros(operario, app, monkeypatch):
    nombre = _crear(operario, [(1, 'o1'), (2, 'o2')]).get_json()['bono']['nombre']
    from app.routes import progreso

    # Aún no finalizado: terminal completado, pero el bono sigue vivo.
    monkeypatch.setattr(progreso, '_bono_finalizado', lambda n, terminales=None: False)
    r = operario.post(f'/api/bonos/{nombre}/progreso/estado', json={'terminal': 'T1', 'estado': 'completado'})
    assert r.get_json()['carros_liberados'] == []
    assert not any(c['libre'] for c in operario.get('/api/bonos/asistente/estado').get_json()['carros'][:2])

    monkeypatch.setattr(progreso, '_bono_finalizado', lambda n, terminales=None: True)
    r = operario.post(f'/api/bonos/{nombre}/progreso/estado', json={'terminal': 'T2', 'estado': 'completado'})
    assert r.get_json()['carros_liberados'] == [1, 2]
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute("SELECT estado, bono_id FROM carros WHERE numero=1").fetchone() == ('disponible', None)
        assert conn.execute("SELECT estado FROM bonos WHERE nombre=?", (nombre,)).fetchone() == ('completado',)
        # La orden conserva su carro para los reports.
        assert conn.execute("SELECT estado, carro_numero FROM ordenes_produccion WHERE id='o1'").fetchone() == ('completado', 1)
    # Idempotente, y los carros vuelven a admitir otro bono.
    r = operario.post(f'/api/bonos/{nombre}/progreso/estado', json={'terminal': 'T2', 'estado': 'completado'})
    assert r.get_json()['carros_liberados'] == []
    assert _crear(operario, [(1, 'o3')]).status_code == 200


def test_el_boton_sale_en_la_pantalla_principal_compartida_y_solo_con_permiso(operario, app):
    import os
    with app.app_context():
        with open(os.path.join(app.config['DATA_DIR'], 'operario_gate.json'), 'w', encoding='utf-8') as f:
            json.dump({'enabled': True}, f)
    operario.post('/api/pc/configurar', json={'modulo': 'manguitos_mangueras'})
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("UPDATE operarios SET modulos_permitidos=?", (json.dumps(['mangueras', 'manguitos', 'bonos']),))
        conn.execute("UPDATE operario_logins SET modulo='manguitos_mangueras'")
    html = operario.get('/modules').get_data(as_text=True)
    assert 'id="ab-abrir"' in html and 'id="ab-modal"' in html
    # Dentro de los módulos ya no sale.
    for ruta in ('/mangueras', '/manguitos'):
        assert 'ab-abrir' not in operario.get(ruta).get_data(as_text=True), ruta
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("UPDATE operarios SET modulos_permitidos=?", (json.dumps(['mangueras', 'manguitos']),))
    assert 'ab-abrir' not in operario.get('/modules').get_data(as_text=True)


def _fase(app, tabla, orden_id, fin):
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute(f"INSERT OR REPLACE INTO {tabla} (orden_id, inicio, fin) VALUES (?, 'a', ?)", (orden_id, fin))


def test_orden_sin_fases_terminadas_no_entra_a_carro(operario, app):
    # o4: ni mangueras ni manguitos
    r = operario.post('/api/bonos/asistente/orden', json={'codigo': 'H1-6004-1'})
    assert r.status_code == 409 and 'mangueras' in r.get_json()['error'] and 'manguitos' in r.get_json()['error']
    # Mangueras terminada pero manguitos solo empezada (fin NULL)
    _fase(app, 'mangueras_preparaciones', 'o4', 'b')
    _fase(app, 'manguitos_colocaciones', 'o4', None)
    r = operario.post('/api/bonos/asistente/orden', json={'codigo': 'H1-6004-1'})
    assert r.status_code == 409
    assert 'manguitos' in r.get_json()['error'] and 'mangueras' not in r.get_json()['error']
    assert _crear(operario, [(1, 'o4')]).status_code == 409
    _fase(app, 'manguitos_colocaciones', 'o4', 'b')
    assert operario.post('/api/bonos/asistente/orden', json={'codigo': 'H1-6004-1'}).get_json()['success']
    assert _crear(operario, [(1, 'o4')]).status_code == 200


def test_asignacion_manual_tambien_exige_las_fases(operario, app):
    r = operario.post('/api/carros/asignar-orden', json={'orden_id': 'o4', 'numero_carro': 2})
    assert r.status_code == 409 and 'Termínala' in r.get_json()['message']
    assert operario.post('/api/carros/asignar-orden', json={'orden_id': 'o1', 'numero_carro': 2}).status_code == 200


def test_listado_de_ordenes_lleva_el_check(operario):
    por_id = {o['id']: o for o in operario.get('/api/ordenes/listar').get_json()['ordenes']}
    assert por_id['o1']['fases_completas'] is True
    assert por_id['o4']['fases_completas'] is False and por_id['o4']['mangueras_terminada'] is False


def test_borrar_el_bono_libera_los_carros(operario, app):
    nombre = _crear(operario, [(1, 'o1'), (2, 'o2')]).get_json()['bono']['nombre']
    assert operario.delete(f'/api/bonos/{nombre}').get_json()['success']
    carros = operario.get('/api/bonos/asistente/estado').get_json()['carros']
    assert all(c['libre'] for c in carros)
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute("SELECT estado, carro_numero, bono_id FROM ordenes_produccion WHERE id='o1'").fetchone() \
            == ('pendiente', None, None)


def test_liberar_carro_atascado(operario, app):
    _crear(operario, [(3, 'o1')])
    ruta = '/api/bonos/asistente/liberar-carro'
    assert operario.post(ruta, json={'carro': 3}).status_code == 400          # sin confirmar
    assert operario.post(ruta, json={'carro': 9, 'confirmar': True}).status_code == 400
    r = operario.post(ruta, json={'carro': 3, 'confirmar': True})
    assert r.status_code == 200 and r.get_json()['success']
    libres = {c['numero']: c['libre'] for c in operario.get('/api/bonos/asistente/estado').get_json()['carros']}
    assert libres[3] is True
    # Puede volver a ocuparse con otra orden
    assert _crear(operario, [(3, 'o2')]).status_code == 200
