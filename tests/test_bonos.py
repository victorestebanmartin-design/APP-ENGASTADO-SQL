"""Tests del flujo de bonos: crear, duplicados, órdenes, carros y borrado."""
from datetime import datetime


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
    anio = datetime.now().year
    nombre1 = r.get_json()['nombre']
    assert nombre1 == f'0000001_{anio}'

    client.post('/api/bonos', json={'nombre': nombre1, 'ordenes_ids': []})
    r = client.get('/api/bonos/nombre-sugerido')
    assert r.get_json()['nombre'] == f'0000002_{anio}'


def test_nombre_sugerido_reinicia_por_anio_e_ignora_formato_antiguo(client):
    anio = datetime.now().year
    for n in ('27102025_9', f'0000041_{anio - 1}', f'0000005_{anio}'):
        client.post('/api/bonos', json={'nombre': n, 'ordenes_ids': []})
    r = client.get('/api/bonos/nombre-sugerido')
    assert r.get_json()['nombre'] == f'0000006_{anio}'


def test_listado_bonos_incluye_resumen_de_ordenes(client):
    _crear_orden(client, 'ORD_RES')
    client.post('/api/bonos', json={'nombre': 'B_RES', 'ordenes_ids': ['ORD_RES']})
    bono = next(b for b in client.get('/api/bonos').get_json()['bonos'] if b['nombre'] == 'B_RES')
    assert [o['numero'] for o in bono['ordenes_resumen']] == ['ORD_RES']


def _bono(client, nombre):
    r = client.post('/api/bonos', json={'nombre': nombre, 'ordenes_ids': []})
    assert r.get_json()['success']


def test_editar_bono_estado(client):
    _bono(client, 'B_EST')
    r = client.put('/api/bonos/B_EST', json={'nombre': 'B_EST', 'estado': 'pausado'})
    assert r.get_json()['success']
    assert client.get('/api/bonos/B_EST').get_json()['bono']['estado'] == 'pausado'


def test_renombrar_bono_mueve_el_progreso(client, app):
    import json, os
    _bono(client, 'B_VIEJO')
    cuerpo = {'terminal': 'T1', 'carro': 1}
    assert client.post('/api/bonos/B_VIEJO/progreso', json=cuerpo).get_json()['success']
    datos = app.config['DATA_DIR']
    viejo = os.path.join(datos, 'progreso_bono_B_VIEJO.json')
    assert os.path.exists(viejo)
    antes = json.load(open(viejo, encoding='utf-8'))

    r = client.put('/api/bonos/B_VIEJO', json={'nombre': 'B_NUEVO', 'estado': 'activo'})
    assert r.get_json()['success']
    assert not os.path.exists(viejo)
    nuevo = os.path.join(datos, 'progreso_bono_B_NUEVO.json')
    assert json.load(open(nuevo, encoding='utf-8')) == antes
    assert client.get('/api/bonos/B_NUEVO/progreso').get_json()['success']
    assert client.get('/api/bonos/B_VIEJO').status_code == 404


def test_renombrar_bono_rechaza_duplicado_y_nombres_raros(client):
    _bono(client, 'B_A')
    _bono(client, 'B_B')
    assert client.put('/api/bonos/B_A', json={'nombre': 'B_B', 'estado': 'activo'}).status_code == 409
    assert client.put('/api/bonos/B_A', json={'nombre': '../x', 'estado': 'activo'}).status_code == 400
    assert client.put('/api/bonos/B_A', json={'nombre': 'B_A', 'estado': 'en_proceso'}).status_code == 400
    assert client.put('/api/bonos/NO_EXISTE', json={'nombre': 'X'}).status_code == 404
    assert client.get('/api/bonos/B_A').status_code == 200


def _orden_en_carro(client, app, numero, carro):
    from sqlalchemy import text
    from app.routes.base import db
    orden = _crear_orden(client, numero)
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(text("UPDATE ordenes_produccion SET archivo_excel = 'corte.xlsx' WHERE id = :id"), {'id': orden['id']})
        for tabla in ('mangueras_preparaciones', 'manguitos_colocaciones'):
            conn.execute(text(f"INSERT INTO {tabla} (orden_id, inicio, fin) VALUES (:id, 'a', 'b')"), {'id': orden['id']})
    respuesta = client.post('/api/carros/asignar-orden', json={'orden_id': orden['id'], 'numero_carro': carro})
    assert respuesta.status_code == 200, respuesta.get_json()
    return orden, respuesta.get_json()['proyecto_id']


def test_asignacion_manual_rechaza_ocupados_y_orden_duplicada(client, app):
    orden, proyecto = _orden_en_carro(client, app, 'MANUAL_3', 3)
    assert client.post('/api/carros/asignar-orden', json={'orden_id': orden['id'], 'numero_carro': 3}).status_code == 409
    assert client.post('/api/carros/asignar-orden', json={'orden_id': orden['id'], 'numero_carro': 4}).status_code == 409
    carros = client.get('/api/carros').get_json()['carros']
    assert not carros[0]['ocupado'] and not carros[1]['ocupado']
    assert carros[2]['proyecto_id'] == proyecto
    assert carros[2]['proyecto_nombre'] == 'MANUAL_3 - COD_TEST'


def test_mover_intercambiar_y_liberar_ordenes(client, app):
    orden, proyecto = _orden_en_carro(client, app, 'MOV_3', 3)
    otra, otro_proyecto = _orden_en_carro(client, app, 'MOV_4', 4)
    ruta = '/api/carros/3/mover'
    assert client.post(ruta, json={'destino': 4, 'proyecto_id': proyecto}).status_code == 409
    assert client.post(ruta, json={'destino': 4, 'proyecto_id': proyecto, 'intercambiar': True}).status_code == 200
    assert client.get('/api/carros').get_json()['carros'][2]['proyecto_id'] == otro_proyecto
    assert client.post('/api/carros/4/mover', json={'destino': 6, 'proyecto_id': proyecto}).status_code == 200
    assert client.post('/api/carros/6/liberar').status_code == 200
    ordenes = {item['id']: item for item in client.get('/api/ordenes/listar').get_json()['ordenes']}
    assert ordenes[orden['id']]['estado'] == 'pendiente'
    assert ordenes[orden['id']]['carro_numero'] is None
    assert ordenes[otra['id']]['carro_numero'] == 3


def test_bono_selectivo_conserva_carros_fisicos_y_reserva(client, app):
    _orden_en_carro(client, app, 'QUEDA_1', 1)
    _orden_en_carro(client, app, 'BONO_3', 3)
    _orden_en_carro(client, app, 'BONO_4', 4)
    respuesta = client.post('/api/bonos/generar', json={'nombre': 'SOLO_3_4', 'carros': [3, 4]})
    assert respuesta.status_code == 200, respuesta.get_json()
    bono = client.get('/api/bonos/SOLO_3_4').get_json()['bono']
    assert bono['numeracion_carros'] == 'fisica'
    assert {orden['carro_numero'] for orden in bono['ordenes']} == {3, 4}
    assert len(bono['ordenes']) == 2
    carros = client.get('/api/carros').get_json()['carros']
    assert carros[0]['ocupado'] and not carros[0]['en_bono']
    assert carros[2]['ocupado'] and carros[2]['en_bono']
    assert client.post('/api/carros/3/liberar').status_code == 409
    assert client.post('/api/carros/3/liberar', json={'confirmar_bono': True}).status_code == 200
    assert len(client.get('/api/bonos/SOLO_3_4').get_json()['bono']['ordenes']) == 2


def test_bono_rechaza_carros_vacios_o_seleccion_invalida(client, app):
    _orden_en_carro(client, app, 'NO_PERDER', 4)
    for seleccion, codigo in (([], 400), ([4, 4], 400), ([7], 400), ([True], 400), ([3, 4], 409)):
        assert client.post('/api/bonos/generar', json={'nombre': 'INVALIDO', 'carros': seleccion}).status_code == codigo
    assert client.get('/api/carros').get_json()['carros'][3]['ocupado']


def test_progreso_y_report_respetan_numeracion_nueva_y_antigua(client, app, monkeypatch):
    from flask import jsonify
    from sqlalchemy import text
    from app.routes import progreso, reports
    from app.routes.base import db
    monkeypatch.setattr(progreso, '_crimps_por_terminal_archivo', lambda archivo: {'T1': 2})
    monkeypatch.setattr(reports, '_crimps_por_terminal_archivo', lambda archivo: {'T1': 2})
    monkeypatch.setattr(reports, 'render_template', lambda plantilla, **datos: jsonify(carros=datos['carros']))
    _orden_en_carro(client, app, 'FISICO_3', 3)
    _orden_en_carro(client, app, 'FISICO_4', 4)
    assert client.post('/api/bonos/generar', json={'nombre': 'FISICOS', 'carros': [3, 4]}).status_code == 200
    assert client.post('/api/bonos/FISICOS/progreso', json={'terminal': 'T1', 'carro': 3}).get_json()['success']
    datos = client.get('/api/bonos/FISICOS/progreso-ponderado').get_json()
    assert set(datos['progreso_por_carro']) == {'3', '4'}
    assert datos['progreso_por_carro']['3']['porcentaje'] == 100
    assert datos['progreso_por_carro']['4']['porcentaje'] == 0
    assert datos['porcentaje_bono'] == 50
    carros = client.get('/report/bono/FISICOS/carros').get_json()['carros']
    assert {carro['numero'] for carro in carros} == {3, 4}
    assert next(carro for carro in carros if carro['numero'] == 3)['completados'] == 1
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(text("UPDATE bonos SET numeracion_carros = 'posicional' WHERE nombre = 'FISICOS'"))
    antiguos = client.get('/api/bonos/FISICOS/progreso-ponderado').get_json()
    assert set(antiguos['progreso_por_carro']) == {'1', '2'}
    assert {carro['numero'] for carro in client.get('/report/bono/FISICOS/carros').get_json()['carros']} == {1, 2}
