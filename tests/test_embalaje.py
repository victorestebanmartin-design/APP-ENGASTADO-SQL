"""
Embalaje (app/embalaje.py, app/routes/embalaje.py).

Lo que se vigila:
  - Solo se embala una orden con todas sus máquinas acabadas; con paquetes
    pendientes, solo con supervisor.
  - El reparto se guarda por código de corte y la siguiente orden lo hereda.
  - Rehacer un reparto guardado pide supervisor; completarlo con paquetes
    nuevos, no.
  - Una serie es un solo paquete.
  - Los carteles salen por la impresora de red y queda apuntado quién embaló.
"""
import json

import pandas as pd
import pytest
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from app import embalaje, impresion_planchas as ip
from app.routes.base import db


def _sql(app, sentencia, **p):
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(text(sentencia), p)


def _excel(app, nombre, filas):
    pd.DataFrame(filas, columns=['Cod. cable', 'Sección', 'De Elemento', 'De Elemento Etiquetas',
                                 'De Terminal', 'Para Elemento', 'Para Terminal']
                 ).to_excel(f"{app.config['UPLOAD_FOLDER']}/{nombre}", index=False)


def _etiquetas(app, archivo, codigo, filas):
    """filas: (numero, sub, padre, serie, cod_cable, elemento)"""
    for n, sub, padre, serie, cod, el in filas:
        _sql(app, "INSERT INTO etiquetas_elementos (archivo_excel, codigo_corte, numero_etiqueta, "
                  "sub_numero, es_grupo_padre, grupo_serie, cod_cable, elemento, descripcion, seccion) "
                  "VALUES (:a, :c, :n, :s, :p, :g, :cc, :e, 'desc', '1')",
             a=archivo, c=codigo, n=n, s=sub, p=padre, g=serie, cc=cod, e=el)


@pytest.fixture
def planta(app):
    """Bono B1 con dos órdenes del mismo corte H01 (carros 1 y 2).
    Terminales T1 y T2, los dos en una máquina activa."""
    _sql(app, "INSERT INTO puestos (id, nombre) VALUES ('p1', 'Puesto 1')")
    _sql(app, "INSERT INTO maquinas (id, puesto_id, nombre, activo) VALUES ('m1', 'p1', 'M1', 1)")
    for t in ('T1', 'T2'):
        _sql(app, "INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES ('m1', :t)", t=t)
    _excel(app, 'h01.xlsx', [['C1', '1', 'X1', 'X1', 'T1', 'X2', 'T2'],
                             ['C2', '1', 'X3', 'X3', 'T1', 'X4', ''],
                             ['C3', '1', 'X5', 'X5', 'T2', 'X6', '']])
    _etiquetas(app, 'h01.xlsx', 'H01', [
        (1, 0, 0, None, 'C1', 'X1'),
        (2, 0, 0, None, 'C2', 'X3'),
        (3, 0, 1, 'S1', 'GRUPO_SERIE', 'S1'),
        (3, 1, 0, 'S1', 'C3', 'X5'),
        (3, 2, 0, 'S1', 'C4', 'X7'),
    ])
    _sql(app, "INSERT INTO bonos (id, nombre) VALUES ('b1', 'B1')")
    _sql(app, "INSERT INTO ordenes_produccion (id, codigo_corte, bono_id, numero, descripcion, cantidad, "
              "archivo_excel, fecha_creacion) VALUES ('o1', 'H01', 'b1', '600', 'Mazo puerta', 50, "
              "'h01.xlsx', '2026-01-01 08:00:00')")
    _sql(app, "INSERT INTO ordenes_produccion (id, codigo_corte, bono_id, numero, descripcion, cantidad, "
              "archivo_excel, fecha_creacion) VALUES ('o2', 'H01', 'b1', '601', 'Mazo puerta', 200, "
              "'h01.xlsx', '2026-01-01 09:00:00')")
    _sql(app, "INSERT INTO operarios (id, nombre, modulos_permitidos, clave_personal_hash, tag_uid) "
              "VALUES ('sup', 'Supervisora', :p, :c, 'AABBCCDD')",
         p=json.dumps(['engastado', 'ensayos_supervisor']), c=generate_password_hash('clave123'))
    _sql(app, "INSERT INTO operarios (id, nombre, tag_uid, clave_personal_hash) "
              "VALUES ('op', 'Operario', '11223344', :c)", c=generate_password_hash('clave123'))
    return app


def _engastar(client, terminal, carro):
    r = client.post('/api/bonos/B1/progreso', json={'terminal': terminal, 'carro': carro, 'operario': 'Ana'})
    assert r.get_json()['success']


def _ordenes(client):
    return {o['id']: o for o in client.get('/api/embalaje/bono/B1').get_json()['ordenes']}


def _reparto(client, orden, cajas, asign):
    return client.post(f'/api/embalaje/orden/{orden}/reparto',
                       json={'num_cajas': cajas, 'asignaciones': asign, 'operario': 'Operario'})


def _supervisor(client, orden):
    r = client.post('/api/embalaje/supervisor', json={'orden_id': orden, 'usuario': 'sup', 'clave': 'clave123'})
    assert r.status_code == 200, r.get_json()


CLAVES = {'uno': 'C1|X1', 'dos': 'C2|X3', 'serie': 'GRUPO_SERIE|S1'}


# ==================== cuándo se puede embalar ====================

def test_sin_engastar_nada_esta_en_gris_y_el_boton_apagado(planta, client):
    assert client.get('/api/embalaje/disponible').get_json()['disponible'] is False
    o = _ordenes(client)
    assert o['o1']['estado'] == 'incompleta' and 'terminales' in o['o1']['motivo']


def test_orden_completa_cuando_todas_sus_maquinas_acaban_ese_carro(planta, client):
    _engastar(client, 'T1', 1)
    assert _ordenes(client)['o1']['estado'] == 'incompleta'
    _engastar(client, 'T2', 1)
    o = _ordenes(client)
    assert o['o1']['estado'] == 'completa'
    assert o['o2']['estado'] == 'incompleta'          # carro 2: nadie ha pasado
    assert client.get('/api/embalaje/disponible').get_json()['disponible'] is True
    bonos = client.get('/api/embalaje/bonos').get_json()['bonos']
    assert [(b['nombre'], b['listas'], b['total']) for b in bonos] == [('B1', 1, 2)]


def test_terminal_sin_maquina_no_impide_embalar(planta, client):
    _sql(planta, "DELETE FROM maquinas_terminales WHERE terminal_codigo = 'T2'")
    _engastar(client, 'T1', 1)
    assert _ordenes(client)['o1']['estado'] == 'completa'


def test_paquetes_pendientes_piden_supervisor(planta, client):
    _engastar(client, 'T1', 1)
    client.post('/api/bonos/B1/progreso/parcial', json={
        'terminal': 'T2', 'carro': 1, 'paquetes_pendientes': [{'elemento': 'X2', 'cod_cable': 'C1'}]})
    assert _ordenes(client)['o1']['estado'] == 'pendientes'

    r = _reparto(client, 'o1', 1, {c: 1 for c in CLAVES.values()})
    assert r.status_code == 403 and r.get_json()['supervisor_requerido'] is True
    _supervisor(client, 'o1')
    assert _reparto(client, 'o1', 1, {c: 1 for c in CLAVES.values()}).status_code == 200


def test_orden_incompleta_no_se_puede_repartir(planta, client):
    r = _reparto(client, 'o1', 1, {c: 1 for c in CLAVES.values()})
    assert r.status_code == 409 and 'terminada' in r.get_json()['motivo']


def test_bono_cerrado_cuenta_como_terminado(planta, client):
    _sql(planta, "UPDATE ordenes_produccion SET estado = 'completado', fecha_completado = datetime('now')")
    _sql(planta, "UPDATE bonos SET estado = 'completado'")
    assert {o['estado'] for o in _ordenes(client).values()} == {'completa'}
    assert client.get('/api/embalaje/disponible').get_json()['disponible'] is True


# ==================== paquetes y reparto ====================

def test_una_serie_es_un_solo_paquete(planta, client):
    _engastar(client, 'T1', 1)
    _engastar(client, 'T2', 1)
    d = client.get('/api/embalaje/orden/o1').get_json()
    assert [p['clave'] for p in d['paquetes']] == list(CLAVES.values())
    serie = d['paquetes'][2]
    assert serie['es_serie'] and [c['etiqueta'] for c in serie['contenido']] == ['3.01', '3.02']
    assert d['reparto'] is None


def test_reparto_sin_caja_o_con_caja_vacia_no_se_guarda(planta, client):
    _engastar(client, 'T1', 1)
    _engastar(client, 'T2', 1)
    r = _reparto(client, 'o1', 2, {CLAVES['uno']: 1, CLAVES['dos']: 1})
    assert r.status_code == 400 and r.get_json()['sin_caja'] == ['3']
    r = _reparto(client, 'o1', 2, {c: 1 for c in CLAVES.values()})
    assert r.status_code == 400 and 'caja 2' in r.get_json()['motivo']


def test_la_siguiente_orden_del_mismo_corte_sale_guiada(planta, client):
    for t in ('T1', 'T2'):
        _engastar(client, t, 1)
        _engastar(client, t, 2)
    asign = {CLAVES['uno']: 1, CLAVES['dos']: 2, CLAVES['serie']: 2}
    assert _reparto(client, 'o1', 2, asign).get_json()['success']

    d = client.get('/api/embalaje/orden/o2').get_json()
    assert d['reparto']['num_cajas'] == 2 and d['reparto']['asignaciones'] == asign
    assert d['cantidad_distinta'] is True     # 50 en el reparto, 200 en esta orden
    assert d['paquetes_nuevos'] == []


def test_rehacer_un_reparto_guardado_pide_supervisor(planta, client):
    _engastar(client, 'T1', 1)
    _engastar(client, 'T2', 1)
    _reparto(client, 'o1', 2, {CLAVES['uno']: 1, CLAVES['dos']: 2, CLAVES['serie']: 2})

    r = _reparto(client, 'o1', 2, {CLAVES['uno']: 2, CLAVES['dos']: 1, CLAVES['serie']: 2})
    assert r.status_code == 403 and r.get_json()['supervisor_requerido']
    r = _reparto(client, 'o1', 1, {c: 1 for c in CLAVES.values()})
    assert r.status_code == 403

    # Guardar lo mismo no es cambiar nada
    assert _reparto(client, 'o1', 2, {CLAVES['uno']: 1, CLAVES['dos']: 2, CLAVES['serie']: 2}).status_code == 200

    _supervisor(client, 'o1')
    assert _reparto(client, 'o1', 1, {c: 1 for c in CLAVES.values()}).get_json()['cambio'] is True
    with planta.app_context(), db.engine.connect() as conn:
        filas = conn.execute(text("SELECT num_cajas, activo, supervisor FROM embalaje_repartos "
                                  "ORDER BY created_at, rowid")).fetchall()
    assert [tuple(f) for f in filas] == [(2, 0, None), (1, 1, 'Supervisora')]


def test_paquete_nuevo_en_el_excel_se_completa_sin_supervisor(planta, client):
    _engastar(client, 'T1', 1)
    _engastar(client, 'T2', 1)
    _reparto(client, 'o1', 2, {CLAVES['uno']: 1, CLAVES['dos']: 2, CLAVES['serie']: 2})
    _etiquetas(planta, 'h01.xlsx', 'H01', [(4, 0, 0, None, 'C9', 'X9')])

    d = client.get('/api/embalaje/orden/o1').get_json()
    assert d['paquetes_nuevos'] == ['C9|X9']
    r = client.post('/api/embalaje/orden/o1/carteles', json={'operario': 'Operario'})
    assert r.status_code == 409 and r.get_json()['sin_caja'] == ['4']

    asign = {**d['reparto']['asignaciones'], 'C9|X9': 1}
    r = _reparto(client, 'o1', 2, asign)
    assert r.status_code == 200 and r.get_json()['cambio'] is False


def test_operario_no_supervisor_no_autoriza(planta, client):
    r = client.post('/api/embalaje/supervisor', json={'orden_id': 'o1', 'usuario': 'op', 'clave': 'clave123'})
    assert r.status_code == 403 and 'supervisor' in r.get_json()['motivo']


# ==================== carteles ====================

def _lista_para_imprimir(planta, client):
    _engastar(client, 'T1', 1)
    _engastar(client, 'T2', 1)
    _reparto(client, 'o1', 2, {CLAVES['uno']: 1, CLAVES['dos']: 2, CLAVES['serie']: 2})


def test_carteles_salen_por_la_impresora_y_queda_apuntado(planta, client, monkeypatch):
    _lista_para_imprimir(planta, client)
    ip.guardar_config(planta.config['DATA_DIR'], '192.168.1.50')
    enviado = {}
    monkeypatch.setattr(ip, 'html_a_pdf', lambda html: enviado.setdefault('html', html) and b'%PDF-')
    monkeypatch.setattr(ip, 'enviar_a_impresora', lambda pdf, i, p: enviado.update(ip=i))

    r = client.post('/api/embalaje/orden/o1/carteles', json={'operario': 'Operario', 'operario_via': 'tarjeta'})
    assert r.get_json()['success'] is True and r.get_json()['cajas'] == [1, 2]
    html = enviado['html']
    assert enviado['ip'] == '192.168.1.50'
    for dato in ('H01', 'Mazo puerta', '600', '50', 'CAJA <b>1</b> de 2', 'CAJA <b>2</b> de 2', 'Serie S1'):
        assert dato in html

    emb = _ordenes(client)['o1']['embalada']
    assert emb['operario'] == 'Operario' and emb['cajas_impresas'] == '1,2'


def test_reimprimir_una_sola_caja(planta, client, monkeypatch):
    _lista_para_imprimir(planta, client)
    ip.guardar_config(planta.config['DATA_DIR'], '192.168.1.50')
    enviado = {}
    monkeypatch.setattr(ip, 'html_a_pdf', lambda html: enviado.setdefault('html', html) and b'%PDF-')
    monkeypatch.setattr(ip, 'enviar_a_impresora', lambda pdf, i, p: None)
    r = client.post('/api/embalaje/orden/o1/carteles', json={'cajas': [2], 'operario': 'Operario'})
    assert r.get_json()['cajas'] == [2]
    assert 'CAJA <b>2</b>' in enviado['html'] and 'CAJA <b>1</b>' not in enviado['html']


def test_sin_impresora_responde_200_con_motivo_y_no_apunta(planta, client, monkeypatch):
    _lista_para_imprimir(planta, client)
    monkeypatch.setattr(ip, 'html_a_pdf', lambda html: b'%PDF-')
    r = client.post('/api/embalaje/orden/o1/carteles', json={'operario': 'Operario'})
    assert r.status_code == 200
    d = r.get_json()
    assert d['success'] is False and d['sin_impresora'] is True and d['consejo']
    assert _ordenes(client)['o1']['embalada'] is None


def test_carteles_html_para_imprimir_desde_el_navegador(planta, client):
    _lista_para_imprimir(planta, client)
    html = client.get('/api/embalaje/orden/o1/carteles.html?cajas=1').get_data(as_text=True)
    assert 'CAJA <b>1</b> de 2' in html and 'CAJA <b>2</b>' not in html


def test_sin_reparto_no_hay_carteles(planta, client):
    _engastar(client, 'T1', 1)
    _engastar(client, 'T2', 1)
    r = client.post('/api/embalaje/orden/o1/carteles', json={})
    assert r.status_code == 409 and 'reparto' in r.get_json()['motivo']


# ==================== tarjeta en el lector ====================

def test_tarjeta_de_operario_al_embalar(planta, client, monkeypatch):
    from app.routes import embalaje as rutas
    monkeypatch.setattr(rutas, '_lector_listo', lambda puesto: 'lector-p1')
    token = client.post('/api/embalaje/operario/tarjeta', json={'puesto_id': 'p1'}).get_json()['token']

    r = client.post('/api/esp32/rfid/operario/captura',
                    json={'device_id': 'lector-p1', 'token': token, 'uid': '99999999'})
    assert r.status_code == 409   # no registrada: sigue esperando
    assert client.get(f'/api/embalaje/operario/tarjeta/{token}').get_json()['estado'] == 'armada'

    r = client.post('/api/esp32/rfid/operario/captura',
                    json={'device_id': 'lector-p1', 'token': token, 'uid': '11223344'})
    assert r.status_code == 200
    d = client.get(f'/api/embalaje/operario/tarjeta/{token}').get_json()
    assert d['estado'] == 'asignada' and d['operario'] == 'Operario'


def test_sin_lector_se_elige_de_la_lista(planta, client):
    r = client.post('/api/embalaje/operario/tarjeta', json={'puesto_id': 'p1'})
    assert r.status_code == 409 and r.get_json()['sin_lector'] is True


def test_tarjeta_de_supervisor_autoriza_una_vez(planta, client, monkeypatch):
    from app.routes import embalaje as rutas
    monkeypatch.setattr(rutas, '_lector_listo', lambda puesto: 'lector-p1')
    token = client.post('/api/embalaje/supervisor/tarjeta',
                        json={'orden_id': 'o1', 'puesto_id': 'p1'}).get_json()['token']
    assert client.post('/api/esp32/rfid/operario/captura',
                       json={'device_id': 'lector-p1', 'token': token, 'uid': 'AABBCCDD'}).status_code == 200
    assert client.get(f'/api/embalaje/supervisor/tarjeta/{token}').get_json()['supervisor'] == 'Supervisora'
    r = client.post('/api/embalaje/supervisor', json={'orden_id': 'o1', 'token': token})
    assert r.get_json()['supervisor'] == 'Supervisora'
    # La misma lectura no vale dos veces
    assert client.post('/api/embalaje/supervisor', json={'orden_id': 'o1', 'token': token}).status_code == 403


# ==================== lógica pura ====================

def test_es_cambio_ignora_paquetes_que_el_reparto_no_conocia():
    reparto = {'num_cajas': 2, 'asignaciones': {'a': 1, 'b': 2}}
    assert embalaje.es_cambio(reparto, 2, {'a': 1, 'b': 2, 'nuevo': 1}) is False
    assert embalaje.es_cambio(reparto, 2, {'a': 2, 'b': 2}) is True
    assert embalaje.es_cambio(reparto, 3, {'a': 1, 'b': 2}) is True
    assert embalaje.es_cambio(None, 3, {'a': 1}) is False


def test_rejilla_del_cartel_cabe_en_la_hoja_apaisada_y_no_agranda():
    from app.routes import embalaje as rutas
    assert rutas._rejilla(3) == (3, 1.0)      # pocas: tamaño real, no gigantes
    for n in range(1, 200):
        cols, s = rutas._rejilla(n)
        assert s <= 1.0
        filas = -(-n // cols)
        assert cols * rutas._ETQ_ANCHO_MM * s <= rutas._REJILLA_ANCHO_MM + 0.01
        if s > 0.45:  # por debajo se deja pasar a otra hoja antes que hacerla ilegible
            assert filas * rutas._ETQ_ALTO_MM * s <= rutas._REJILLA_ALTO_MM + 0.01


# ==================== observaciones ====================

def _obs(client, orden, clave, texto):
    return client.post(f'/api/embalaje/orden/{orden}/observacion',
                       json={'clave': clave, 'texto': texto, 'operario': 'Operario'})


def _paquete(client, orden, clave):
    return next(p for p in client.get(f'/api/embalaje/orden/{orden}').get_json()['paquetes']
                if p['clave'] == clave)


def test_observacion_se_guarda_y_la_hereda_la_siguiente_orden(planta, client):
    for t in ('T1', 'T2'):
        _engastar(client, t, 1)
        _engastar(client, t, 2)
    _supervisor(client, 'o1')
    _supervisor(client, 'o2')
    r = _obs(client, 'o1', CLAVES['dos'], '  poner   capuchón ')
    assert r.get_json()['success'] and r.get_json()['observacion'] == 'poner capuchón'
    assert _paquete(client, 'o1', CLAVES['dos'])['observacion'] == 'poner capuchón'
    assert _paquete(client, 'o2', CLAVES['dos'])['observacion'] == 'poner capuchón'
    assert _paquete(client, 'o2', CLAVES['uno'])['observacion'] == ''

    assert _obs(client, 'o2', CLAVES['dos'], '').get_json()['observacion'] == ''
    assert _paquete(client, 'o1', CLAVES['dos'])['observacion'] == ''


def test_observacion_sobrevive_a_rehacer_el_reparto(planta, client):
    _lista_para_imprimir(planta, client)
    _supervisor(client, 'o1')
    _obs(client, 'o1', CLAVES['uno'], 'encintar')
    assert _reparto(client, 'o1', 1, {c: 1 for c in CLAVES.values()}).get_json()['cambio'] is True
    assert _paquete(client, 'o1', CLAVES['uno'])['observacion'] == 'encintar'


def test_observacion_de_un_paquete_ajeno_o_muy_larga_se_rechaza(planta, client):
    _supervisor(client, 'o1')
    assert _obs(client, 'o1', 'ZZ|ZZ', 'x').status_code == 400
    r = _obs(client, 'o1', CLAVES['uno'], 'x' * 201)
    assert r.status_code == 400 and r.get_json()['consejo']


def test_observacion_sale_en_el_cartel_con_asterisco(planta, client):
    _lista_para_imprimir(planta, client)
    _supervisor(client, 'o1')
    _obs(client, 'o1', CLAVES['dos'], 'poner capuchón')
    html = client.get('/api/embalaje/orden/o1/carteles.html?cajas=2').get_data(as_text=True)
    assert 'Antes de meterlos en la caja' in html and 'poner capuchón' in html
    assert "class='etq con-obs'" in html
    html1 = client.get('/api/embalaje/orden/o1/carteles.html?cajas=1').get_data(as_text=True)
    assert 'poner capuchón' not in html1      # el paquete va en la caja 2


# ==================== nombres de las cajas ====================

def _nombre(client, orden, caja, nombre):
    return client.post(f'/api/embalaje/orden/{orden}/caja_nombre',
                       json={'caja': caja, 'nombre': nombre, 'operario': 'Operario'})


def test_nombre_de_caja_sale_en_el_cartel_sin_quitar_caja_n_de_m(planta, client):
    _lista_para_imprimir(planta, client)
    _supervisor(client, 'o1')
    r = _nombre(client, 'o1', 2, ' Conectores ')
    assert r.get_json()['success'] and r.get_json()['nombre'] == 'Conectores'
    assert client.get('/api/embalaje/orden/o1').get_json()['nombres_cajas'] == {'2': 'Conectores'}
    html = client.get('/api/embalaje/orden/o1/carteles.html?cajas=2').get_data(as_text=True)
    assert 'CAJA <b>2</b> de 2' in html and 'Conectores' in html


def test_nombre_de_caja_lo_hereda_el_codigo_de_corte_y_se_puede_quitar(planta, client):
    for t in ('T1', 'T2'):
        _engastar(client, t, 1)
        _engastar(client, t, 2)
    _supervisor(client, 'o1')
    _supervisor(client, 'o2')
    _nombre(client, 'o1', 1, 'Lado izquierdo')
    assert client.get('/api/embalaje/orden/o2').get_json()['nombres_cajas'] == {'1': 'Lado izquierdo'}
    assert _nombre(client, 'o2', 1, '').get_json()['nombre'] == ''
    assert client.get('/api/embalaje/orden/o1').get_json()['nombres_cajas'] == {}


def test_nombre_de_caja_invalido_se_rechaza_con_consejo(planta, client):
    _lista_para_imprimir(planta, client)
    _supervisor(client, 'o1')
    assert _nombre(client, 'o1', 0, 'x').status_code == 400
    r = _nombre(client, 'o1', 1, 'x' * 41)
    assert r.status_code == 400 and r.get_json()['consejo']


def test_cartel_junta_las_observaciones_iguales_en_una_linea():
    from app.routes import embalaje as rutas
    ps = [{'etiqueta': str(i), 'observacion': 'AGRUPAR CON BRIDA'} for i in (40, 55, 56)]
    ps.append({'etiqueta': '9', 'observacion': 'otra'})
    grupos = rutas._grupos_obs(ps)
    assert [(t, [p['etiqueta'] for p in g]) for t, g in grupos] ==         [('AGRUPAR CON BRIDA', ['40', '55', '56']), ('otra', ['9'])]
    assert rutas._alto_obs(grupos) == rutas._OBS_FIJO_MM + 2 * rutas._OBS_FILA_MM


def test_observacion_y_nombre_de_caja_piden_supervisor(planta, client, app):
    _lista_para_imprimir(planta, client)
    for r in (_obs(client, 'o1', CLAVES['uno'], 'encintar'), _nombre(client, 'o1', 1, 'Puerta')):
        d = r.get_json()
        assert r.status_code == 403 and d['supervisor_requerido'] and d['consejo']
    assert _paquete(client, 'o1', CLAVES['uno'])['observacion'] == ''
    assert client.get('/api/embalaje/orden/o1').get_json()['nombres_cajas'] == {}

    _supervisor(client, 'o1')
    assert _obs(client, 'o1', CLAVES['uno'], 'encintar').get_json()['success']
    assert _nombre(client, 'o1', 1, 'Puerta').get_json()['success']
    with app.app_context():
        from app.routes.base import db
        from sqlalchemy import text
        with db.engine.connect() as conn:
            assert conn.execute(text("SELECT supervisor FROM embalaje_observaciones")).scalar() == 'Supervisora'
            assert conn.execute(text("SELECT supervisor FROM embalaje_cajas_nombres")).scalar() == 'Supervisora'
