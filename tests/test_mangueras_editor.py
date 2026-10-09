import io
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.excel_manager import ExcelManager, _parse_instrucciones
from app.routes.manguitos import _ordenar_mangueras_por_paquete
from app.mangueras_editor import (
    leer_preparacion, exportar_preparacion, listar_biblioteca_retractiles,
    serializar_instrucciones,
)


def excel_original():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Format'
    hoja.append(['Cable / Marca', 'Sección', 'Cod. cable', 'De Elemento', 'Observaciones', 'Longitud'])
    hoja.append(['MG1', '2x0,5', 'C1', 'X1', '<-PM100/MRS20 // PM200->', '=10+20'])
    hoja.append(['MG1', '12X1', 'C1', 'X1', 'Nota', 250])
    hoja.append(['Hilo', '0,5', 'C2', 'X2', None, 100])
    hoja.append(['MG3', '3 x 1', 'C3', 'X3', None, 100])
    hoja['A2'].font = Font(bold=True)
    libro.create_sheet('Otra').append(['No modificar'])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_sugerencias_y_legacy():
    datos = leer_preparacion(excel_original(), 'corte.xlsx')
    assert [fila['fila'] for fila in datos['filas']] == [2, 3, 5]
    assert datos['filas'][0]['de']['m_mrs_medida'] == 20
    assert datos['filas'][0]['para']['pm'] == 200


def test_descarga_compatible_sin_perder_excel(tmp_path):
    original = excel_original()
    datos = leer_preparacion(original, 'corte.xlsx')
    antes = deepcopy(datos)
    cambio = datos['filas'][1]
    cambio['de'] = _parse_instrucciones('PM120/MRC30/A100/A1_80/A2_90')
    cambio['para'] = _parse_instrucciones('PM150/M_CORTAR')
    cambio['retractil_de'] = [{'codigo': '649255', 'medida': 40}, {'codigo': '649251', 'medida': 70}]
    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])
    libro = load_workbook(salida)
    assert libro['Format']['F2'].value == '=10+20'
    assert libro['Format']['A2'].font.bold
    assert libro['Otra']['A1'].value == 'No modificar'
    assert libro['Format']['E3'].value == 'Nota'
    destino = tmp_path / 'editado.xlsx'
    libro.save(destino)
    mangueras = ExcelManager(str(tmp_path)).get_mangueras('editado.xlsx')
    assert len(mangueras) == 2
    assert mangueras[0]['de']['pm'] == 100
    assert mangueras[1]['de'] == cambio['de']
    assert mangueras[1]['retractil_de'] == cambio['retractil_de']
    assert leer_preparacion(original, 'corte.xlsx') == antes


def test_borrar_legacy_conserva_notas():
    original = excel_original()
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][0]
    cambio['de'] = _parse_instrucciones('')
    cambio['para'] = _parse_instrucciones('')
    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])
    assert load_workbook(salida)['Format']['E2'].value is None


@pytest.mark.parametrize('token', ['PM0/M0/A0/A1_0', 'PM120/MRS/A25', 'PM120/MRC/A100', 'M_CORTAR'])
def test_roundtrip_todos_los_campos(token):
    instrucciones = _parse_instrucciones(token)
    assert _parse_instrucciones(serializar_instrucciones(instrucciones)) == instrucciones


def test_rechaza_revision_o_fila_incorrecta():
    original = excel_original()
    datos = leer_preparacion(original, 'corte.xlsx')
    with pytest.raises(ValueError, match='ha cambiado'):
        exportar_preparacion(original, 'corte.xlsx', [], 'vieja')
    with pytest.raises(ValueError, match='Fila'):
        exportar_preparacion(original, 'corte.xlsx', [{'fila': 4}], datos['revision'])


@pytest.mark.parametrize('valor', [-1, 1.5, True, 'abc', 1000000])
def test_rechaza_medidas_invalidas(valor):
    with pytest.raises(ValueError, match='medidas'):
        serializar_instrucciones({'pm': valor})


def test_editor_y_descarga_http(client):
    pagina = client.get('/mangueras/editor')
    assert pagina.status_code == 200
    assert b'\x00' not in pagina.data
    original = excel_original()
    respuesta = client.post('/api/mangueras/editor/leer', data={'excel': (io.BytesIO(original), 'corte.xlsx')})
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    cambio = datos['filas'][1]
    cambio['de']['pm'] = 80
    cambio['observaciones_mangueras'] = '  Nota de taller\nsegunda línea  '
    descarga = client.post('/api/mangueras/editor/descargar', data={
        'excel': (io.BytesIO(original), 'corte.xlsx'), 'revision': datos['revision'],
        'cambios': json.dumps([cambio]),
    })
    assert descarga.status_code == 200
    assert 'corte_preparacion.xlsx' in descarga.headers['Content-Disposition']
    libro = load_workbook(io.BytesIO(descarga.data))
    assert libro['Format']['G3'].value == 'PM80'
    assert libro['Format']['W1'].value == 'Observaciones Mangueras'
    assert libro['Format']['W3'].value == cambio['observaciones_mangueras']
    assert libro['Format']['E3'].value == 'Nota'


def test_corte_registrado_no_se_sobrescribe(client, app):
    ruta = Path(app.config['UPLOAD_FOLDER']) / 'corte.xlsx'
    original = excel_original()
    ruta.write_bytes(original)
    datos = client.post('/api/mangueras/editor/leer', data={'archivo': 'corte.xlsx'}).get_json()
    respuesta = client.post('/api/mangueras/editor/descargar', data={
        'archivo': 'corte.xlsx', 'revision': datos['revision'], 'cambios': '[]',
    })
    assert respuesta.status_code == 200
    assert ruta.read_bytes() == original
    ruta.write_bytes(original + b'cambio')
    respuesta = client.post('/api/mangueras/editor/descargar', data={
        'archivo': 'corte.xlsx', 'revision': datos['revision'], 'cambios': '[]',
    })
    assert respuesta.status_code == 400
    assert 'ha cambiado' in respuesta.get_json()['error']


@pytest.mark.parametrize('data', [{'archivo': '../fuera.xlsx'}, {'cambios': '{'}])
def test_editor_rechaza_origen_invalido(client, data):
    assert client.post('/api/mangueras/editor/descargar', data=data).status_code == 400


def test_conserva_tokens_y_retractiles_no_reconocidos():
    libro = load_workbook(io.BytesIO(excel_original()))
    hoja = libro['Format']
    hoja['G1'] = 'Instrucciones Mangueras DE'
    hoja['G3'] = 'PM100/OTRA'
    hoja['H1'] = 'Retráctil DE'
    hoja['H3'] = 'COD_ABC_20/pendiente'
    buffer = io.BytesIO()
    libro.save(buffer)
    original = buffer.getvalue()
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][1]
    assert cambio['de']['otros_tokens'] == ['OTRA']
    cambio['de']['pm'] = 200
    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])
    editado = load_workbook(salida)['Format']
    assert editado['G3'].value == 'PM200/OTRA'
    assert editado['H3'].value == 'COD_ABC_20/pendiente'


def test_editor_respeta_permisos_mangueras(client, monkeypatch):
    import app.auth as auth
    from app.routes import base
    monkeypatch.setattr(auth, 'gate_operario_activo', lambda: True)
    monkeypatch.setattr(auth, '_pc_configurado_o_redirect', lambda: ('mangueras', None))
    monkeypatch.setattr(auth, '_operario_en_sesion_valido', lambda: 'Sin permiso')
    monkeypatch.setattr(base, 'operario_puede', lambda *args: False)
    assert client.get('/mangueras/editor').status_code == 403
    for accion in ('leer', 'biblioteca', 'descargar'):
        respuesta = (client.get('/api/mangueras/editor/biblioteca') if accion == 'biblioteca'
                     else client.post(f'/api/mangueras/editor/{accion}'))
        assert respuesta.status_code == 403
        assert respuesta.get_json()['success'] is False


@pytest.mark.parametrize('instrucciones', [
    {'m_cortar': True, 'm_mrc': True}, {'m': 20, 'm_mrs': True},
    {'a_especificos': {'1': None}}, {'a_especificos': {'0': 20}},
])
def test_rechaza_preparacion_ambigua(instrucciones):
    with pytest.raises(ValueError):
        serializar_instrucciones(instrucciones)


def test_exportacion_mantiene_celdas_como_texto():
    original = excel_original()
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][1]
    cambio['de']['otros_tokens'] = ['=SUM(A1)']
    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])
    celda = load_workbook(salida)['Format']['G3']
    assert celda.value == '=SUM(A1)'
    assert celda.data_type == 's'


def test_exportacion_normaliza_cabeceras_de_preparacion(tmp_path):
    libro = load_workbook(io.BytesIO(excel_original()))
    hoja = libro['Format']
    hoja['G1'] = 'instrucciones mangueras de'
    hoja['G3'] = 'PM10'
    buffer = io.BytesIO()
    libro.save(buffer)
    original = buffer.getvalue()
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][1]
    cambio['de']['pm'] = 50
    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])
    destino = tmp_path / 'editado.xlsx'
    destino.write_bytes(salida.getvalue())
    assert ExcelManager(str(tmp_path)).get_mangueras('editado.xlsx')[1]['de']['pm'] == 50


@pytest.mark.parametrize(('ultima_columna', 'columna_esperada'), [(17, 23), (25, 30)])
def test_observaciones_mangueras_se_guarda_en_columna_w_o_al_final(ultima_columna, columna_esperada):
    libro = load_workbook(io.BytesIO(excel_original()))
    hoja = libro['Format']
    for columna in range(7, ultima_columna + 1):
        hoja.cell(1, columna, f'Campo {columna}')
    buffer = io.BytesIO()
    libro.save(buffer)
    original = buffer.getvalue()
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][0]
    cambio['observaciones_mangueras'] = '  Revisar color y longitud\nNo cortar todavía.  '

    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])

    hoja = load_workbook(salida)['Format']
    assert hoja.cell(1, columna_esperada).value == 'Observaciones Mangueras'
    assert hoja.cell(2, columna_esperada).value == cambio['observaciones_mangueras']
    assert hoja.cell(2, columna_esperada).data_type == 's'


def test_observaciones_mangueras_reutiliza_columna_y_se_recargan():
    libro = load_workbook(io.BytesIO(excel_original()))
    hoja = libro['Format']
    hoja['W1'] = 'Observaciones Mangueras'
    hoja['W2'] = 'Nota anterior'
    buffer = io.BytesIO()
    libro.save(buffer)
    original = buffer.getvalue()
    datos = leer_preparacion(original, 'corte.xlsx')
    assert datos['filas'][0]['observaciones_mangueras'] == 'Nota anterior'
    cambio = datos['filas'][0]
    cambio['observaciones_mangueras'] = 'Nota nueva'
    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])
    recargadas = leer_preparacion(salida.getvalue(), 'corte.xlsx')
    assert recargadas['filas'][0]['observaciones_mangueras'] == 'Nota nueva'


def test_mangueras_lee_observacion_sola_y_conserva_saltos(tmp_path):
    libro = load_workbook(io.BytesIO(excel_original()))
    hoja = libro['Format']
    hoja['W1'] = 'Observaciones Mangueras'
    hoja['W3'] = '  Nota de taller\nsegunda línea  '
    buffer = io.BytesIO()
    libro.save(buffer)
    ruta = tmp_path / 'corte.xlsx'
    ruta.write_bytes(buffer.getvalue())

    resultado = ExcelManager(str(tmp_path)).get_mangueras('corte.xlsx')

    observacion = next(manguera for manguera in resultado
                       if manguera['cable_marca'] == 'MG1' and manguera['de_elemento'] == 'X1'
                       and manguera['de'] is None)
    assert observacion['observaciones_mangueras'] == '  Nota de taller\nsegunda línea  '


def test_orden_mangueras_agrupa_paquetes_y_conserva_orden_de_fila():
    mangueras = [
        {'cable_marca': 'P2-B', 'numero_etiqueta': '2', 'cod_cable': 'C2', 'de_elemento': 'E'},
        {'cable_marca': 'P1-A', 'numero_etiqueta': '1', 'cod_cable': 'C1', 'de_elemento': 'E'},
        {'cable_marca': 'P2-C', 'numero_etiqueta': '2', 'cod_cable': 'C2', 'de_elemento': 'E'},
        {'cable_marca': 'P1-02', 'numero_etiqueta': '1.02', 'cod_cable': 'C1', 'de_elemento': 'E'},
        {'cable_marca': 'SIN-ETQ-B', 'numero_etiqueta': None, 'cod_cable': 'C3', 'de_elemento': 'B'},
        {'cable_marca': 'SIN-ETQ-A', 'numero_etiqueta': None, 'cod_cable': 'C3', 'de_elemento': 'A'},
        {'cable_marca': 'SIN-ETQ-A2', 'numero_etiqueta': None, 'cod_cable': 'C3', 'de_elemento': 'A'},
    ]

    resultado = _ordenar_mangueras_por_paquete(mangueras)

    assert [manguera['cable_marca'] for manguera in resultado] == [
        'P1-A', 'P1-02', 'P2-B', 'P2-C', 'SIN-ETQ-A', 'SIN-ETQ-A2', 'SIN-ETQ-B',
    ]


def test_biblioteca_retractiles_reune_codigos_de_todos_los_cortes(tmp_path):
    for nombre, columna, valores in (
        ('corte-a.xlsx', 'Retractil DE', ['649255_40/649251_30', None, None, None]),
        ('corte-b.xlsx', 'Retráctil PARA', [None, None, '649700_25', None]),
    ):
        libro = load_workbook(io.BytesIO(excel_original()))
        hoja = libro['Format']
        hoja['G1'] = columna
        for fila, valor in enumerate(valores, start=2):
            hoja.cell(fila, 7, valor)
        libro.save(tmp_path / nombre)

    assert listar_biblioteca_retractiles(str(tmp_path)) == ['649251', '649255', '649700']


def test_api_biblioteca_retractiles(client, app):
    ruta = Path(app.config['UPLOAD_FOLDER']) / 'corte.xlsx'
    libro = load_workbook(io.BytesIO(excel_original()))
    libro['Format']['G1'] = 'Retractil DE'
    libro['Format']['G2'] = '649255_30'
    libro.save(ruta)

    respuesta = client.get('/api/mangueras/editor/biblioteca')

    assert respuesta.status_code == 200
    assert respuesta.get_json()['codigos'] == ['649255']


def test_aplicar_actualiza_mismo_excel_y_conserva_backup(admin_client, app):
    ruta = Path(app.config['UPLOAD_FOLDER']) / 'corte.xlsx'
    original = excel_original()
    ruta.write_bytes(original)
    manager = ExcelManager(str(ruta.parent))
    assert manager.get_mangueras('corte.xlsx')[0]['de']['pm'] == 100
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][0]
    cambio['de']['pm'] = 180
    cambio['observaciones_mangueras'] = 'Aplicar con cuidado.'
    with sqlite3.connect(app.config['DB_PATH']) as conexion:
        bd_antes = list(conexion.iterdump())
    respuesta = admin_client.post('/api/mangueras/editor/aplicar', data={
        'destino': 'corte.xlsx', 'revision': datos['revision'], 'cambios': json.dumps([cambio]),
    })
    assert respuesta.status_code == 200
    resultado = respuesta.get_json()
    assert resultado['archivo'] == 'corte.xlsx'
    assert resultado['datos']['revision'] != datos['revision']
    assert manager.get_mangueras('corte.xlsx')[0]['de']['pm'] == 180
    assert leer_preparacion(ruta.read_bytes(), 'corte.xlsx')['filas'][0]['observaciones_mangueras'] == 'Aplicar con cuidado.'
    assert (ruta.parent / resultado['backup']).read_bytes() == original
    libro = load_workbook(ruta)
    assert libro['Format']['F2'].value == '=10+20'
    assert libro['Otra']['A1'].value == 'No modificar'
    with sqlite3.connect(app.config['DB_PATH']) as conexion:
        assert list(conexion.iterdump()) == bd_antes


def test_aplicar_exige_administracion(client, app):
    ruta = Path(app.config['UPLOAD_FOLDER']) / 'corte.xlsx'
    original = excel_original()
    ruta.write_bytes(original)
    assert client.post('/api/mangueras/editor/aplicar', data={'destino': 'corte.xlsx'}).status_code == 401
    assert ruta.read_bytes() == original


@pytest.mark.parametrize('tipo', ['revision', 'medida', 'destino', 'json'])
def test_aplicar_error_no_modifica_original(admin_client, app, tipo):
    ruta = Path(app.config['UPLOAD_FOLDER']) / 'corte.xlsx'
    original = excel_original()
    ruta.write_bytes(original)
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][0]
    cambio['de']['pm'] = -1 if tipo == 'medida' else 180
    respuesta = admin_client.post('/api/mangueras/editor/aplicar', data={
        'destino': '../fuera.xlsx' if tipo == 'destino' else 'corte.xlsx',
        'revision': 'vieja' if tipo == 'revision' else datos['revision'],
        'cambios': '{' if tipo == 'json' else json.dumps([cambio]),
    })
    assert respuesta.status_code == 400
    assert ruta.read_bytes() == original
    assert list(ruta.parent.iterdir()) == [ruta]


def test_aplicar_fallo_de_escritura_no_modifica_original(admin_client, app, monkeypatch):
    from app.routes import manguitos
    ruta = Path(app.config['UPLOAD_FOLDER']) / 'corte.xlsx'
    original = excel_original()
    ruta.write_bytes(original)
    datos = leer_preparacion(original, 'corte.xlsx')
    def fallar(*args):
        raise OSError('Error de escritura simulado')
    monkeypatch.setattr(manguitos.os, 'replace', fallar)
    respuesta = admin_client.post('/api/mangueras/editor/aplicar', data={
        'destino': 'corte.xlsx', 'revision': datos['revision'], 'cambios': '[]',
    })
    assert respuesta.status_code == 500
    assert ruta.read_bytes() == original
    assert not any(fichero.name.startswith('tmp') for fichero in ruta.parent.iterdir())


def excel_con_activos():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Format'
    hoja.append(['Cable / Marca', 'Sección', 'Cod. cable', 'De Elemento', 'Para Elemento',
                 'De Elemento Etiquetas', 'Longitud', 'De Terminal', 'Para Terminal', 'Series'])
    hoja.append(['1502-P', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 4, 'TM', 'TM', None])
    hoja.append(['1502-1', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 0, 'TA', 'TA', None])
    hoja.append(['1502-2', '2X0,5+P', 'C1', 'X1*', 'X2', 'X1', 0, 'TA', 'TA', None])
    hoja.append(['1503-P', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 5, 'TM', 'TM', None])
    hoja.append(['1503-1', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 0, 'TA', 'TA', None])
    hoja.append(['1502-3', '2X0,5+P', 'OTRO', 'X1', 'X2', 'X1', 0, 'TA', 'TA', None])
    hoja.append(['1502-4', '2X0,5+P', 'C1', 'X9', 'X2', 'X9', 0, 'TA', 'TA', None])
    hoja.append(['1502-5', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 0, 'TA', 'TA', 'Serie2'])
    hoja['K1'] = 'Instrucciones Mangueras DE'
    hoja['L1'] = 'Instrucciones Mangueras PARA'
    hoja['K5'] = 'PM50'
    hoja['L5'] = 'PM60'
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_identifica_activos_sin_mezclar_otras_mangueras():
    datos = leer_preparacion(excel_con_activos(), 'corte.xlsx')
    padre = next(fila for fila in datos['filas'] if fila['fila'] == 2)
    assert padre['vinculacion']['confirmados'] is True
    assert [activo['cable_marca'] for activo in padre['vinculacion']['activos']] == ['1502-1', '1502-2']
    assert not any(fila['fila'] in (3, 4, 6) for fila in datos['filas'])


def test_pm_bloquea_solo_lado_sin_preparar_y_se_reactiva(tmp_path):
    original = excel_con_activos()
    datos = leer_preparacion(original, 'corte.xlsx')
    cambio = datos['filas'][0]
    cambio['de'] = _parse_instrucciones('PM100')
    cambio['para'] = _parse_instrucciones('A20/MRC')
    salida = exportar_preparacion(original, 'corte.xlsx', [cambio], datos['revision'])
    hoja = load_workbook(salida)['Format']
    assert hoja['D2'].value == 'X1'
    assert hoja['D4'].value == 'X1*'
    assert [hoja[f'E{fila}'].value for fila in (2, 3, 4)] == ['X2*'] * 3
    assert hoja['E5'].value == 'X2'
    assert hoja['E7'].value == 'X2'
    destino = tmp_path / 'corte.xlsx'
    destino.write_bytes(salida.getvalue())
    manager = ExcelManager(str(tmp_path))
    assert manager.cargar_excel_directo('corte.xlsx')
    grupos = manager.agrupar_por_cable_elemento(manager.buscar_terminal('TA'), 'TA')
    assert sum(grupo['num_terminales'] for grupo in grupos.values()) == 9
    assert '1502-1' in grupos['C1|X1']['cables_de_terminal']
    assert '1502-1' not in grupos['C1|X1']['cables_para_terminal']
    assert '1502-2' not in grupos['C1|X1']['cables_doble_terminal']
    datos = leer_preparacion(salida.getvalue(), 'corte.xlsx')
    cambio = datos['filas'][0]
    cambio['para'] = _parse_instrucciones('PM200')
    siguiente = exportar_preparacion(salida.getvalue(), 'corte.xlsx', [cambio], datos['revision'])
    hoja = load_workbook(siguiente)['Format']
    assert [hoja[f'E{fila}'].value for fila in (2, 3, 4)] == ['X2'] * 3
    assert hoja['D4'].value == 'X1*'
    columna_bloqueo = next(celda.column for celda in hoja[1] if celda.value == 'Bloqueo Mangueras PARA')
    assert all(hoja.cell(fila, columna_bloqueo).value is None for fila in (2, 3, 4))


def test_no_bloquea_identificacion_ambigua():
    libro = load_workbook(io.BytesIO(excel_con_activos()))
    libro['Format'].append(['1502-P', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 6, 'TM', 'TM', None])
    buffer = io.BytesIO()
    libro.save(buffer)
    datos = leer_preparacion(buffer.getvalue(), 'corte.xlsx')
    cambio = datos['filas'][0]
    assert cambio['vinculacion']['ambiguo'] is True
    assert cambio['vinculacion']['confirmados'] is False
    salida = exportar_preparacion(buffer.getvalue(), 'corte.xlsx', [cambio], datos['revision'])
    assert load_workbook(salida)['Format']['E3'].value == 'X2'


def test_sin_pm_bloquea_ambos_lados_incluso_sin_editar():
    original = excel_con_activos()
    datos = leer_preparacion(original, 'corte.xlsx')
    salida = exportar_preparacion(original, 'corte.xlsx', [], datos['revision'])
    hoja = load_workbook(salida)['Format']
    assert [hoja[f'D{fila}'].value for fila in (2, 3, 4)] == ['X1*'] * 3
    assert [hoja[f'E{fila}'].value for fila in (2, 3, 4)] == ['X2*'] * 3
    assert hoja['D5'].value == 'X1'
    assert hoja['D6'].value == 'X1'


def test_bloqueo_coherente_con_selector_y_conteos(app, client, monkeypatch):
    from app.routes import progreso
    libro = load_workbook(io.BytesIO(excel_con_activos()))
    hoja = libro['Format']
    hoja['H2'] = 'TBLOQUEADO'
    hoja['I2'] = 'TBLOQUEADO'
    buffer = io.BytesIO()
    libro.save(buffer)
    original = buffer.getvalue()
    datos = leer_preparacion(original, 'corte.xlsx')
    salida = exportar_preparacion(original, 'corte.xlsx', [], datos['revision'])
    (Path(app.config['UPLOAD_FOLDER']) / 'corte.xlsx').write_bytes(salida.getvalue())
    monkeypatch.setattr(progreso.BonoRepository, 'obtener_bono_por_nombre', lambda *args: {'id': 1})
    monkeypatch.setattr(progreso.OrdenRepository, 'obtener_ordenes_por_bono',
                        lambda *args: [{'archivo_excel': 'corte.xlsx'}])
    respuesta = client.get('/api/bonos/BPRUEBA/terminales-disponibles').get_json()
    assert 'TBLOQUEADO' not in respuesta['terminales']
    assert 'TA' in respuesta['terminales']
    with app.app_context():
        conteos = progreso._crimps_por_terminal_archivo('corte.xlsx')
    assert 'TBLOQUEADO' not in conteos
    assert conteos['TA'] == 8


def test_identifica_activo_por_observaciones():
    libro = load_workbook(io.BytesIO(excel_con_activos()))
    hoja = libro['Format']
    hoja['A3'] = '1502'
    hoja['M1'] = 'Observaciones'
    hoja['M3'] = '(1)'
    buffer = io.BytesIO()
    libro.save(buffer)
    datos = leer_preparacion(buffer.getvalue(), 'corte.xlsx')
    assert datos['filas'][0]['vinculacion']['confirmados']
    assert datos['filas'][0]['vinculacion']['activos'][0]['numero'] == '1'


def test_renfe_vincula_hijos_por_referencia_mang_aunque_cambie_o_falte_marca():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Sheet1'
    hoja.append(['Posición', 'Cable / Marca', 'Sección', 'Longitud', 'Cod. cable',
                 'De Elemento', 'De Elemento Etiquetas', 'De Terminal', 'Para Elemento',
                 'Para Terminal', 'Observaciones'])
    hoja.append([317, 'EFM2-2', '2X0,5', 3.4, '640D10009A', 'LEM/P1/TB2',
                 'LEMIO1/P1', 'S/T', 'X21', 'S/T', 'MANG. EFM2-2(PELAR 500 mm)'])
    hoja.append([318, '1116(1)', '2X0,5', 0, '640D10009A', 'LEMIO1/P1',
                 'LEMIO1/P1', '641M10100', 'X21', '641H10055', 'MANG. EFM2-2(1)'])
    hoja.append([319, '203-6(2)', '2X0,5', 0, '640D10009A', 'TB2',
                 'LEMIO1/P1', '641H10055', 'X21', '641H10055', 'MANG. EFM2-2(2)'])
    hoja.append([320, None, '2X0,5', 0, '640D10009A', 'CORTAR',
                 'LEMIO1/P1', 'S/T', 'CORTAR', 'S/T', 'MANG. EFM2-2(S)'])
    buffer = io.BytesIO()
    libro.save(buffer)

    datos = leer_preparacion(buffer.getvalue(), 'renfe.xlsx')
    padre = datos['filas'][0]

    assert padre['cable_marca'] == 'EFM2-2'
    assert padre['vinculacion']['confirmados']
    assert [activo['cable_marca'] for activo in padre['vinculacion']['activos']] == [
        '1116(1)', '203-6(2)',
    ]
    assert [malla['cable_marca'] for malla in padre['vinculacion']['mallas']] == ['']
    salida = exportar_preparacion(buffer.getvalue(), 'renfe.xlsx', [], datos['revision'])
    hoja = load_workbook(salida)['Sheet1']
    assert hoja['F3'].value == 'LEMIO1/P1*'
    assert hoja['I3'].value == 'X21*'
    assert hoja['F4'].value == 'TB2*'
    assert hoja['I4'].value == 'X21*'
    assert hoja['F5'].value == 'CORTAR'


def test_renfe_referencia_mang_admite_cable_adicional_tras_sufijo():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Sheet1'
    hoja.append(['Cable / Marca', 'Sección', 'Longitud', 'Cod. cable', 'De Elemento',
                 'De Elemento Etiquetas', 'De Terminal', 'Para Elemento', 'Para Terminal',
                 'Observaciones'])
    hoja.append(['CFM1-1', '2X1+P', 5.5, '640D10029A', 'MCM/P2/TB1',
                 'MCM/P2/TB1', 'S/T', 'CFM1-1', 'S/T', 'MANG. CFM1-1(PELAR 500 mm)'])
    hoja.append(['813(1)', '2X1+P', 0, '640D10029A', 'MCMIFB/P2',
                 'MCM/P2/TB1', '641M155', 'CFM1-1', 'S/T', 'MANG. CFM1-1(1) 813(1)'])
    buffer = io.BytesIO()
    libro.save(buffer)

    datos = leer_preparacion(buffer.getvalue(), 'renfe.xlsx')

    assert datos['filas'][0]['vinculacion']['confirmados']
    assert datos['filas'][0]['vinculacion']['activos'][0]['cable_marca'] == '813(1)'


def test_renfe_kit_de_envio_vincula_activos_por_grupo_y_elemento():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Sheet1'
    hoja.append(['Cable / Marca', 'Sección', 'Longitud', 'Cod. cable', 'De Elemento',
                 'De Elemento Etiquetas', 'De Terminal', 'Para Elemento', 'Para Terminal',
                 'Observaciones'])
    hoja.append(['EFM1-1', '3X0.5', 2.5, '640D10002', 'TB2/K3.4', 'TB2/K3.4',
                 'S/T', 'X19', 'S/T', 'MANG. EFM1-1 PELAR 400 mm.'])
    hoja.append(['EFM1-1', '3X0.5', 0.7, '640D10002', 'X19', 'X19',
                 'S/T', 'X19', 'S/T', 'KIT DE ENVÍO'])
    for posicion, marca in enumerate(('1009-1(1)', '1010-1(2)', '1011-1(3)'), start=1):
        hoja.append([marca, '3X0.5', 0, '640D10002', 'X19', 'X19',
                     f'T{posicion}', 'X19', 'T4', 'KIT DE ENVÍO'])
    buffer = io.BytesIO()
    libro.save(buffer)

    datos = leer_preparacion(buffer.getvalue(), 'renfe.xlsx')
    padre_kit = next(fila for fila in datos['filas'] if fila['fila'] == 3)
    padre_otro_elemento = next(fila for fila in datos['filas'] if fila['fila'] == 2)

    assert padre_kit['vinculacion']['confirmados']
    assert [activo['cable_marca'] for activo in padre_kit['vinculacion']['activos']] == [
        '1009-1(1)', '1010-1(2)', '1011-1(3)',
    ]
    assert padre_otro_elemento['vinculacion']['confirmados'] is False
    salida = exportar_preparacion(buffer.getvalue(), 'renfe.xlsx', [], datos['revision'])
    hoja = load_workbook(salida)['Sheet1']
    assert [hoja[f'E{fila}'].value for fila in (4, 5, 6)] == ['X19*'] * 3
    assert [hoja[f'H{fila}'].value for fila in (4, 5, 6)] == ['X19*'] * 3


def test_renfe_kit_de_envio_no_asocia_si_hay_dos_padres_iguales():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Sheet1'
    hoja.append(['Cable / Marca', 'Sección', 'Longitud', 'Cod. cable', 'De Elemento',
                 'De Elemento Etiquetas', 'De Terminal', 'Para Elemento', 'Para Terminal',
                 'Observaciones'])
    for marca in ('EFM1-A', 'EFM1-B'):
        hoja.append([marca, '3X0.5', 0.7, '640D10002', 'X19', 'X19', 'S/T', 'X19', 'S/T', 'KIT DE ENVÍO'])
    hoja.append(['1009-1(1)', '3X0.5', 0, '640D10002', 'X19', 'X19', 'T1', 'X19', 'T2', 'KIT DE ENVÍO'])
    buffer = io.BytesIO()
    libro.save(buffer)

    datos = leer_preparacion(buffer.getvalue(), 'renfe.xlsx')

    assert all(fila['vinculacion']['confirmados'] is False for fila in datos['filas'][:2])
    hijo = next(fila for fila in datos['filas'] if fila['fila'] == 4)
    assert hijo['vinculacion']['confirmados'] is False


def test_legacy_y_pm_cero_habilitan_lados():
    libro = load_workbook(io.BytesIO(excel_con_activos()))
    hoja = libro['Format']
    hoja['M1'] = 'Observaciones'
    hoja['M2'] = '<-PM0 // PM200->'
    buffer = io.BytesIO()
    libro.save(buffer)
    datos = leer_preparacion(buffer.getvalue(), 'corte.xlsx')
    salida = exportar_preparacion(buffer.getvalue(), 'corte.xlsx', [], datos['revision'])
    hoja = load_workbook(salida)['Format']
    assert hoja['D3'].value == 'X1'
    assert hoja['E3'].value == 'X2'
    assert hoja['D4'].value == 'X1*'


def excel_con_parentesis():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Sheet1'
    hoja.append(['Cable / Marca', 'Sección', 'Cod. cable', 'De Elemento', 'Para Elemento',
                 'De Elemento Etiquetas', 'Longitud', 'De Terminal', 'Para Terminal', 'Series'])
    hoja.append(['2705', '2X0,5+P', '640D10009A', 'MCMIFB/P2', 'X3', 'MCMIFB/P2', 1.6, 'S/T', 'S/T', None])
    hoja.append(['2705(S)', '2X0,5+P', '640D10009A', 'RACK', 'X3', 'MCMIFB/P2', 0, '641H039', 'S/T', None])
    hoja.append(['2705(2)', '2X0,5+P', '640D10009A', 'MCMIFB/P2', 'X3', 'MCMIFB/P2', 0, '641M10100', '641M644', None])
    hoja.append(['2705(1)', '2X0,5+P', '640D10009A', 'MCMIFB/P2', 'X3', 'MCMIFB/P2', 0, '641M10100', '641M644', None])
    hoja.append(['2706(1)', '2X0,5+P', '640D10009A', 'MCMIFB/P2', 'X3', 'MCMIFB/P2', 0, '641M10100', '641M644', None])
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_parentesis_identifica_activos_y_malla_con_elemento_distinto():
    datos = leer_preparacion(excel_con_parentesis(), 'corte.xlsx')
    padre = datos['filas'][0]
    assert padre['cable_marca'] == '2705'
    assert padre['vinculacion']['confirmados']
    assert [activo['cable_marca'] for activo in padre['vinculacion']['activos']] == ['2705(2)', '2705(1)']
    assert padre['vinculacion']['mallas'][0]['cable_marca'] == '2705(S)'
    assert padre['vinculacion']['mallas'][0]['de_elemento'] == 'RACK'
    assert [fila['fila'] for fila in datos['filas']] == [2, 6]


def test_parentesis_bloquea_y_reactiva_malla_y_activos():
    original = excel_con_parentesis()
    datos = leer_preparacion(original, 'corte.xlsx')
    salida = exportar_preparacion(original, 'corte.xlsx', [], datos['revision'])
    hoja = load_workbook(salida)['Sheet1']
    assert hoja['D3'].value == 'RACK*'
    assert hoja['D4'].value == 'MCMIFB/P2*'
    assert hoja['E4'].value == 'X3*'
    assert hoja['D6'].value == 'MCMIFB/P2'
    nuevos = leer_preparacion(salida.getvalue(), 'corte.xlsx')
    cambio = nuevos['filas'][0]
    cambio['de'] = _parse_instrucciones('PM100')
    siguiente = exportar_preparacion(salida.getvalue(), 'corte.xlsx', [cambio], nuevos['revision'])
    hoja = load_workbook(siguiente)['Sheet1']
    assert hoja['D3'].value == 'RACK'
    assert hoja['D4'].value == 'MCMIFB/P2'
    assert hoja['E4'].value == 'X3*'


def test_hri_manguera_l_asocia_l1_l2_l3_y_malla():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Sheet1'
    hoja.append(['Cod. cable', 'Sección', 'Longitud', 'Cable / Marca', 'De Elemento',
                 'De Terminal', 'Para Elemento', 'Para Terminal', 'De Elemento Etiquetas'])
    hoja.append(['640D10019', '3X2,5+P', 0, 'L1(1)', 'K5', '640205', 'TB5', '641H10058', 'K5'])
    hoja.append(['640D10019', '3X2,5+P', 0, 'L2(2)', 'K5', '640205', 'TB5', '641H10058', 'K5'])
    hoja.append(['640D10019', '3X2,5+P', 0, 'L3(3)', 'K5', '640205', 'TB5', '641H10058', 'K5'])
    hoja.append(['640D10019', '3X2,5+P', 0, 'L(S)', 'K5', 'S/T', 'CARRIL-EMC', 'S/T', 'K5'])
    hoja.append(['640D10019', '3X2,5+P', 1, 'L', 'K5', 'S/T', 'TB5', 'S/T', 'K5'])
    buffer = io.BytesIO()
    libro.save(buffer)

    datos = leer_preparacion(buffer.getvalue(), 'corte.xlsx')

    assert [fila['fila'] for fila in datos['filas']] == [6]
    padre = datos['filas'][0]
    assert padre['cable_marca'] == 'L'
    assert padre['vinculacion']['confirmados'] is True
    assert [activo['cable_marca'] for activo in padre['vinculacion']['activos']] == [
        'L1(1)', 'L2(2)', 'L3(3)',
    ]
    assert [malla['cable_marca'] for malla in padre['vinculacion']['mallas']] == ['L(S)']
    salida = exportar_preparacion(buffer.getvalue(), 'corte.xlsx', [], datos['revision'])
    hoja = load_workbook(salida)['Sheet1']
    assert [hoja[f'E{fila}'].value for fila in (2, 3, 4)] == ['K5*'] * 3
    assert hoja['E5'].value == 'K5'
    assert hoja['E6'].value == 'K5'


def test_zefiro_j_asocia_colores_y_pantalla_sin_mezclar_n():
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Sheet1'
    hoja.append(['Cod. cable', 'Sección', 'Longitud', 'Cable / Marca', 'De Elemento',
                 'De Terminal', 'Para Elemento', 'Para Terminal', 'De Elemento Etiquetas'])
    hoja.append(['H0211195', '2X0,5 S', 1.6, 'J', 'X3', 'S/T', 'CAN1 IN', 'S/T', 'X3'])
    hoja.append(['H0211195', '2X0,5 S', 0, 'J (RED)', 'X3', '641M644', 'CAN1 IN', '641M937', 'X3'])
    hoja.append(['H0211195', '2X0,5 S', 0, 'J (WHITE)', 'X3', '641M644', 'CAN1 IN', '641M937', 'X3'])
    hoja.append(['H0211195', '2X0,5 S', 0, 'J (BLUE)', 'X3', '641M644', 'CAN1 IN', '641M937', 'X3'])
    hoja.append(['H0211195', '2X0,5 S', 0, 'J(S)', 'X3 P.MASAS', 'S/T', 'CAN1 IN', 'S/T', 'X3'])
    hoja.append(['H0211195', '2X0,5 S', 1.6, 'N', 'X3', 'S/T', 'CAN2 IN', 'S/T', 'X3'])
    hoja.append(['H0211195', '2X0,5 S', 0, 'N (BLUE)', 'X3', '641M576', 'CAN2 IN', '641M937', 'X3'])
    buffer = io.BytesIO()
    libro.save(buffer)

    datos = leer_preparacion(buffer.getvalue(), 'corte.xlsx')
    padre_j = next(fila for fila in datos['filas'] if fila['cable_marca'] == 'J')
    padre_n = next(fila for fila in datos['filas'] if fila['cable_marca'] == 'N')

    assert padre_j['vinculacion']['confirmados'] is True
    assert [activo['cable_marca'] for activo in padre_j['vinculacion']['activos']] == [
        'J (RED)', 'J (WHITE)', 'J (BLUE)',
    ]
    assert [malla['cable_marca'] for malla in padre_j['vinculacion']['mallas']] == ['J(S)']
    assert padre_n['vinculacion']['confirmados'] is True
    assert [activo['cable_marca'] for activo in padre_n['vinculacion']['activos']] == ['N (BLUE)']


def test_api_mangueras_oculta_hijos_confirmados_y_conserva_padres(client, tmp_path):
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Format'
    hoja.append(['Cable / Marca', 'Sección', 'Cod. cable', 'De Elemento', 'Para Elemento',
                 'De Elemento Etiquetas', 'Longitud', 'De Terminal', 'Para Terminal',
                 'Series', 'Instrucciones Mangueras DE', 'Instrucciones Mangueras PARA'])
    hoja.append(['2705', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 1.6, 'S/T', 'S/T', None, 'PM100', 'PM200'])
    hoja.append(['2705(1)', '2X0,5+P', 'C1', 'X1', 'X2', 'X1', 0, 'T1', 'T2', None, 'PM100', 'PM200'])
    hoja.append(['2705(S)', '2X0,5+P', 'C1', 'RACK', 'X2', 'X1', 0, 'S/T', 'S/T', None, 'M_CORTAR', 'PM200'])
    hoja.append(['2706', '2X0,5+P', 'C2', 'X3', 'X4', 'X3', 1.6, 'S/T', 'S/T', None, 'PM80', 'PM90'])
    buffer = io.BytesIO()
    libro.save(buffer)
    (tmp_path / 'corte.xlsx').write_bytes(buffer.getvalue())
    client.application.config['UPLOAD_FOLDER'] = str(tmp_path)

    respuesta = client.post('/api/mangueras/datos', json={'archivo': 'corte.xlsx'})

    assert respuesta.status_code == 200
    mangueras = respuesta.get_json()['mangueras']
    assert [manguera['cable_marca'] for manguera in mangueras] == ['2705', '2706']
    assert all(manguera['fila_excel'] in (2, 5) for manguera in mangueras)