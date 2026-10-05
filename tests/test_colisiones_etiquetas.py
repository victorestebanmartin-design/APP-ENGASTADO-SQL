"""
La máquina de corte junta lo que comparte (cable, elemento) aunque sea de
series distintas: una etiqueta se queda en la hoja y las demás van a reserva.
"""
import re

import pandas as pd

from app.colisiones_etiquetas import detectar_colisiones, etiqueta_texto
from app.routes.etiquetas import generar_html_etiquetas_impresion


def _e(num, sub, cod, elem, n=1, serie=None, padre=0):
    return {'numero_etiqueta': num, 'sub_numero': sub, 'cod_cable': cod,
            'elemento': elem, 'num_cables': n, 'grupo_serie': serie,
            'es_grupo_padre': padre, 'seccion': '1', 'descripcion': ''}


ETIQ = [
    _e(1, 0, 'GRUPO_SERIE', '202', padre=1, serie='202'),
    _e(1, 1, 'C1', 'K4', serie='202'),
    _e(1, 2, 'C1', 'K5', serie='202'),
    _e(2, 0, 'GRUPO_SERIE', '203', padre=1, serie='203'),
    _e(2, 1, 'C1', 'K4', n=3, serie='203'),
    _e(3, 0, 'C1', 'K4', n=3),
    _e(4, 0, 'C2', 'K4'),
]


def test_etiqueta_texto():
    assert etiqueta_texto(1, 7) == '1.07'
    assert etiqueta_texto(24, 0) == '24'


def _txt(e):
    return etiqueta_texto(e['numero_etiqueta'], e['sub_numero'])


def test_la_etiqueta_suelta_predomina_sobre_las_de_serie():
    c = detectar_colisiones(ETIQ)[0]
    assert (c['cod_cable'], c['elemento']) == ('C1', 'K4')
    # La 3 es la única fuera de serie: gana aunque 1.01 y 2.01 tengan igual o más cables
    assert _txt(c['principal']) == '3'
    assert [_txt(r) for r in c['reservas']] == ['1.01', '2.01']


def test_sin_etiqueta_suelta_gana_la_de_mas_cables_y_luego_la_mas_baja():
    solo_series = [e for e in ETIQ if not (e['numero_etiqueta'] == 3)]
    c = detectar_colisiones(solo_series)[0]
    assert _txt(c['principal']) == '2.01'          # 3 cables frente a 1
    empate = [_e(1, 1, 'C1', 'K4', n=2, serie='a'), _e(2, 1, 'C1', 'K4', n=2, serie='b')]
    assert _txt(detectar_colisiones(empate)[0]['principal']) == '1.01'


def test_cabeceras_de_serie_y_otros_cables_no_colisionan():
    assert detectar_colisiones([ETIQ[0], ETIQ[3], ETIQ[6]]) == []


def test_hoja_pone_las_reservas_en_la_misma_rejilla_desde_una_fila_nueva():
    html = generar_html_etiquetas_impresion(ETIQ, 'x.xlsx')
    assert 'reserva-box' not in html            # un recuadro desplazaría la rejilla troquelada
    assert html.count('etiqueta-reserva"') == 2
    # Normales: 5 (4 de ellas con cabecera) → la fila se rellena hasta 13 antes de las reservas
    cuerpo = html[html.index('<div class="etiquetas-container">'):]
    marcas = [m.strip() for m in re.findall(r'class="(etiqueta-vacia|etiqueta etiqueta-reserva|etiqueta)"', cuerpo)]
    marcas = ['etiqueta-reserva' if m.endswith('reserva') else m for m in marcas]
    primera_reserva = marcas.index('etiqueta-reserva')
    assert primera_reserva == 13
    assert marcas[:primera_reserva].count('etiqueta') == 5
    assert '>1.01<' in cuerpo[cuerpo.index('etiqueta-reserva"'):] and 'cortado en 3<' in cuerpo


def test_hoja_sin_colisiones_no_pinta_reservas():
    html = generar_html_etiquetas_impresion([ETIQ[0], ETIQ[6]], 'x.xlsx')
    assert 'etiqueta-reserva"' not in html and 'etiqueta-vacia"' not in html


def test_endpoint_reetiquetado_reparte_por_marca_y_longitud(client, app, monkeypatch):
    from app.routes import manguitos as m

    df = pd.DataFrame({
        'Cod. cable': ['C1', 'C1', 'C1'],
        'De Elemento Etiquetas': ['K4', 'K4', 'K4'],
        'Series': ['202', '203', '203'],
        'Cable / Marca': ['202', '203', '203'],
        'Longitud': [0.3, 0.3, 0.3],
    })
    monkeypatch.setattr(m, 'leer_excel_cacheado', lambda p: df)
    monkeypatch.setattr(m.ExcelManager, '_ruta_segura', lambda self, f: __file__)

    with app.app_context():
        from sqlalchemy import text
        with m.db.engine.connect() as conn:
            for num, sub, serie, n in ((1, 1, '202', 1), (2, 1, '203', 2)):
                conn.execute(text(
                    "INSERT INTO etiquetas_elementos (archivo_excel, codigo_corte, numero_etiqueta,"
                    " sub_numero, es_grupo_padre, grupo_serie, cod_cable, elemento, num_cables)"
                    " VALUES ('a.xlsx','a',:n,:s,0,:g,'C1','K4',:c)"), {'n': num, 's': sub, 'g': serie, 'c': n})
            conn.commit()

    r = client.post('/api/manguitos/reetiquetado', json={'archivo': 'a.xlsx'}).get_json()
    assert r['success'] and len(r['colisiones']) == 1
    c = r['colisiones'][0]
    assert c['principal']['etiqueta'] == '2.01'      # más cables (ambas en serie)
    assert c['reservas'][0]['etiqueta'] == '1.01'
    assert c['reservas'][0]['cables'] == [
        {'marca': '202', 'longitud': 0.3, 'cantidad': 1, 'igual_en_principal': False}]
