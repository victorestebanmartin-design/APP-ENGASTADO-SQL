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
