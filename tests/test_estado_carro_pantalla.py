"""El carro colorea su numero segun el estado que anuncia /api/esp32/current:
libre (verde), asignado sin empezar (naranja) y engastando (rojo)."""
import json
import os

from sqlalchemy import text


def _estado(client, carro):
    d = client.get(f'/api/esp32/current?carro={carro}').get_json()
    return d['carro_estado'], d['carro_bono']


def _asignar(app, numero, bono_id='b1', nombre='0000001_2026'):
    from app.routes.base import db
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO bonos (id, nombre, estado) VALUES (:i, :n, 'activo')"),
                {'i': bono_id, 'n': nombre})
            conn.execute(text(
                "UPDATE carros SET bono_id = :b, estado = 'en_proceso' WHERE numero = :n"),
                {'b': bono_id, 'n': numero})


def test_carro_sin_bono_es_libre(client):
    assert _estado(client, 1) == ('libre', '')


def test_carro_con_bono_sin_empezar_es_asignado(app, client):
    _asignar(app, 2)
    assert _estado(client, 2) == ('asignado', '0000001_2026')


def test_carro_con_trabajo_hecho_es_engastando(app, client):
    _asignar(app, 3)
    ruta = os.path.join(app.config['DATA_DIR'], 'progreso_bono_0000001_2026.json')
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'T1': {'estado': 'en_proceso', 'carros_completados': [],
                          'carros_con_pendientes': {'3': {'paquetes': []}}}}, f)
    assert _estado(client, 3) == ('engastando', '0000001_2026')


def test_carro_desconocido_no_tumba_la_respuesta(client):
    assert _estado(client, 'X') == ('', '')


def test_composicion_del_bono_lista_ordenes_y_carros(app, client):
    from app.routes.base import db
    _asignar(app, 4, bono_id='b9', nombre='0000009_2026')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO ordenes_produccion (id, codigo_corte, numero, proyecto, estado, bono_id, carro_numero) "
                "VALUES ('o1', 'H0564725', '60261311', 'PC_HRI_ZEFIRO_ED07', 'en_bono', 'b9', 4)"))
    info = client.get('/api/esp32/current?carro=4').get_json()['carro_bono_info']
    assert info['nombre'] == '0000009_2026'
    assert info['ordenes'] == [{'c': 4, 'o': '60261311', 'k': 'PC_HRI_ZEFIRO_ED07'}]


def test_carro_libre_no_manda_composicion(client):
    assert client.get('/api/esp32/current?carro=1').get_json()['carro_bono_info'] is None
