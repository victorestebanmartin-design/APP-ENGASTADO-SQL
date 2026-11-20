"""
Admin → Cable: un cable marcado como «corte manual» avisa en la preparación de
mangueras para que revisen la longitud. No depende de que el cable tenga color.
"""
from pathlib import Path

import pandas as pd


def _excel_mangueras(app, nombre, filas):
    pd.DataFrame(filas, columns=['Cod. cable', 'Sección', 'De Elemento', 'De Terminal', 'Para Elemento',
                                 'Para Terminal', 'Instrucciones Mangueras DE']).to_excel(
        Path(app.config['UPLOAD_FOLDER']) / nombre, index=False, sheet_name='Format')


def _mangueras(client):
    respuesta = client.post('/api/mangueras/datos', json={'archivo': 'corte.xlsx'}).get_json()
    assert respuesta['success'] is True
    return {m['cod_cable']: m for m in respuesta['mangueras']}


def test_marcar_y_desmarcar_corte_manual_sin_color(client):
    assert client.post('/api/cables/corte-manual', json={'cod_cable': ' c1 ', 'corte_manual': True}).status_code == 200
    datos = client.get('/api/cable-colores').get_json()
    assert datos['corte_manual'] == ['C1']
    assert datos['colores'] == [] or all(c['cod_cable'] != 'C1' for c in datos['colores'])

    client.post('/api/cables/corte-manual', json={'cod_cable': 'C1', 'corte_manual': False})
    assert client.get('/api/cable-colores').get_json()['corte_manual'] == []


def test_marcar_sin_codigo_es_400(client):
    assert client.post('/api/cables/corte-manual', json={'corte_manual': True}).status_code == 400


def test_borrar_el_color_no_quita_el_corte_manual(client):
    client.post('/api/cable-colores', json={'cod_cable': 'C1', 'color_hex': '#123456'})
    client.post('/api/cables/corte-manual', json={'cod_cable': 'C1', 'corte_manual': True})
    client.delete('/api/cable-colores/C1')
    assert client.get('/api/cable-colores').get_json()['corte_manual'] == ['C1']


def test_preparacion_de_mangueras_lleva_el_aviso(app, client):
    _excel_mangueras(app, 'corte.xlsx', [
        ['C1', '1', 'X1', 'TA', 'X2', 'TA', 'PM150'],
        ['C2', '1', 'X3', 'TA', 'X4', 'TA', 'PM150'],
    ])
    client.post('/api/cables/corte-manual', json={'cod_cable': 'c1', 'corte_manual': True})

    mangueras = _mangueras(client)
    assert mangueras['C1']['corte_manual'] is True
    assert mangueras['C2']['corte_manual'] is False
