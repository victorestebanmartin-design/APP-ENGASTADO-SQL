"""Fallos encontrados en la revisión de fiabilidad (1.31.1): cada test es uno
que en planta no daba error, daba datos perdidos o un servidor lento."""
import json
import os
from datetime import datetime, timedelta

from sqlalchemy import text


def _sql(app, sentencia, **p):
    from app.routes.base import db
    with app.app_context():
        with db.engine.begin() as conn:
            r = conn.execute(text(sentencia), p)
            return r.fetchall() if r.returns_rows else None


def _orden(client, numero):
    r = client.post('/api/ordenes', json={'codigo_corte': 'CC', 'numero': numero})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['orden']['id']


# ── Listado de bonos ────────────────────────────────────────────────────────

def test_listar_bonos_no_recalcula_los_cerrados(app, client, monkeypatch):
    """Visualización sondea el listado cada 5 s: recorrer los Excel de todo el
    histórico lo dejaba en decenas de segundos."""
    _sql(app, "INSERT INTO bonos (id, nombre, estado) VALUES ('b1','CERRADO','completado'),"
              "('b2','VIVO','activo'),('b3','PARADO','pausado')")
    from app.routes import progreso
    calculados = []
    monkeypatch.setattr(progreso, '_bono_finalizado',
                        lambda nombre, terminales=None: calculados.append(nombre) or False)

    bonos = {b['nombre']: b for b in client.get('/api/bonos').get_json()['bonos']}

    assert calculados == ['VIVO']
    assert bonos['CERRADO']['finalizado'] is True
    assert bonos['PARADO']['finalizado'] is False


# ── Sesiones de bloqueo ─────────────────────────────────────────────────────

def _sesion(app, maquina='M1', **campos):
    from app.routes.base import db
    from repositories.sesion_trabajo_repository import SesionTrabajoRepository
    with app.app_context():
        repo = SesionTrabajoRepository(db)
        sid = repo.crear_sesion(maquina, 'T1', 'a.xlsx', '1',
                                [{'cod_cable': 'C1', 'elemento': 'E1'}], orden_id='O1')
    for campo, valor in campos.items():
        _sql(app, f"UPDATE sesiones_trabajo SET {campo} = :v WHERE id = :id", v=valor, id=sid)
    return sid


def _bloqueados(app):
    from app.routes.base import db
    from repositories.sesion_trabajo_repository import SesionTrabajoRepository
    with app.app_context():
        repo = SesionTrabajoRepository(db)
        repo.caducar_sesiones(forzar=True)
        return repo.verificar_bloqueos([{'cod_cable': 'C1', 'elemento': 'E1'}], orden_id='O1')


def test_liberar_sesion_acepta_el_beacon_en_texto_plano(app, client):
    """Al cerrar la pestaña el aviso llegaba como text/plain y daba 500: los
    paquetes se quedaban bloqueados."""
    sid = _sesion(app)
    r = client.post('/api/sesion/liberar', data=json.dumps({'sesion_id': sid}),
                    content_type='text/plain;charset=UTF-8')
    assert r.status_code == 200
    assert _sql(app, "SELECT activo FROM sesiones_trabajo WHERE id = :id", id=sid) == [(0,)]


def test_el_js_manda_el_beacon_como_json():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, 'static', 'js', 'v3', 'v3-estado.js'), encoding='utf-8') as f:
        js = f.read()
    trozo = js[js.index("sendBeacon('/api/sesion/liberar'"):][:200]
    assert "type: 'application/json'" in trozo


def test_sesion_que_deja_de_latir_ya_no_bloquea(app, client):
    hace_rato = (datetime.now() - timedelta(minutes=30)).isoformat()
    sid = _sesion(app, ultimo_latido=hace_rato)
    assert _bloqueados(app) == {}
    assert client.post('/api/sesion/latido', json={'sesion_id': sid}).get_json()['activa'] is False


def test_sesion_que_late_sigue_bloqueando(app, client):
    ayer = (datetime.now() - timedelta(hours=20)).isoformat()
    sid = _sesion(app, timestamp_inicio=ayer)
    r = client.post('/api/sesion/latido', json={'sesion_id': sid})
    assert r.get_json() == {'success': True, 'activa': True}
    assert list(_bloqueados(app)) == [('C1', 'E1')]


def test_sesion_sin_ningun_latido_aguanta_un_turno(app):
    """Una página abierta desde antes de la actualización no late: no se le
    quita el bloqueo a los 10 minutos, solo cuando es claramente un fantasma."""
    _sesion(app, timestamp_inicio=(datetime.now() - timedelta(hours=2)).isoformat())
    assert list(_bloqueados(app)) == [('C1', 'E1')]
    _sesion(app, timestamp_inicio=(datetime.now() - timedelta(hours=13)).isoformat())
    assert _bloqueados(app) == {}


# ── Progreso ────────────────────────────────────────────────────────────────

def test_guardar_progreso_reintenta_si_el_fichero_esta_abierto(tmp_path, monkeypatch):
    """En Windows os.replace falla si otro hilo tiene abierto el destino."""
    from app.routes import progreso
    real = os.replace
    fallos = [3]

    def replace_ocupado(origen, destino):
        if fallos[0]:
            fallos[0] -= 1
            raise PermissionError(13, 'El proceso no tiene acceso al archivo')
        return real(origen, destino)

    monkeypatch.setattr(progreso.os, 'replace', replace_ocupado)
    monkeypatch.setattr(progreso.time, 'sleep', lambda s: None)
    ruta = str(tmp_path / 'progreso_bono_X.json')
    progreso._escribir_progreso_atomico(ruta, {'T1': {'estado': 'en_proceso'}})

    with open(ruta, encoding='utf-8') as f:
        assert json.load(f) == {'T1': {'estado': 'en_proceso'}}
    assert [n for n in os.listdir(tmp_path) if n.endswith('.tmp')] == []


def test_progreso_de_bono_antiguo_con_barra(app, client):
    _sql(app, "INSERT INTO bonos (id, nombre, estado) VALUES ('bz','ZEFIRO 26/10','activo')")
    r = client.post('/api/bonos/ZEFIRO%2026%2F10/progreso', json={'terminal': 'T1', 'carro': 1})
    assert r.status_code == 200 and r.get_json()['success']
    r = client.get('/api/bonos/ZEFIRO%2026%2F10/progreso')
    assert r.get_json()['progreso']['T1']['carros_completados'] == [1]
    # y la ficha del bono sigue saliendo por su ruta de siempre
    assert client.get('/api/bonos/ZEFIRO%2026%2F10').get_json()['bono']['nombre'] == 'ZEFIRO 26/10'


def test_el_js_no_da_por_guardado_lo_que_no_confirma_el_servidor():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    v3 = os.path.join(raiz, 'static', 'js', 'v3')
    for nombre in os.listdir(v3):
        with open(os.path.join(v3, nombre), encoding='utf-8') as f:
            js = f.read()
        # Todo guardado de progreso pasa por guardarProgresoBono, que mira la respuesta
        assert '/progreso/parcial`' not in js and '/progreso/estado`' not in js, nombre


# ── Borrar bonos / órdenes repetidas ────────────────────────────────────────

def test_borrar_bono_completado_no_resucita_sus_ordenes(app, client):
    hecha, a_medias = _orden(client, 'ORD_HECHA'), _orden(client, 'ORD_MEDIAS')
    client.post('/api/bonos', json={'nombre': 'B_VIEJO', 'ordenes_ids': ['ORD_HECHA', 'ORD_MEDIAS']})
    _sql(app, "UPDATE ordenes_produccion SET estado='completado', carro_numero=1 WHERE id=:i", i=hecha)
    ruta = os.path.join(app.config['DATA_DIR'], 'progreso_bono_B_VIEJO.json')
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'T1': {'estado': 'completado', 'carros_completados': [1]}}, f)

    assert client.delete('/api/bonos/B_VIEJO').get_json()['success']

    estados = dict(_sql(app, "SELECT id, estado FROM ordenes_produccion"))
    assert estados == {hecha: 'completado', a_medias: 'pendiente'}
    assert _sql(app, "SELECT COUNT(*) FROM ordenes_produccion WHERE bono_id IS NOT NULL") == [(0,)]
    # El progreso (la trazabilidad) se aparta: ni se pierde ni lo hereda otro bono
    assert not os.path.exists(ruta)
    apartados = os.listdir(os.path.join(app.config['DATA_DIR'], 'progreso_bonos_borrados'))
    assert len(apartados) == 1 and apartados[0].endswith('progreso_bono_B_VIEJO.json')


def test_no_se_crean_dos_ordenes_con_el_mismo_numero(client):
    _orden(client, '60000001')
    r = client.post('/api/ordenes', json={'codigo_corte': 'CC', 'numero': ' 60000001 '})
    assert r.status_code == 409
    assert '60000001' in r.get_json()['message']
    assert client.post('/api/ordenes', json={'codigo_corte': 'CC', 'numero': '  '}).status_code == 400


# ── Copia automática ────────────────────────────────────────────────────────

def test_backup_automatico_lleva_progreso_y_excel(app):
    from app.backup_auto import _una_copia
    data = app.config['DATA_DIR']
    with open(os.path.join(data, 'progreso_bono_B1.json'), 'w', encoding='utf-8') as f:
        f.write('{"T1": {}}')
    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'corte.xlsx'), 'wb') as f:
        f.write(b'excel')

    base = _una_copia(data, app.logger)

    copia = os.path.join(base, os.listdir(base)[0])
    assert os.path.isfile(os.path.join(copia, 'progreso_bono_B1.json'))
    assert os.path.isfile(os.path.join(copia, 'cortes', 'corte.xlsx'))
