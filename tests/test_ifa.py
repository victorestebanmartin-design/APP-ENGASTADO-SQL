"""
Sección IFA y Análisis por corte de Gestión de Puestos.

IFA es la lista con la que se actualizan en SAP los terminales que se colocan en
esta área: un lado con '*' en su elemento se queda en paneles, y un corte que no
se puede leer tiene que avisar, no desaparecer de la lista.
"""
import io
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from sqlalchemy import text


def _excel(app, nombre, filas):
    df = pd.DataFrame(filas, columns=['Cod. cable', 'Sección', 'De Elemento', 'De Terminal',
                                      'Para Elemento', 'Para Terminal'])
    df['Observaciones'] = ''
    df.to_excel(Path(app.config['UPLOAD_FOLDER']) / nombre, index=False, sheet_name='Format')


def _sql(app, sentencia, **parametros):
    from app.routes.base import db
    with app.app_context():
        db.session.execute(text(sentencia), parametros)
        db.session.commit()


def _corte(app, codigo, archivo):
    _sql(app, "INSERT INTO codigos_cortes (codigo, archivo_excel) VALUES (:c, :a)", c=codigo, a=archivo)


def _maquina(app, terminal, tipo='MANUAL'):
    _sql(app, "INSERT OR IGNORE INTO puestos (id, nombre) VALUES ('p1', 'PUESTO')")
    _sql(app, "INSERT OR IGNORE INTO maquinas (id, puesto_id, nombre, tipo_operacion) "
              "VALUES (:m, 'p1', :m, :t)", m='MAQ_' + tipo, t=tipo)
    _sql(app, "INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES (:m, :t)",
         m='MAQ_' + tipo, t=terminal)


def _filas_ifa(client, consulta=''):
    respuesta = client.get('/api/ifa/terminales-por-corte' + consulta)
    assert respuesta.status_code == 200
    return respuesta.get_json()


def _por_terminal(datos):
    return {f['terminal']: f for f in datos['filas']}


def test_ifa_separa_colocados_y_paneles(app, client):
    _excel(app, 'corte.xlsx', [
        ['C1', '1', 'X1', 'TA', 'X2', 'TA'],    # dos lados aquí
        ['C2', '1', 'X1*', 'TA', 'X2', 'TB'],   # un lado de TA a paneles
        ['C3', '1', 'X1*', 'TC', 'X2*', 'TC'],  # TC solo va en paneles
    ])
    _corte(app, 'H1', 'corte.xlsx')

    filas = _por_terminal(_filas_ifa(client))

    assert (filas['TA']['colocados'], filas['TA']['paneles']) == (2, 1)
    assert (filas['TB']['colocados'], filas['TB']['paneles']) == (1, 0)
    assert (filas['TC']['colocados'], filas['TC']['paneles']) == (0, 2)


def test_ifa_coincide_con_los_crimps_de_engastado(app, client):
    from app.routes.progreso import _crimps_por_terminal_archivo
    _excel(app, 'corte.xlsx', [
        ['C1', '1', 'X1', 'TA', 'X2', 'TA'],
        ['C2', '1', 'X1*', 'TA', 'X2', 'TB'],
        ['C3', '1', 'X1*', 'TC', 'X2*', 'TC'],
        ['C4', '1', 'X1', 'S/T', 'X2', 'TB'],
    ])
    _corte(app, 'H1', 'corte.xlsx')

    with app.app_context():
        crimps = _crimps_por_terminal_archivo('corte.xlsx')

    assert crimps == {'TA': 2, 'TB': 2}
    colocados = {f['terminal']: f['colocados'] for f in _filas_ifa(client)['filas'] if f['colocados']}
    assert colocados == crimps


def test_ifa_deja_fuera_ignorados_y_sin_terminal(app, client):
    _excel(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'S/T'],
                               ['C2', '1', 'X1', 'KN-PELAR', 'X2', 'TA']])
    _corte(app, 'H1', 'corte.xlsx')
    _sql(app, "INSERT INTO terminales_ignorados (terminal_codigo) VALUES ('KN-PELAR')")

    assert set(_por_terminal(_filas_ifa(client))) == {'TA'}


def test_ifa_indica_maquina_o_sin_asignar(app, client):
    _excel(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TB']])
    _corte(app, 'H1', 'corte.xlsx')
    _maquina(app, 'TA', 'SEMI-AUTOMATICA')

    filas = _por_terminal(_filas_ifa(client))

    assert filas['TA']['tipo_operacion'] == 'SEMI-AUTOMATICA'
    assert filas['TB']['maquina'] is None


def test_ifa_filtra_por_codigo(app, client):
    _excel(app, 'a.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TA']])
    _excel(app, 'b.xlsx', [['C1', '1', 'X1', 'TB', 'X2', 'TB']])
    _corte(app, 'H1', 'a.xlsx')
    _corte(app, 'H2', 'b.xlsx')

    assert set(_por_terminal(_filas_ifa(client))) == {'TA', 'TB'}
    assert set(_por_terminal(_filas_ifa(client, '?codigo=H2'))) == {'TB'}


def test_ifa_avisa_del_corte_que_no_se_puede_leer(app, client):
    _excel(app, 'bueno.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TA']])
    _corte(app, 'H1', 'bueno.xlsx')
    _corte(app, 'H2', 'no_existe.xlsx')

    datos = _filas_ifa(client)

    assert set(_por_terminal(datos)) == {'TA'}
    assert [a['codigo'] for a in datos['avisos']] == ['H2']


def test_ifa_exporta_excel_con_cantidades(app, client):
    _excel(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2*', 'TA']])
    _corte(app, 'H1', 'corte.xlsx')
    _corte(app, 'H2', 'no_existe.xlsx')

    respuesta = client.get('/api/ifa/export-excel')

    assert respuesta.status_code == 200
    libro = load_workbook(io.BytesIO(respuesta.data))
    hoja = libro['Terminales']
    cabecera = [c.value for c in hoja[1]]
    fila = dict(zip(cabecera, [c.value for c in hoja[2]]))
    assert fila['Código corte'] == 'H1'
    assert fila['Referencia'] == 'TA'
    assert fila['Cantidad IFA'] == 1
    assert fila['Cantidad paneles'] == 1
    assert 'Avisos' in libro.sheetnames


def _excel_mangueras(app, nombre, filas):
    pd.DataFrame(filas, columns=['Cod. cable', 'Sección', 'De Elemento', 'De Terminal', 'Para Elemento',
                                 'Para Terminal', 'Instrucciones Mangueras DE', 'Retractil DE',
                                 'Retractil PARA']).to_excel(
        Path(app.config['UPLOAD_FOLDER']) / nombre, index=False, sheet_name='Format')


def test_ifa_suma_los_mm_de_cada_retractil(app, client):
    _excel_mangueras(app, 'corte.xlsx', [
        ['C1', '1', 'X1', 'TA', 'X2', 'TA', 'PM150', '649255_40/649251_70', '649255_30'],
        ['C2', '1', 'X1', 'TA', 'X2', 'TA', 'PM150', '649255_40', None],
    ])
    _corte(app, 'H1', 'corte.xlsx')

    datos = _filas_ifa(client)

    totales = {r['retractil']: (r['mm'], r['piezas']) for r in datos['retractiles']}
    assert totales == {'649255': (110, 3), '649251': (70, 1)}
    assert datos['avisos'] == []


def test_ifa_avisa_del_retractil_sin_formato_en_vez_de_perderlo(app, client):
    _excel_mangueras(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TA', 'PM150', '649255_40/649251', None]])
    _corte(app, 'H1', 'corte.xlsx')

    datos = _filas_ifa(client)

    assert [r['mm'] for r in datos['retractiles']] == [40]
    assert len(datos['avisos']) == 1
    assert '649251' in datos['avisos'][0]['motivo']


def test_ifa_avisa_de_propuestas_de_mangueras_pendientes(app, client):
    _excel_mangueras(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TA', 'PM150', '649255_40', None]])
    _corte(app, 'H1', 'corte.xlsx')
    from app.routes.base import db
    with app.app_context():
        columnas = db.session.execute(text('PRAGMA table_info(mangueras_propuestas)')).fetchall()
        valores = {c[1]: ('' if c[2].upper() == 'TEXT' else (b'' if c[2].upper() == 'BLOB' else 0))
                   for c in columnas if c[3] and not c[5] and c[4] is None}
        valores.update(archivo='corte.xlsx', estado='pendiente')
        db.session.execute(text(
            f"INSERT INTO mangueras_propuestas ({', '.join(valores)}) "
            f"VALUES ({', '.join(':' + k for k in valores)})"), valores)
        db.session.commit()

    assert _filas_ifa(client)['cortes'][0]['propuestas_mangueras'] == 1


def test_ifa_exporta_retractil_y_solo_paneles_en_su_hoja(app, client):
    _excel_mangueras(app, 'corte.xlsx', [
        ['C1', '1', 'X1', 'TA', 'X2*', 'TB', 'PM150', '649255_40', None],
    ])
    _corte(app, 'H1', 'corte.xlsx')

    respuesta = client.get('/api/ifa/export-excel?codigo=H1')

    assert 'ifa_H1_' in respuesta.headers['Content-Disposition']
    libro = load_workbook(io.BytesIO(respuesta.data))
    assert [c.value for c in libro['Terminales']['B']] == ['Referencia', 'TA']
    assert [c.value for c in libro['Solo en paneles']['B']] == ['Referencia', 'TB']
    assert [c.value for c in libro['Retráctil'][2]][:4] == ['H1', '649255', 40, 1]


def test_mangueras_datos_sigue_sin_cambiar_tras_extraer_el_helper(app, client):
    _excel_mangueras(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TA', 'PM150', '649255_40', None]])

    respuesta = client.post('/api/mangueras/datos', json={'archivo': 'corte.xlsx'}).get_json()

    assert respuesta['success'] is True
    assert respuesta['mangueras'][0]['retractil_de'] == [{'codigo': '649255', 'medida': 40}]


def test_pagina_trae_la_seccion_ifa(admin_client):
    html = admin_client.get('/gestion-puestos').get_data(as_text=True)

    assert 'id="sec-ifa"' in html
    assert "gpNav('ifa')" in html


def test_tarjetas_de_analisis_llevan_a_su_corte_en_ifa():
    js = (Path(__file__).parent.parent / 'static' / 'js' / 'gestion-puestos.js').read_text(encoding='utf-8')

    assert 'irIfaCorte(this.dataset.codigo)' in js
    assert 'function irIfaCorte(codigo)' in js


def _propuesta(app, archivo, terminal, estado, cables=1):
    _sql(app, "INSERT INTO engastado_propuestas (archivo, terminal, paquete, autor_id, autor_nombre, "
              "creada_at, motivo, estado) VALUES (:a, :t, 'P', 'o1', 'Op', '2026-01-01', 'Otros: x', :e)",
         a=archivo, t=terminal, e=estado)
    for fila in range(cables):
        _sql(app, "INSERT INTO engastado_propuestas_cables (propuesta_id, archivo, fila, lado, terminal, "
                  "cod_cable, cable_marca, elemento) VALUES ((SELECT MAX(id) FROM engastado_propuestas), "
                  ":a, :f, 'de', :t, 'C1', 'M', 'X1')", a=archivo, f=fila + 2, t=terminal)


def test_ifa_ensena_propuestas_pendientes_sin_cambiar_la_cantidad(app, client):
    _excel(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TA'],
                               ['C2', '1', 'X1', 'TA', 'X2', 'TB']])
    _corte(app, 'H1', 'corte.xlsx')
    _propuesta(app, 'corte.xlsx', 'TA', 'pendiente', cables=2)
    _propuesta(app, 'corte.xlsx', 'TB', 'rechazada')

    filas = _por_terminal(_filas_ifa(client))

    assert (filas['TA']['colocados'], filas['TA']['pendientes']) == (3, 2)
    assert (filas['TB']['colocados'], filas['TB']['pendientes']) == (1, 0)


def test_ifa_una_propuesta_aprobada_baja_la_cantidad(app, client):
    # Aprobar escribe el '*' en el Excel: de ahí sale la cantidad, sin más lógica
    _excel(app, 'corte.xlsx', [['C1', '1', 'X1*', 'TA', 'X2', 'TA']])
    _corte(app, 'H1', 'corte.xlsx')
    _propuesta(app, 'corte.xlsx', 'TA', 'aprobada')

    fila = _por_terminal(_filas_ifa(client))['TA']

    assert (fila['colocados'], fila['paneles'], fila['pendientes']) == (1, 1, 0)


def test_analisis_no_cuenta_ignorados(app, client):
    _excel(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'KN-PELAR']])
    _corte(app, 'H1', 'corte.xlsx')
    _maquina(app, 'TA')
    _sql(app, "INSERT INTO terminales_ignorados (terminal_codigo) VALUES ('KN-PELAR')")

    datos = client.get('/api/estadisticas-tipo-operacion').get_json()

    assert datos['por_archivo'][0]['total'] == 1
    assert datos['por_archivo'][0]['sin_asignar'] == 0
    assert datos['global']['sin_asignar'] == 0


def test_analisis_no_cuenta_lo_que_solo_lleva_asterisco(app, client):
    _excel(app, 'corte.xlsx', [['C1', '1', 'X1', 'TA', 'X2*', 'TPANEL']])
    _corte(app, 'H1', 'corte.xlsx')
    _maquina(app, 'TA')

    datos = client.get('/api/estadisticas-tipo-operacion').get_json()

    assert datos['por_archivo'][0]['total'] == 1
    assert datos['por_archivo'][0]['sin_asignar'] == 0


def test_analisis_global_cuenta_terminales_distintos(app, client):
    _excel(app, 'a.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TPEND']])
    _excel(app, 'b.xlsx', [['C1', '1', 'X1', 'TA', 'X2', 'TPEND']])
    _corte(app, 'H1', 'a.xlsx')
    _corte(app, 'H2', 'b.xlsx')
    _maquina(app, 'TA')

    datos = client.get('/api/estadisticas-tipo-operacion').get_json()

    assert [a['sin_asignar'] for a in datos['por_archivo']] == [1, 1]
    assert datos['global']['sin_asignar'] == 1
    assert datos['global']['MANUAL'] == 1
    assert datos['global']['total'] == 2
