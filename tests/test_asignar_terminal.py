"""Regresion: asignar un terminal que quedo atado a una maquina eliminada.

Eliminar una maquina es un borrado suave (activo=0) que dejaba sus filas de
maquinas_terminales. La lista de Terminales (solo maquinas activas) lo
enseñaba como "sin asignar", pero /api/asignar-terminal veia la fila vieja y
respondia 400 "ya asignado"; la UI ignoraba la respuesta y decia "asignado
correctamente" sin que cambiara nada.
"""


def _puesto_y_maquinas(admin_client):
    r = admin_client.post('/api/puestos', json={'nombre': 'P1', 'descripcion': ''})
    puesto_id = r.get_json()['puesto']['id']
    ids = []
    for nombre in ('M-VIEJA', 'M-NUEVA'):
        r = admin_client.post('/api/maquinas', json={'puesto_id': puesto_id, 'nombre': nombre})
        ids.append(r.get_json()['maquina']['id'])
    return ids


def _asignados(admin_client, maquina_id):
    maquinas = admin_client.get('/api/maquinas').get_json()['maquinas']
    return next(m for m in maquinas if m['id'] == maquina_id)['terminales_asignados']


def test_terminal_de_maquina_eliminada_se_puede_reasignar(admin_client):
    vieja, nueva = _puesto_y_maquinas(admin_client)
    r = admin_client.post('/api/asignar-terminal', json={'terminal': 'TX-641', 'maquina_id': vieja})
    assert r.get_json()['success']

    assert admin_client.delete(f'/api/maquinas/{vieja}').get_json()['success']

    r = admin_client.post('/api/asignar-terminal', json={'terminal': 'TX-641', 'maquina_id': nueva})
    assert r.status_code == 200 and r.get_json()['success']
    assert _asignados(admin_client, nueva) == ['TX-641']


def test_fila_huerfana_preexistente_no_bloquea(admin_client, app):
    """BD ya sucia (filas de maquinas inactivas de antes del arreglo)."""
    from sqlalchemy import text
    from app.routes.base import db
    vieja, nueva = _puesto_y_maquinas(admin_client)
    with app.app_context():
        db.session.execute(text("UPDATE maquinas SET activo = 0 WHERE id = :i"), {'i': vieja})
        db.session.execute(text(
            "INSERT INTO maquinas_terminales (maquina_id, terminal_codigo, activo) VALUES (:m, 'T9', 1)"),
            {'m': vieja})
        db.session.commit()

    r = admin_client.post('/api/asignar-terminal', json={'terminal': 'T9', 'maquina_id': nueva})
    assert r.get_json()['success'], r.get_json()
    assert _asignados(admin_client, nueva) == ['T9']


def test_terminal_en_maquina_activa_sigue_rechazado(admin_client):
    a, b = _puesto_y_maquinas(admin_client)
    assert admin_client.post('/api/asignar-terminal', json={'terminal': 'T1', 'maquina_id': a}).get_json()['success']
    r = admin_client.post('/api/asignar-terminal', json={'terminal': 'T1', 'maquina_id': b})
    assert r.status_code == 400 and not r.get_json()['success']
    assert _asignados(admin_client, a) == ['T1']


# ── Un terminal NO puede estar en dos maquinas activas ───────────────────────

def test_repositorio_rechaza_duplicar_terminal(admin_client, app):
    """El guardia esta en el repositorio, no solo en el endpoint."""
    import pytest
    from repositories.maquina_repository import MaquinaRepository, TerminalYaAsignadoError
    from app.routes.base import db
    a, b = _puesto_y_maquinas(admin_client)
    with app.app_context():
        repo = MaquinaRepository(db)
        assert repo.asignar_terminal(a, 'TDUP') is True
        assert repo.asignar_terminal(a, 'TDUP') is True      # idempotente en la misma
        with pytest.raises(TerminalYaAsignadoError) as exc:
            repo.asignar_terminal(b, 'TDUP')
        assert 'M-VIEJA' in str(exc.value)
        assert repo.obtener_terminales_asignados(b) == []


def test_endpoint_menciona_la_maquina_que_ya_lo_tiene(admin_client):
    a, b = _puesto_y_maquinas(admin_client)
    admin_client.post('/api/asignar-terminal', json={'terminal': 'TDUP2', 'maquina_id': a})
    r = admin_client.post('/api/asignar-terminal', json={'terminal': 'TDUP2', 'maquina_id': b})
    assert r.status_code == 400
    assert 'M-VIEJA' in r.get_json()['message']


def test_asignacion_masiva_informa_cual_falla(admin_client):
    """Asignacion rapida = N llamadas; las que chocan dan 400 y el resto se guardan."""
    a, b = _puesto_y_maquinas(admin_client)
    admin_client.post('/api/asignar-terminal', json={'terminal': 'TM2', 'maquina_id': a})
    resultados = {}
    for t in ('TM1', 'TM2', 'TM3'):
        r = admin_client.post('/api/asignar-terminal', json={'terminal': t, 'maquina_id': b})
        resultados[t] = (r.status_code, r.get_json()['message'])
    assert resultados['TM1'][0] == 200 and resultados['TM3'][0] == 200
    assert resultados['TM2'][0] == 400 and 'M-VIEJA' in resultados['TM2'][1]
    assert _asignados(admin_client, b) == ['TM1', 'TM3']


def test_asignar_a_maquina_inexistente_es_404(admin_client):
    r = admin_client.post('/api/asignar-terminal', json={'terminal': 'TX', 'maquina_id': 'no_existe'})
    assert r.status_code == 404


def test_editar_maquina_no_toca_terminales(admin_client):
    """PUT /api/maquinas/<id> no acepta lista de terminales: no es camino de escritura."""
    a, b = _puesto_y_maquinas(admin_client)
    admin_client.post('/api/asignar-terminal', json={'terminal': 'TE1', 'maquina_id': a})
    admin_client.put(f'/api/maquinas/{b}', json={'nombre': 'X', 'terminales_asignados': ['TE1']})
    assert _asignados(admin_client, b) == []
    assert _asignados(admin_client, a) == ['TE1']


def test_seed_no_duplica_un_terminal_que_el_admin_movio(admin_client, app):
    """El seed corre en cada arranque con INSERT OR IGNORE: no puede reinsertar
    el par original si el terminal ya esta en otra maquina activa."""
    import json
    import os
    from sqlalchemy import text
    from repositories import init_db
    base = app.config.get('BASE_DIR') or os.getcwd()
    with open(os.path.join(base, 'seed_inicial.json'), encoding='utf-8') as f:
        par = json.load(f)['maquinas_terminales'][0]
    admin_client.post('/api/desasignar-terminal', json={'terminal': par['terminal_codigo']})
    _, nueva = _puesto_y_maquinas(admin_client)
    r = admin_client.post('/api/asignar-terminal',
                          json={'terminal': par['terminal_codigo'], 'maquina_id': nueva})
    assert r.get_json()['success']
    from flask import Flask
    reinicio = Flask('reinicio')           # app nueva: la real ya atendio peticiones
    reinicio.config.update(app.config)
    nuevo_db = init_db(reinicio)           # simula un reinicio del servidor
    with nuevo_db.engine.connect() as conn:
        filas = conn.execute(text(
            "SELECT COUNT(*) FROM maquinas_terminales mt JOIN maquinas m ON m.id = mt.maquina_id "
            "WHERE mt.terminal_codigo = :t AND mt.activo = 1 AND m.activo = 1"),
            {'t': par['terminal_codigo']}).scalar()
    assert filas == 1
