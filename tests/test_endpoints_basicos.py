"""Smoke tests: las páginas y APIs básicas responden."""
import pytest


@pytest.mark.parametrize('url', [
    '/', '/modules', '/manual', '/v3', '/visualizacion',
    '/progreso-bono', '/etiquetas', '/manguitos', '/mangueras',
    '/proyectos', '/registro-ordenes', '/ordenes', '/health',
])
def test_paginas_publicas_responden(client, url):
    assert client.get(url).status_code == 200


@pytest.mark.parametrize('url', [
    '/api/bonos', '/api/carros', '/api/puestos', '/api/proyectos',
    '/api/maquinas', '/api/codigos', '/api/operarios', '/api/cable-colores',
    '/api/list_files',
])
def test_apis_publicas_responden(client, url):
    r = client.get(url)
    assert r.status_code == 200
    assert r.get_json()['success']


def test_health_reporta_bd_conectada(client):
    d = client.get('/health').get_json()
    assert d['status'] == 'ok'


def test_carros_iniciales_seis_libres(client):
    carros = client.get('/api/carros').get_json()['carros']
    assert len(carros) == 6
    assert all(not c['ocupado'] for c in carros)


def test_operarios_crud(client):
    r = client.post('/api/operarios', json={'nombre': 'OPERARIO TEST'})
    d = r.get_json()
    assert d['success'], d
    op_id = d['operario']['id']

    nombres = [o['nombre'] for o in client.get('/api/operarios').get_json()['operarios']]
    assert 'OPERARIO TEST' in nombres

    r = client.put(f'/api/operarios/{op_id}', json={'nombre': 'OPERARIO CAMBIADO'})
    assert r.get_json()['success']

    r = client.delete(f'/api/operarios/{op_id}')
    assert r.get_json()['success']
