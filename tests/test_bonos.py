"""Tests del flujo de bonos: crear, duplicados, órdenes, carros y borrado."""


def _crear_orden(client, numero='ORD_1'):
    r = client.post('/api/ordenes', json={
        'codigo_corte': 'COD_TEST',
        'numero': numero,
        'cantidad': 2,
    })
    assert r.get_json()['success']
    return r.get_json()['orden']


def test_crear_bono_vacio(client):
    r = client.post('/api/bonos', json={'nombre': 'B_VACIO', 'ordenes_ids': []})
    d = r.get_json()
    assert r.status_code == 200 and d['success']
    assert d['bono']['nombre'] == 'B_VACIO'
    assert d['bono']['ordenes'] == []
    assert d['bono']['carro_numero'] is None


def test_crear_bono_con_ordenes(client):
    _crear_orden(client, 'ORD_B1')
    r = client.post('/api/bonos', json={'nombre': 'B_CON_ORDEN', 'ordenes_ids': ['ORD_B1']})
    d = r.get_json()
    assert r.status_code == 200
    assert len(d['bono']['ordenes']) == 1
    assert d['bono']['ordenes'][0]['numero'] == 'ORD_B1'


def test_bono_duplicado_devuelve_409(client):
    client.post('/api/bonos', json={'nombre': 'B_DUP', 'ordenes_ids': []})
    r = client.post('/api/bonos', json={'nombre': 'B_DUP', 'ordenes_ids': []})
    assert r.status_code == 409
    assert 'Ya existe un bono' in r.get_json()['message']


def test_asignar_bono_a_carro(client):
    r = client.post('/api/bonos', json={'nombre': 'B_CARRO', 'ordenes_ids': []})
    bono_id = r.get_json()['bono']['id']

    r = client.put(f'/api/bonos/{bono_id}/carro', json={'carro_numero': 2})
    d = r.get_json()
    assert r.status_code == 200 and d['success']
    assert d['bono']['carro_numero'] == 2
    assert d['bono']['carros_asignados'] == [2]

    # El carro queda reflejado también en /api/carros
    r = client.get('/api/carros/2')
    carro = r.get_json()['carro']
    assert carro['bono_id'] == bono_id
    assert carro['estado'] == 'en_proceso'


def test_asignar_carro_marca_ordenes_en_proceso(client):
    _crear_orden(client, 'ORD_B2')
    r = client.post('/api/bonos', json={'nombre': 'B_ORDENES', 'ordenes_ids': ['ORD_B2']})
    bono_id = r.get_json()['bono']['id']

    client.put(f'/api/bonos/{bono_id}/carro', json={'carro_numero': 4})

    r = client.get('/api/bonos/B_ORDENES')
    ordenes = r.get_json()['bono']['ordenes']
    assert ordenes[0]['estado'] == 'en_proceso'
    assert ordenes[0]['carro_numero'] == 4


def test_eliminar_bono_devuelve_ordenes_a_pendiente(client):
    _crear_orden(client, 'ORD_B3')
    client.post('/api/bonos', json={'nombre': 'B_BORRAR', 'ordenes_ids': ['ORD_B3']})

    r = client.delete('/api/bonos/B_BORRAR')
    assert r.get_json()['success']

    r = client.get('/api/bonos/B_BORRAR')
    assert r.status_code == 404

    # La orden vuelve a pendiente y sin bono
    r = client.get('/api/ordenes/listar')
    orden = next(o for o in r.get_json()['ordenes'] if o['numero'] == 'ORD_B3')
    assert orden['estado'] == 'pendiente'
    assert orden['bono_id'] is None


def test_nombre_sugerido_incrementa(client):
    r = client.get('/api/bonos/nombre-sugerido')
    nombre1 = r.get_json()['nombre']
    assert nombre1.endswith('_1')

    client.post('/api/bonos', json={'nombre': nombre1, 'ordenes_ids': []})
    r = client.get('/api/bonos/nombre-sugerido')
    assert r.get_json()['nombre'].endswith('_2')
