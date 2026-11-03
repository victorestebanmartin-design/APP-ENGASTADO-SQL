"""
Ensayos de tracción (app/ensayos.py, app/routes/ensayos.py).

Lo que se vigila:
  - Se ensaya la MATRIZ: un OK con un terminal cubre a los demás de esa matriz.
  - Diaria = cada día; mensual = cada mes natural.
  - Un NOK bloquea hasta que un supervisor decide; «continuar» vale hasta
    el final de ese día.
  - Regular la máquina pide repetir el ensayo, pero no levanta un NOK.
  - El servidor bloquea el engaste aunque la pantalla no pregunte.
  - El registro solo admite inserciones.
"""
import io
import json
from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from app import ensayos
from app.routes.base import db


class Reloj:
    def __init__(self, ahora):
        self.ahora = ahora

    def __call__(self):
        return self.ahora


@pytest.fixture
def reloj(monkeypatch):
    r = Reloj(datetime(2026, 11, 3, 8, 0, 0))
    monkeypatch.setattr(ensayos, 'ahora_local', r)
    return r


@pytest.fixture
def planta(app):
    """Máquina AUTO con dos matrices: A1 (T1) y A2 (T2, T3). T4 sin matriz."""
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(text("INSERT INTO puestos (id, nombre) VALUES ('p1', 'Puesto 1')"))
        conn.execute(text(
            "INSERT INTO maquinas (id, puesto_id, nombre, tipo_operacion, ensayo_frecuencia) "
            "VALUES ('m1', 'p1', 'AUTO-1', 'AUTOMATICA', 'diaria')"))
        conn.execute(text("INSERT INTO matrices (id, maquina_id, nombre) VALUES "
                          "('a1', 'm1', 'A1'), ('a2', 'm1', 'A2')"))
        for t, mz in (('T1', 'a1'), ('T2', 'a2'), ('T3', 'a2'), ('T4', None)):
            conn.execute(text("INSERT INTO maquinas_terminales (maquina_id, terminal_codigo, matriz_id) "
                              "VALUES ('m1', :t, :mz)"), {'t': t, 'mz': mz})
        conn.execute(text("INSERT INTO ensayos_especificaciones (terminal_codigo, seccion, fuerza_min_n, norma) "
                          "VALUES ('', '1.5', 155, 'IEC 60352-2'), ('T2', '1.5', 170, 'Cliente')"))
        conn.execute(text(
            "INSERT INTO operarios (id, nombre, modulos_permitidos, clave_personal_hash, tag_uid) "
            "VALUES ('sup', 'Supervisora', :p, :c, 'AABBCCDD')"),
            {'p': json.dumps(['ensayos_supervisor']), 'c': generate_password_hash('clave123')})
        conn.execute(text("INSERT INTO operarios (id, nombre, tag_uid) VALUES ('op', 'Operario', '11223344')"))
    return app


def _estado(client, terminal='T1', maquina='m1'):
    return client.get(f'/api/ensayos/estado?maquina_id={maquina}&terminal={terminal}').get_json()


def _ensayar(client, fuerza, terminal='T1', seccion='1,5'):
    return client.post('/api/ensayos', json={'maquina_id': 'm1', 'terminal': terminal,
                                             'seccion': seccion, 'fuerza_n': fuerza,
                                             'operario': 'Operario'})


def _decidir(client, nok_id, decision, comentario=''):
    return client.post(f'/api/ensayos/{nok_id}/decision', json={
        'decision': decision, 'comentario': comentario,
        'usuario': 'sup', 'clave': 'clave123'})


# ==================== reglas ====================

def test_maquina_sin_frecuencia_no_pide_ensayo(planta, client, reloj):
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE maquinas SET ensayo_frecuencia = NULL"))
    d = _estado(client)
    assert d['requerido'] is False and d['bloquea'] is False


def test_diaria_ok_vale_hasta_el_dia_siguiente(planta, client, reloj):
    assert _estado(client)['bloquea'] is True
    r = _ensayar(client, 160)
    assert r.status_code == 200 and r.get_json()['ensayo']['resultado'] == 'OK'
    reloj.ahora = datetime(2026, 11, 3, 23, 59, 0)
    assert _estado(client)['estado'] == 'ok'
    reloj.ahora = datetime(2026, 11, 4, 6, 0, 0)
    assert _estado(client)['estado'] == 'falta'


def test_el_ensayo_cubre_la_matriz_no_la_maquina(planta, client, reloj):
    assert _ensayar(client, 200, terminal='T2').get_json()['ensayo']['resultado'] == 'OK'
    assert _estado(client, 'T3')['estado'] == 'ok'          # misma matriz A2
    assert _estado(client, 'T1')['estado'] == 'falta'       # matriz A1
    assert _estado(client, 'T4')['estado'] == 'falta'       # sin matriz: nivel máquina


def test_mensual_por_mes_natural(planta, client, reloj):
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE maquinas SET ensayo_frecuencia = 'mensual'"))
    _ensayar(client, 160)
    reloj.ahora = datetime(2026, 11, 30, 18, 0, 0)
    assert _estado(client)['estado'] == 'ok'
    reloj.ahora = datetime(2026, 12, 1, 6, 0, 0)
    d = _estado(client)
    assert d['estado'] == 'falta' and 'mes' in d['motivo']


def test_fuerza_minima_propia_del_terminal_antes_que_la_generica(planta, client, reloj):
    # T2 a 1,5 exige 170 (específica); la genérica es 155.
    r = _ensayar(client, 160, terminal='T2').get_json()['ensayo']
    assert r['resultado'] == 'NOK' and r['fuerza_min_n'] == 170 and r['norma'] == 'Cliente'


def test_justo_el_minimo_es_ok(planta, client, reloj):
    assert _ensayar(client, 155).get_json()['ensayo']['resultado'] == 'OK'


def test_sin_fuerza_minima_no_deja_ensayar(planta, client, reloj):
    r = _ensayar(client, 300, seccion='2.5')
    assert r.status_code == 409
    d = r.get_json()
    assert 'fuerza mínima' in d['motivo'] and d['consejo']
    assert _estado(client)['bloquea'] is True


# ==================== NOK y supervisor ====================

def test_nok_bloquea_hasta_que_decide_el_supervisor(planta, client, reloj):
    nok = _ensayar(client, 100).get_json()['ensayo']
    d = _estado(client)
    assert d['estado'] == 'nok_pendiente' and d['bloquea'] and 'supervisor' in d['consejo']
    # El operario no puede tapar el NOK con otro ensayo
    assert _ensayar(client, 200).status_code == 409

    assert _decidir(client, nok['id'], 'repetir').status_code == 200
    d = _estado(client)
    assert d['estado'] == 'falta' and 'repetir' in d['motivo']
    assert _ensayar(client, 200).get_json()['ensayo']['resultado'] == 'OK'


def test_continuar_exige_motivo_y_vale_solo_ese_dia(planta, client, reloj):
    nok = _ensayar(client, 100).get_json()['ensayo']
    assert _decidir(client, nok['id'], 'continuar').status_code == 400
    assert _decidir(client, nok['id'], 'continuar', 'Probeta mal cortada').status_code == 200
    assert _estado(client)['estado'] == 'continuar'
    assert _estado(client)['bloquea'] is False
    reloj.ahora = datetime(2026, 11, 4, 6, 0, 0)
    assert _estado(client)['estado'] == 'falta'


def test_continuar_en_mensual_tambien_caduca_al_dia_siguiente(planta, client, reloj):
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE maquinas SET ensayo_frecuencia = 'mensual'"))
    nok = _ensayar(client, 100).get_json()['ensayo']
    _decidir(client, nok['id'], 'continuar', 'Lote urgente, revisado a mano')
    reloj.ahora = datetime(2026, 11, 4, 6, 0, 0)
    assert _estado(client)['estado'] == 'falta'


def test_sin_permiso_de_supervisor_no_decide(planta, client, reloj):
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE operarios SET modulos_permitidos = :p WHERE id = 'sup'"),
                     {'p': json.dumps(['engastado'])})
    nok = _ensayar(client, 100).get_json()['ensayo']
    r = _decidir(client, nok['id'], 'repetir')
    assert r.status_code == 403
    assert _estado(client)['estado'] == 'nok_pendiente'


def test_clave_incorrecta_no_decide(planta, client, reloj):
    nok = _ensayar(client, 100).get_json()['ensayo']
    r = client.post(f"/api/ensayos/{nok['id']}/decision",
                    json={'decision': 'repetir', 'usuario': 'sup', 'clave': 'mal'})
    assert r.status_code == 403


def test_un_nok_ya_resuelto_no_se_decide_dos_veces(planta, client, reloj):
    nok = _ensayar(client, 100).get_json()['ensayo']
    _decidir(client, nok['id'], 'repetir')
    assert _decidir(client, nok['id'], 'continuar', 'otra vez').status_code == 409


def _armar_captura_supervisor(nok_id, token='tok-sup'):
    with db.engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO operario_tag_capturas (device_id, operario_id, token, estado, expira_at, tipo, ref)
            VALUES ('lector-p1', '', :t, 'armada', '2099-01-01T00:00:00', 'supervisor_ensayo', :ref)
        """), {'t': token, 'ref': nok_id})


def test_tarjeta_de_supervisor_por_el_lector(planta, client, reloj):
    nok = _ensayar(client, 100).get_json()['ensayo']
    _armar_captura_supervisor(nok['id'])

    orden = client.get('/api/esp32/rfid/operario/captura?device_id=lector-p1').get_json()
    assert orden['captura']['token'] == 'tok-sup'

    # Una tarjeta sin permiso: rechazo con 4xx y la captura sigue armada
    r = client.post('/api/esp32/rfid/operario/captura',
                    json={'device_id': 'lector-p1', 'token': 'tok-sup', 'uid': '11223344'})
    assert r.status_code == 409
    assert client.get('/api/ensayos/supervisor/tarjeta/tok-sup').get_json()['estado'] == 'armada'

    r = client.post('/api/esp32/rfid/operario/captura',
                    json={'device_id': 'lector-p1', 'token': 'tok-sup', 'uid': 'AABBCCDD'})
    assert r.status_code == 200
    est = client.get('/api/ensayos/supervisor/tarjeta/tok-sup').get_json()
    assert est['estado'] == 'asignada' and est['supervisor'] == 'Supervisora'

    r = client.post(f"/api/ensayos/{nok['id']}/decision", json={'decision': 'repetir', 'token': 'tok-sup'})
    assert r.status_code == 200
    assert r.get_json()['decision']['supervisor_via'] == 'tarjeta'
    # La misma lectura no vale para otra decisión
    r = client.post(f"/api/ensayos/{nok['id']}/decision", json={'decision': 'repetir', 'token': 'tok-sup'})
    assert r.status_code == 403
    # Y la tarjeta del supervisor no le ha hecho login como operario
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM operario_logins")).scalar() == 0


def test_admin_registrando_tarjeta_no_hereda_la_captura_de_supervisor(planta, admin_client, reloj):
    nok = _ensayar(admin_client, 100).get_json()['ensayo']
    _armar_captura_supervisor(nok['id'])
    with db.engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO operario_tag_capturas (device_id, operario_id, token, estado, expira_at)
            VALUES ('lector-p1', 'op', 'tok-admin', 'armada', '2099-01-01T00:00:00')
            ON CONFLICT(device_id) DO UPDATE SET operario_id = excluded.operario_id,
                token = excluded.token, tipo = 'registro', ref = NULL
        """))
        tipo = conn.execute(text("SELECT tipo FROM operario_tag_capturas")).scalar()
    assert tipo == 'registro'


# ==================== regulación ====================

def test_regular_invalida_el_ok(planta, client, reloj):
    _ensayar(client, 200)
    reloj.ahora = datetime(2026, 11, 3, 10, 0, 0)
    assert client.post('/api/ensayos/regulacion', json={'maquina_id': 'm1'}).status_code == 200
    d = _estado(client)
    assert d['estado'] == 'falta' and 'regulado' in d['motivo']
    reloj.ahora = datetime(2026, 11, 3, 10, 5, 0)
    _ensayar(client, 200)
    assert _estado(client)['estado'] == 'ok'


def test_regular_no_levanta_un_nok(planta, client, reloj):
    _ensayar(client, 100)
    reloj.ahora = datetime(2026, 11, 3, 10, 0, 0)
    client.post('/api/ensayos/regulacion', json={'maquina_id': 'm1'})
    assert _estado(client)['estado'] == 'nok_pendiente'


# ==================== servidor y auditoría ====================

def test_el_servidor_no_deja_iniciar_sesion_sin_ensayo(planta, client, reloj):
    r = client.get('/api/datos_trabajo_v3?archivo=x.xlsx&terminal=T1&maquina=m1&iniciar_sesion=true')
    assert r.status_code == 409
    d = r.get_json()
    assert d['ensayo_requerido'] is True and d['consejo']


def test_registro_solo_admite_inserciones(planta, client, reloj):
    _ensayar(client, 100)
    with pytest.raises(Exception):
        with db.engine.begin() as conn:
            conn.execute(text("UPDATE ensayos_traccion SET resultado = 'OK'"))
    with pytest.raises(Exception):
        with db.engine.begin() as conn:
            conn.execute(text("DELETE FROM ensayos_traccion"))
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT resultado FROM ensayos_traccion")).scalar() == 'NOK'


def test_el_registro_guarda_copia_de_lo_exigido(planta, client, reloj):
    _ensayar(client, 160)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE ensayos_especificaciones SET fuerza_min_n = 999"))
        conn.execute(text("UPDATE maquinas SET nombre = 'Renombrada'"))
    ev = client.get('/api/ensayos/historial').get_json()['eventos'][0]
    assert ev['fuerza_min_n'] == 155 and ev['maquina_nombre'] == 'AUTO-1'
    assert ev['matriz_nombre'] == 'A1' and ev['operario'] == 'Operario'


# ==================== configuración ====================

def test_historial_filtra_por_bono_y_operario(planta, client, reloj):
    """El report del módulo Calidad cruza cada bono y operario con sus ensayos."""
    client.post('/api/ensayos', json={'maquina_id': 'm1', 'terminal': 'T1', 'seccion': '1,5',
                                      'fuerza_n': 200, 'operario': 'Operario', 'bono': 'B-1'})
    _ensayar(client, 200, terminal='T2')
    por_bono = client.get('/api/ensayos/historial?bono=B-1').get_json()['eventos']
    assert [e['terminal_codigo'] for e in por_bono] == ['T1']
    assert len(client.get('/api/ensayos/historial?operario=Operario').get_json()['eventos']) == 2
    assert client.get('/api/ensayos/historial?operario=Otro').get_json()['eventos'] == []


def test_pagina_calidad_junta_report_y_ensayos(planta, client):
    html = client.get('/calidad').get_data(as_text=True)
    assert 'calidad-report.js' in html and 'ensayos.js' in html
    assert 'panel-rep-bono' in html and 'panel-historial' in html


def test_configuracion_pide_sesion_de_admin(planta, client, admin_client):
    assert client.put('/api/ensayos/maquinas/m1', json={'ensayo_frecuencia': 'mensual'}).status_code == 401
    assert admin_client.put('/api/ensayos/maquinas/m1',
                            json={'ensayo_frecuencia': 'semanal'}).status_code == 400
    assert admin_client.put('/api/ensayos/maquinas/m1',
                            json={'ensayo_frecuencia': 'mensual'}).status_code == 200


def test_matriz_de_otra_maquina_no_se_asigna(planta, admin_client):
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO maquinas (id, puesto_id, nombre) VALUES ('m2', 'p1', 'B')"))
        conn.execute(text("INSERT INTO matrices (id, maquina_id, nombre) VALUES ('b1', 'm2', 'B1')"))
    r = admin_client.put('/api/ensayos/terminal-matriz',
                         json={'maquina_id': 'm1', 'terminal': 'T1', 'matriz_id': 'b1'})
    assert r.status_code == 400


def test_importar_fuerzas_desde_excel(planta, admin_client):
    df = pd.DataFrame({'Terminal': ['T9', None], 'Sección': ['0,5', '2.5'],
                       'Fuerza mínima (N)': ['60', '230'], 'Norma': ['Cliente', 'IEC']})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    r = admin_client.post('/api/ensayos/especificaciones/importar',
                          data={'archivo': (buf, 'fuerzas.xlsx')}, content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['importadas'] == 2
    with db.engine.connect() as conn:
        assert ensayos.especificacion(conn, 'T9', '0.5')['fuerza_min_n'] == 60
        assert ensayos.especificacion(conn, 'OTRO', '2,5')['fuerza_min_n'] == 230


@pytest.mark.parametrize('crudo,limpio', [
    ('1,5', '1.5'), ('1.50', '1.5'), (1.5, '1.5'), ('2', '2'), ('0.35 mm2', '0.35'), ('', ''), (None, ''),
])
def test_normalizar_seccion(crudo, limpio):
    assert ensayos.normalizar_seccion(crudo) == limpio
