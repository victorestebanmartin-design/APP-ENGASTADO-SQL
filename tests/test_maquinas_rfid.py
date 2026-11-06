"""
Matrícula y etiqueta RFID de las máquinas, y la máquina en el report de engastado.

El lector manda una etiqueta de máquina a la misma entrada que una tarjeta de
operario: tiene que quedar apuntada para el puesto sin crear ningún login, y lo
que acaba en el report son datos copiados, que no cambian si luego se renombra.
"""
import json
import os
from datetime import datetime

import pytest
from sqlalchemy import text

from app.routes.base import db

LECTOR = 'lector-p1'
TAG = 'AABBCCDD'
TAG_OPERARIO = '11223344'


def _sql(sentencia, **parametros):
    with db.engine.begin() as conn:
        conn.execute(text(sentencia), parametros)


@pytest.fixture
def planta(app):
    with app.app_context():
        _sql("INSERT INTO puestos (id, nombre) VALUES ('p1', 'PUESTO 1')")
        _sql("INSERT INTO maquinas (id, puesto_id, nombre, tipo_operacion, matricula, tag_uid) "
             "VALUES ('m1', 'p1', 'AMP ROJA', 'MANUAL', 'M-001', :tag)", tag=TAG)
        _sql("INSERT INTO maquinas (id, puesto_id, nombre, tipo_operacion) "
             "VALUES ('m2', 'p1', 'AMP AZUL', 'MANUAL')")
        _sql("INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES ('m1', 'T1')")
        _sql("INSERT INTO operarios (id, nombre, tag_uid) VALUES ('o1', 'Ana', :tag)", tag=TAG_OPERARIO)
        _guardar_lector(app, puesto_id='p1')
        yield app


def _guardar_lector(app, puesto_id='', fw=None):
    from app.routes.sistema import _rfid_firmware_version
    with open(os.path.join(app.config['DATA_DIR'], 'esp32_rfid_devices.json'), 'w', encoding='utf-8') as f:
        json.dump({LECTOR: {'puesto_id': puesto_id, 'puesto_nombre': 'PUESTO 1' if puesto_id else '',
                            'last_seen': datetime.now().isoformat(),
                            'fw': fw or _rfid_firmware_version()}}, f)


def _pasar(client, uid, device=LECTOR):
    return client.post('/api/puestos/engastado_v3/entrada', json={'tag_uid': uid, 'device_id': device})


def _leida(client, since=None):
    q = {'since': since} if since else {}
    return client.get('/api/puestos/p1/maquina-leida', query_string=q).get_json()


# ==================== matrícula ====================

def test_matricula_se_normaliza_y_no_se_repite(planta, admin_client):
    r = admin_client.post('/api/maquinas', json={'puesto_id': 'p1', 'nombre': 'NUEVA', 'matricula': '  m - 2 '})
    assert r.get_json()['maquina']['matricula'] == 'M - 2'

    r = admin_client.post('/api/maquinas', json={'puesto_id': 'p1', 'nombre': 'OTRA', 'matricula': 'm-001'})
    assert r.status_code == 409 and 'AMP ROJA' in r.get_json()['message']

    r = admin_client.put('/api/maquinas/m2', json={'matricula': 'M-001'})
    assert r.status_code == 409
    # La suya propia no choca consigo misma
    assert admin_client.put('/api/maquinas/m1', json={'matricula': 'M-001', 'nombre': 'AMP ROJA'}).status_code == 200


def test_editar_sin_matricula_no_la_borra_y_vacia_la_quita(planta, admin_client):
    r = admin_client.put('/api/maquinas/m1', json={'nombre': 'ROJA'})
    assert r.get_json()['maquina']['matricula'] == 'M-001'
    r = admin_client.put('/api/maquinas/m1', json={'matricula': ''})
    assert r.get_json()['maquina']['matricula'] is None


def test_matricula_con_caracteres_raros_se_rechaza(planta, admin_client):
    r = admin_client.put('/api/maquinas/m2', json={'matricula': '<img src=x>'})
    assert r.status_code == 409


def test_dar_de_baja_libera_matricula_y_etiqueta(planta, admin_client):
    assert admin_client.delete('/api/maquinas/m1').status_code == 200
    assert admin_client.put('/api/maquinas/m2', json={'matricula': 'M-001'}).status_code == 200
    # Y la etiqueta de la baja ya no es de nadie
    assert _pasar(admin_client, TAG).status_code == 404


# ==================== alta de la etiqueta ====================

def _armar(cliente, maquina='m2'):
    r = cliente.post(f'/api/maquinas/{maquina}/rfid/captura', json={'device_id': LECTOR})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['token']


def _leer_captura(cliente, token, uid):
    return cliente.post('/api/esp32/rfid/operario/captura',
                        json={'device_id': LECTOR, 'token': token, 'uid': uid})


def test_capturar_etiqueta_de_maquina(planta, admin_client):
    token = _armar(admin_client)
    orden = admin_client.get(f'/api/esp32/rfid/operario/captura?device_id={LECTOR}').get_json()
    assert orden['captura']['token'] == token

    r = _leer_captura(admin_client, token, 'A1:B2:C3:D4')
    assert r.status_code == 200 and r.get_json()['operario'] == 'AMP AZUL'

    est = admin_client.get(f'/api/maquinas/m2/rfid/captura/{token}').get_json()
    assert est['estado'] == 'asignada' and est['uid'] == 'A1B2C3D4'
    maquinas = {m['id']: m for m in admin_client.get('/api/maquinas').get_json()['maquinas']}
    assert maquinas['m2']['tag_uid'] == 'A1B2C3D4'


def test_captura_rechaza_tarjeta_de_operario_y_etiqueta_de_otra_maquina(planta, admin_client):
    r = _leer_captura(admin_client, _armar(admin_client), TAG_OPERARIO)
    assert r.status_code == 409 and 'Ana' in r.get_json()['error']
    r = _leer_captura(admin_client, _armar(admin_client), TAG)
    assert r.status_code == 409 and 'AMP ROJA' in r.get_json()['error']


def test_captura_de_maquina_no_hereda_la_de_supervisor(planta, admin_client):
    _sql("INSERT INTO operario_tag_capturas (device_id, operario_id, token, estado, expira_at, tipo, ref) "
         "VALUES (:d, '', 'tok-sup', 'armada', '2099-01-01T00:00:00', 'supervisor_ensayo', 'nok')", d=LECTOR)
    _armar(admin_client)
    with db.engine.connect() as conn:
        fila = conn.execute(text("SELECT tipo, ref FROM operario_tag_capturas")).fetchone()
    assert tuple(fila) == ('maquina', 'm2')


def test_captura_exige_lector_con_firmware_al_dia(planta, admin_client):
    _guardar_lector(planta, puesto_id='p1', fw='viejo')
    r = admin_client.post('/api/maquinas/m2/rfid/captura', json={'device_id': LECTOR})
    assert r.status_code == 409 and 'firmware' in r.get_json()['error']


def test_operario_no_puede_quedarse_la_etiqueta_de_una_maquina(planta, admin_client):
    r = admin_client.put('/api/operarios/o1', json={'tag_uid': TAG})
    assert r.status_code == 409 and 'AMP ROJA' in r.get_json()['error']

    r = admin_client.post('/api/operarios/o1/rfid/captura', json={'device_id': LECTOR})
    r = _leer_captura(admin_client, r.get_json()['token'], TAG)
    assert r.status_code == 409 and 'AMP ROJA' in r.get_json()['error']


# ==================== lectura en el puesto ====================

def test_pasar_la_maquina_la_apunta_sin_crear_login(planta, client):
    desde = _leida(client)['ahora']
    r = _pasar(client, TAG)
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo['success'] and cuerpo['tipo'] == 'maquina' and 'M-001' in cuerpo['operario_nombre']
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM operario_logins")).scalar() == 0

    lectura = _leida(client, desde)['lectura']
    assert lectura['maquina']['id'] == 'm1'
    assert lectura['maquina']['terminales_asignados'] == ['T1']


def test_una_lectura_antigua_no_elige_maquina(planta, client):
    _pasar(client, TAG)
    ahora = _leida(client)
    assert ahora['lectura'] is None      # sin since: solo fija el punto de partida
    assert _leida(client, ahora['ahora'])['lectura'] is None


def test_lector_sin_puesto_rechaza_con_motivo_y_consejo(planta, client):
    _guardar_lector(planta)
    r = _pasar(client, TAG)
    assert r.status_code == 409 and 'M-001' in r.get_json()['error']
    with open(os.path.join(planta.config['DATA_DIR'], 'rfid_entrada_estado.json'), encoding='utf-8') as f:
        evento = json.load(f)[-1]
    assert evento['error_code'] == 'MAQUINA_SIN_PUESTO' and evento['consejo']


def test_la_tarjeta_de_operario_sigue_entrando(planta, client):
    r = _pasar(client, TAG_OPERARIO)
    assert r.status_code == 200 and r.get_json()['operario_nombre'] == 'Ana' and r.get_json()['login_id']


def test_puesto_sin_lector_responde_200_inactivo(planta, client):
    d = client.get('/api/puestos/otro/maquina-leida')
    assert d.status_code == 200
    assert d.get_json()['activo'] is False and d.get_json()['motivo']


# ==================== report ====================

def _bono_con_carro(app, tmp_path):
    import pandas as pd
    df = pd.DataFrame([['C1', 1.5, 'E1', 'T1', 'E2', '']],
                      columns=['Cod. cable', 'Sección', 'De Elemento', 'De Terminal', 'Para Elemento', 'Para Terminal'])
    df.to_excel(os.path.join(app.config['UPLOAD_FOLDER'], 'corte.xlsx'), index=False, sheet_name='Format')
    _sql("INSERT INTO bonos (id, nombre) VALUES ('b1', 'B1')")
    _sql("INSERT INTO ordenes_produccion (id, codigo_corte, bono_id, numero, archivo_excel) "
         "VALUES ('o1', 'C1', 'b1', 'P1', 'corte.xlsx')")


def _registro(client, bono='B1', terminal='T1', carro='1'):
    return client.get(f'/api/bonos/{bono}/progreso').get_json()['progreso'][terminal]['carros_registro'][carro]


def test_el_progreso_guarda_la_maquina_copiada(planta, admin_client):
    r = admin_client.post('/api/bonos/B1/progreso', json={'terminal': 'T1', 'carro': 1, 'operario': 'Ana',
                                                          'maquina_id': 'm1', 'maquina_origen': 'rfid'})
    assert r.get_json()['success']
    reg = r.get_json()['progreso_actual']['carros_registro']['1']
    assert (reg['maquina_nombre'], reg['maquina_matricula'], reg['maquina_origen']) == ('AMP ROJA', 'M-001', 'rfid')

    # Renombrar la máquina no reescribe lo que ya pasó
    admin_client.put('/api/maquinas/m1', json={'nombre': 'OTRO NOMBRE', 'matricula': 'M-999'})
    d = admin_client.get('/api/report/progreso?bono=B1').get_json()
    assert d['registros'][0]['maquinas'] == ['M-001 · AMP ROJA']


def test_el_progreso_parcial_sin_pendientes_tambien_guarda_la_maquina(planta, client):
    r = client.post('/api/bonos/B1/progreso/parcial', json={
        'terminal': 'T1', 'carro': 1, 'operario': 'Ana', 'paquetes_hechos': 3,
        'paquetes_pendientes': [], 'maquina_id': 'm1', 'maquina_origen': 'sin_confirmar'})
    assert r.get_json()['success']
    d = client.get('/api/report/progreso?bono=B1').get_json()
    assert d['registros'][0]['maquinas'] == ['M-001 · AMP ROJA']


def test_guardar_sin_maquina_sigue_funcionando_y_no_inventa_nada(planta, client):
    assert client.post('/api/bonos/B1/progreso', json={'terminal': 'T1', 'carro': 1}).get_json()['success']
    assert client.get('/api/report/progreso?bono=B1').get_json()['registros'][0]['maquinas'] == []


def test_origen_desconocido_cuenta_como_pantalla(planta, client):
    r = client.post('/api/bonos/B1/progreso', json={'terminal': 'T1', 'carro': 1, 'maquina_id': 'm1',
                                                    'maquina_origen': 'lo-que-sea'})
    assert r.get_json()['progreso_actual']['carros_registro']['1']['maquina_origen'] == 'pantalla'


def test_report_por_carro_tiene_columna_maquina(planta, client, tmp_path):
    _bono_con_carro(planta, tmp_path)
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T1', 'carro': 1, 'operario': 'Ana',
                                                'maquina_id': 'm1', 'maquina_origen': 'sin_confirmar'})
    html = client.get('/report/bono/B1/carros').get_data(as_text=True)
    assert '<th style="width:24%;">Máquina</th>' in html
    assert 'M-001 · AMP ROJA' in html and '(sin confirmar)' in html


def test_report_de_registros_antiguos_no_deduce_la_maquina(planta, client, tmp_path):
    """T1 está asignado a AMP ROJA hoy, pero el registro no dice quién lo hizo."""
    _bono_con_carro(planta, tmp_path)
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T1', 'carro': 1, 'operario': 'Ana'})
    html = client.get('/report/bono/B1/carros').get_data(as_text=True)
    assert 'AMP ROJA' not in html


# ==================== herencia en el pick-to-light ====================

def _asignar_herramienta(admin_client, nombre, canal=3, puesto='p1'):
    return admin_client.put('/api/pick-to-light/canal', json={
        'puesto_id': puesto, 'canal': canal, 'terminal': nombre,
        'etiqueta_gaveta': 'A-1', 'tipo': 'herramienta'})


def _uid_canal(canal=3, puesto='p1'):
    with db.engine.connect() as conn:
        return conn.execute(text(
            "SELECT uid_rfid FROM pick_to_light_canales "
            "WHERE puesto_id = :p AND canal = :c AND activo = 1"), {'p': puesto, 'c': canal}).scalar()


def _capturar_etiqueta(admin_client, maquina_id, uid):
    r = _leer_captura(admin_client, _armar(admin_client, maquina_id), uid)
    assert r.status_code == 200, r.get_json()


def test_canal_de_herramienta_hereda_la_etiqueta_de_la_maquina(planta, admin_client):
    d = _asignar_herramienta(admin_client, 'AMP ROJA').get_json()
    assert d['success'] is True and d['rfid_heredado'] == TAG and d['rfid_aviso'] is None
    assert _uid_canal() == TAG


def test_maquina_sin_etiqueta_o_nombre_libre_no_heredan(planta, admin_client):
    assert _asignar_herramienta(admin_client, 'AMP AZUL', canal=3).get_json()['rfid_heredado'] is None
    assert _asignar_herramienta(admin_client, 'Pelacables 3', canal=4).get_json()['rfid_heredado'] is None
    assert _uid_canal(3) is None and _uid_canal(4) is None


def test_un_terminal_no_hereda_aunque_se_llame_como_la_maquina(planta, admin_client):
    _sql("INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES ('m1', 'AMP ROJA')")
    r = admin_client.put('/api/pick-to-light/canal', json={
        'puesto_id': 'p1', 'canal': 3, 'terminal': 'AMP ROJA', 'etiqueta_gaveta': 'A-1'})
    assert r.get_json()['success'] is True and _uid_canal() is None


def test_etiqueta_puesta_a_mano_no_se_pisa(planta, admin_client):
    _asignar_herramienta(admin_client, 'AMP AZUL')
    _sql("UPDATE pick_to_light_canales SET uid_rfid = 'MANUAL01' WHERE canal = 3")
    _sql("UPDATE maquinas SET tag_uid = 'CCDDEEFF' WHERE id = 'm2'")
    assert _asignar_herramienta(admin_client, 'AMP AZUL').get_json()['rfid_heredado'] is None
    assert _uid_canal() == 'MANUAL01'


def test_etiqueta_ya_en_otro_canal_avisa_y_no_duplica(planta, admin_client):
    _sql("INSERT INTO pick_to_light_canales (puesto_id, canal, terminal_codigo, etiqueta_gaveta, tipo, uid_rfid, activo) "
         "VALUES ('p1', 9, 'OTRA', 'B-1', 'herramienta', :tag, 1)", tag=TAG)
    d = _asignar_herramienta(admin_client, 'AMP ROJA').get_json()
    assert d['success'] is True and d['rfid_heredado'] is None and 'canal 9' in d['rfid_aviso']
    assert _uid_canal() is None


def test_mismo_nombre_en_otro_puesto_hereda_la_del_puesto(planta, admin_client):
    _sql("INSERT INTO puestos (id, nombre) VALUES ('p2', 'PUESTO 2')")
    _sql("INSERT INTO maquinas (id, puesto_id, nombre, tipo_operacion, tag_uid) "
         "VALUES ('m9', 'p2', 'AMP ROJA', 'MANUAL', 'EEFF0011')")
    _asignar_herramienta(admin_client, 'AMP ROJA')
    assert _uid_canal() == TAG


def test_quitar_la_etiqueta_de_la_maquina_la_quita_del_canal(planta, admin_client):
    _asignar_herramienta(admin_client, 'AMP ROJA')
    assert admin_client.delete('/api/maquinas/m1/rfid').status_code == 200
    assert _uid_canal() is None


def test_cambiar_la_etiqueta_de_la_maquina_actualiza_el_canal(planta, admin_client):
    _asignar_herramienta(admin_client, 'AMP ROJA')
    _capturar_etiqueta(admin_client, 'm1', 'CAFE0001')
    assert _uid_canal() == 'CAFE0001'


def test_cambiar_la_etiqueta_respeta_la_puesta_a_mano(planta, admin_client):
    _asignar_herramienta(admin_client, 'AMP ROJA')
    _sql("UPDATE pick_to_light_canales SET uid_rfid = 'MANUAL01' WHERE canal = 3")
    _capturar_etiqueta(admin_client, 'm1', 'CAFE0001')
    assert _uid_canal() == 'MANUAL01'


# ==================== validez de la inspección ====================

def test_inspeccion_se_guarda_como_mes_se_valida_y_se_quita(planta, admin_client):
    r = admin_client.post('/api/maquinas', json={'puesto_id': 'p1', 'nombre': 'NUEVA',
                                                 'inspeccion_valida_hasta': '2027-03'})
    assert r.get_json()['maquina']['inspeccion_valida_hasta'] == '2027-03'

    for mal in ('03/2027', '2027-13', '2027-03-31'):
        r = admin_client.put('/api/maquinas/m1', json={'inspeccion_valida_hasta': mal})
        assert r.status_code == 400 and 'inspección' in r.get_json()['message'], mal

    r = admin_client.put('/api/maquinas/m1', json={'nombre': 'AMP ROJA', 'inspeccion_valida_hasta': '2027-3'})
    assert r.get_json()['maquina']['inspeccion_valida_hasta'] == '2027-03'

    # Sin el campo no se toca; vacío la quita.
    r = admin_client.put('/api/maquinas/m1', json={'nombre': 'AMP ROJA'})
    assert r.get_json()['maquina']['inspeccion_valida_hasta'] == '2027-03'
    r = admin_client.put('/api/maquinas/m1', json={'nombre': 'AMP ROJA', 'inspeccion_valida_hasta': ''})
    assert r.get_json()['maquina']['inspeccion_valida_hasta'] is None


def test_inspeccion_vale_el_mes_entero_y_avisa_a_dos_meses_de_su_final():
    from datetime import date
    from app.inspeccion import calcular
    assert calcular(None, date(2026, 11, 6))['estado'] == 'sin_anotar'
    # Enero de 2027 vale hasta el 31; el aviso empieza cuando quedan dos meses
    # contando el actual (diciembre y enero), el 1 de diciembre
    assert calcular('2027-01', date(2026, 11, 30))['estado'] == 'vigente'
    assert calcular('2027-01', date(2026, 12, 1))['estado'] == 'aviso'
    assert calcular('2027-02', date(2026, 12, 31))['estado'] == 'vigente'
    assert calcular('2027-01', date(2027, 1, 31))['estado'] == 'aviso'
    assert calcular('2027-01', date(2027, 1, 31))['bloquea'] is False
    caducada = calcular('2027-01', date(2027, 2, 1))
    assert caducada['estado'] == 'caducada' and caducada['bloquea'] is True
    assert 'enero de 2027' in caducada['motivo'] and caducada['consejo']
    # Febrero bisiesto: vale hasta el 29
    assert calcular('2028-02', date(2028, 2, 29))['bloquea'] is False
    assert calcular('2028-02', date(2028, 3, 1))['bloquea'] is True


def test_fecha_antigua_con_dia_se_queda_con_su_mes(app):
    """La 1.30.0 guardaba AAAA-MM-DD: al arrancar se recorta al mes."""
    from app import inspeccion
    assert inspeccion.calcular('2027-01-15', __import__('datetime').date(2027, 1, 31))['bloquea'] is False
    with app.app_context():
        _sql("INSERT INTO puestos (id, nombre) VALUES ('px', 'PX')")
        _sql("INSERT INTO maquinas (id, puesto_id, nombre, inspeccion_valida_hasta) "
             "VALUES ('mx', 'px', 'VIEJA', '2027-01-15')")
        from app import _apply_migrations
        _apply_migrations(app.config['DB_PATH'])
        with db.engine.connect() as conn:
            assert conn.execute(text("SELECT inspeccion_valida_hasta FROM maquinas WHERE id='mx'")).scalar() == '2027-01'


def _datos_trabajo(client):
    return client.get('/api/datos_trabajo_v3?archivo=x.xlsx&terminal=T1&maquina=m1&iniciar_sesion=true')


def test_servidor_bloquea_inspeccion_caducada_hasta_anotar_la_nueva(planta, client, admin_client):
    _sql("UPDATE maquinas SET inspeccion_valida_hasta = '2020-01' WHERE id = 'm1'")
    r = _datos_trabajo(client)
    d = r.get_json()
    assert r.status_code == 409 and d['inspeccion_caducada'] is True and d['consejo']
    assert 'enero de 2020' in d['message']
    assert client.get('/api/maquinas/m1/inspeccion').get_json()['bloquea'] is True

    # La ficha lo levanta en cuanto se anota la nueva
    admin_client.put('/api/maquinas/m1', json={'nombre': 'AMP ROJA', 'inspeccion_valida_hasta': '2099-01'})
    assert not _datos_trabajo(client).get_json().get('inspeccion_caducada')
    assert client.get('/api/maquinas/m1/inspeccion').get_json()['estado'] == 'vigente'


def test_sin_fecha_de_inspeccion_ni_avisa_ni_bloquea(planta, client):
    assert not _datos_trabajo(client).get_json().get('inspeccion_caducada')
    d = client.get('/api/maquinas/m1/inspeccion').get_json()
    assert d['estado'] == 'sin_anotar' and d['bloquea'] is False
    assert client.get('/api/maquinas/noexiste/inspeccion').get_json()['bloquea'] is False
