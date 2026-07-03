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
    with open(ruta, 'w') as f:
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
