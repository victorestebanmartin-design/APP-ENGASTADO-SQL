"""El bono se monta con la orden elegida (por id), no con todas las que
compartan su número."""
import sqlite3


def _sql(app, sentencia, *p):
    with sqlite3.connect(app.config['DB_PATH']) as c:
        return c.execute(sentencia, p).fetchall()


def _orden(app, oid, numero, estado='pendiente', corte='CC1'):
    _sql(app, "INSERT INTO ordenes_produccion (id, codigo_corte, numero, estado, archivo_excel) "
              "VALUES (?,?,?,?,'a.xlsx')", oid, corte, numero, estado)


def _estado(app, oid):
    return _sql(app, "SELECT estado, bono_id IS NOT NULL, carro_numero FROM ordenes_produccion WHERE id = ?", oid)[0]


def test_crear_bono_por_id_no_arrastra_a_la_del_mismo_numero(app, client):
    _orden(app, 'vieja', '60000001', estado='completado')
    _orden(app, 'nueva', '60000001')
    r = client.post('/api/bonos', json={'nombre': 'B1', 'ordenes_ids': ['nueva']})
    assert r.status_code == 200, r.get_json()
    assert _estado(app, 'nueva')[:2] == ('en_bono', 1)
    assert _estado(app, 'vieja')[:2] == ('completado', 0)


def test_crear_bono_por_numero_coge_la_unica_abierta(app, client):
    """Por número (compatibilidad) vale mientras señale a una sola orden abierta."""
    _orden(app, 'vieja', '60000001', estado='completado')
    _orden(app, 'nueva', '60000001')
    assert client.post('/api/bonos', json={'nombre': 'B1', 'ordenes_ids': ['60000001']}).status_code == 200
    assert _estado(app, 'nueva')[:2] == ('en_bono', 1)
    assert _estado(app, 'vieja')[:2] == ('completado', 0)


def test_crear_bono_por_numero_ambiguo_se_rechaza_entero(app, client):
    _orden(app, 'una', '60000001')
    _orden(app, 'otra', '60000001', corte='CC2')
    r = client.post('/api/bonos', json={'nombre': 'B1', 'ordenes_ids': ['60000001']})
    assert r.status_code == 409
    assert '60000001' in r.get_json()['message']
    assert _sql(app, "SELECT COUNT(*) FROM bonos") == [(0,)]
    assert _estado(app, 'una')[:2] == ('pendiente', 0)


def test_crear_bono_con_orden_que_no_existe(app, client):
    r = client.post('/api/bonos', json={'nombre': 'B1', 'ordenes_ids': ['no-existe']})
    assert r.status_code == 404
    assert _sql(app, "SELECT COUNT(*) FROM bonos") == [(0,)]


def _carro_con_proyecto(app, carro, nombre, orden_id=None):
    _sql(app, "INSERT OR IGNORE INTO carros (numero) VALUES (?)", carro)
    _sql(app, "INSERT INTO proyectos (nombre, archivo, carro_asignado, orden_id) VALUES (?, 'a.xlsx', ?, ?)",
         nombre, carro, orden_id)


def test_generar_desde_carros_usa_la_orden_del_proyecto(app, client):
    _orden(app, 'vieja', '60000001', estado='completado')
    _orden(app, 'nueva', '60000001', estado='en_proceso')
    _carro_con_proyecto(app, 3, '60000001 - CC1', orden_id='nueva')

    r = client.post('/api/bonos/generar', json={'nombre': 'B_GEN', 'carros': [3]})

    assert r.status_code == 200, r.get_json()
    assert _estado(app, 'nueva') == ('en_bono', 1, 3)
    assert _estado(app, 'vieja')[:2] == ('completado', 0)


def test_generar_con_proyecto_antiguo_sin_orden_id(app, client):
    """Proyecto de antes de guardar orden_id: se busca por el número del nombre,
    y solo vale la orden abierta."""
    _orden(app, 'vieja', '60000002', estado='completado')
    _orden(app, 'abierta', '60000002', estado='en_proceso')
    _carro_con_proyecto(app, 4, '60000002 - CC1')

    assert client.post('/api/bonos/generar', json={'nombre': 'B_ANT', 'carros': [4]}).status_code == 200
    assert _estado(app, 'abierta') == ('en_bono', 1, 4)
    assert _estado(app, 'vieja')[:2] == ('completado', 0)


def test_generar_con_proyecto_antiguo_y_numero_ambiguo(app, client):
    _orden(app, 'una', '60000003', estado='en_proceso')
    _orden(app, 'otra', '60000003', estado='en_proceso', corte='CC2')
    _carro_con_proyecto(app, 5, '60000003 - CC1')

    r = client.post('/api/bonos/generar', json={'nombre': 'B_AMB', 'carros': [5]})

    assert r.status_code == 409 and '60000003' in r.get_json()['message']
    assert _sql(app, "SELECT COUNT(*) FROM bonos") == [(0,)]
    assert _sql(app, "SELECT carro_asignado FROM proyectos") == [(5,)]


def test_generar_con_carro_cargado_a_mano_sin_orden(app, client):
    _carro_con_proyecto(app, 6, 'Proyecto suelto')
    r = client.post('/api/bonos/generar', json={'nombre': 'B_MANO', 'carros': [6]})
    assert r.status_code == 200, r.get_json()
    assert _sql(app, "SELECT bono_id IS NOT NULL, estado FROM carros WHERE numero = 6") == [(1, 'en_proceso')]
