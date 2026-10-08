"""Tests del CRUD de órdenes de producción."""


def test_crear_y_listar_orden(client):
    r = client.post('/api/ordenes', json={
        'codigo_corte': 'COD_A',
        'numero': 'ORD_100',
        'descripcion': 'prueba',
        'cantidad': 3,
    })
    d = r.get_json()
    assert d['success']
    assert d['orden']['numero'] == 'ORD_100'
    assert d['orden']['cantidad'] == 3
    # No hay código de corte registrado, así que no encuentra archivo
    assert d['archivo_encontrado'] is False

    r = client.get('/api/ordenes/listar')
    numeros = [o['numero'] for o in r.get_json()['ordenes']]
    assert 'ORD_100' in numeros


def test_actualizar_orden(client):
    r = client.post('/api/ordenes', json={'codigo_corte': 'COD_A', 'numero': 'ORD_101', 'cantidad': 1})
    orden_id = r.get_json()['orden']['id']

    r = client.put(f'/api/ordenes/actualizar/{orden_id}', json={'cantidad': 9, 'prioridad': 'alta'})
    d = r.get_json()
    assert d['success']
    assert d['orden']['cantidad'] == 9
    assert d['orden']['prioridad'] == 'alta'


def test_eliminar_orden(client):
    r = client.post('/api/ordenes', json={'codigo_corte': 'COD_A', 'numero': 'ORD_102', 'cantidad': 1})
    orden_id = r.get_json()['orden']['id']

    r = client.delete(f'/api/ordenes/eliminar/{orden_id}')
    assert r.get_json()['success']

    r = client.delete(f'/api/ordenes/eliminar/{orden_id}')
    assert r.status_code == 404


def test_orden_hereda_archivo_del_codigo_corte(admin_client, app):
    import os
    # Registrar un código de corte apuntando a un Excel existente
    ruta = os.path.join(app.config['UPLOAD_FOLDER'], 'corte_test.xlsx')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write('x')
    r = admin_client.post('/api/add_corte', json={
        'codigo_barras': 'CODBAR1',
        'archivo': 'corte_test.xlsx',
    })
    assert r.get_json()['success']

    # La orden creada con ese código hereda el archivo
    r = admin_client.post('/api/ordenes', json={'codigo_corte': 'CODBAR1', 'numero': 'ORD_103'})
    d = r.get_json()
    assert d['archivo_encontrado'] is True
    assert d['orden']['archivo_excel'] == 'corte_test.xlsx'


def test_cambiar_numero_renombra_proyecto_y_mantiene_vinculos(client, app):
    """Cambiar el número de una orden en un bono no rompe bono, progreso ni proyecto."""
    import app.routes.ordenes as mod
    from sqlalchemy import text
    from repositories.proyecto_repository import ProyectoRepository

    orden = client.post('/api/ordenes', json={
        'codigo_corte': 'COD_R', 'numero': 'ORD_R1', 'cantidad': 1}).get_json()['orden']
    with mod.db.engine.begin() as conn:
        conn.execute(text("UPDATE ordenes_produccion SET archivo_excel='r.xlsx' WHERE id=:i"),
                     {'i': orden['id']})
    client.post('/api/bonos', json={'nombre': 'B_RENUM', 'ordenes_ids': ['ORD_R1']})
    repo = ProyectoRepository(mod.db)
    pid = repo.crear_proyecto('ORD_R1 - COD_R', 'r.xlsx')
    otro = repo.crear_proyecto('ORD_R1 - COD_R', 'otro.xlsx')  # otra orden con mismo número viejo

    r = client.put(f"/api/ordenes/actualizar/{orden['id']}", json={'numero': ' ORD_R2 '})
    assert r.get_json()['success']
    assert r.get_json()['orden']['numero'] == 'ORD_R2'
    assert repo.obtener_proyecto(pid)['nombre'] == 'ORD_R2 - COD_R'
    assert repo.obtener_proyecto(otro)['nombre'] == 'ORD_R1 - COD_R'

    # La orden sigue dentro del bono y el bono la muestra con el número nuevo
    d = client.get('/api/bonos/B_RENUM').get_json()['bono']
    assert [o['numero'] for o in d['ordenes']] == ['ORD_R2']
    assert d['ordenes'][0]['bono_id'] == d['id']
    assert d['carros'][0]['proyecto_nombre'] == 'ORD_R2'


def test_numero_duplicado_o_vacio_se_rechaza(client):
    a = client.post('/api/ordenes', json={'codigo_corte': 'C', 'numero': 'ORD_D1'}).get_json()['orden']
    client.post('/api/ordenes', json={'codigo_corte': 'C', 'numero': 'ORD_D2'})

    r = client.put(f"/api/ordenes/actualizar/{a['id']}", json={'numero': 'ORD_D2'})
    assert r.status_code == 409
    r = client.put(f"/api/ordenes/actualizar/{a['id']}", json={'numero': '  '})
    assert r.status_code == 400
    # Mismo número que ya tiene: no es duplicado
    r = client.put(f"/api/ordenes/actualizar/{a['id']}", json={'numero': 'ORD_D1', 'cantidad': 4})
    assert r.get_json()['success']
