"""El número de carro no tiene tope; lo limitado son los 6 carros por bono."""
import json
import os
import sqlite3

import pytest

from app import _apply_migrations

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def operario(client, app):
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        conn.execute("INSERT INTO operarios (id, nombre, modulos_permitidos) "
                     "VALUES ('op-b', 'Bea', ?)", (json.dumps(['bonos']),))
        conn.execute("INSERT INTO operario_logins (id, operario_nombre, timestamp_login, ultimo_latido, activo, modulo) "
                     "VALUES ('login-b', 'Bea', datetime('now'), datetime('now'), 1, 'mangueras')")
        for i in range(1, 8):
            conn.execute("INSERT INTO ordenes_produccion (id, codigo_corte, numero, cantidad, archivo_excel) "
                         "VALUES (?, 'H1', ?, 1, 'corte.xlsx')", (f'o{i}', f'600{i}'))
            for tabla in ('mangueras_preparaciones', 'manguitos_colocaciones'):
                conn.execute(f"INSERT INTO {tabla} (orden_id, inicio, fin) VALUES (?, 'a', 'b')", (f'o{i}',))
    with client.session_transaction() as sesion:
        sesion['operario_actual'] = 'Bea'
        sesion['operario_login_id'] = 'login-b'
    return client


def _crear(client, pares):
    return client.post('/api/bonos/asistente/crear',
                       json={'carros': [{'carro': c, 'orden_id': o} for c, o in pares]})


def test_bono_con_carros_7_y_10_los_da_de_alta(operario, app):
    r = _crear(operario, [(7, 'o1'), (10, 'o2')])
    assert r.status_code == 200, r.get_json()
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT numero, estado FROM carros WHERE numero > 6 ORDER BY numero').fetchall() \
            == [(7, 'en_proceso'), (10, 'en_proceso')]
        assert conn.execute("SELECT carro_numero FROM ordenes_produccion WHERE id = 'o2'").fetchone() == (10,)
    # Ocupado desde ahora, como cualquier otro carro.
    assert _crear(operario, [(7, 'o3')]).status_code == 409


def test_bono_sigue_limitado_a_seis_carros(operario):
    pares = [(100 + i, f'o{i}') for i in range(1, 8)]
    assert _crear(operario, pares).status_code == 400
    assert _crear(operario, pares[:6]).status_code == 200


def test_bono_rechazado_no_deja_carro_dado_de_alta(operario, app):
    assert _crear(operario, [(50, 'no-existe')]).status_code == 409
    with sqlite3.connect(app.config['DB_PATH']) as conn:
        assert conn.execute('SELECT 1 FROM carros WHERE numero = 50').fetchone() is None


def test_anadir_carro_y_asignarle_orden(client):
    assert client.post('/api/carros', json={'numero': 12}).status_code == 200
    assert client.post('/api/carros', json={'numero': 12}).status_code == 409
    assert 12 in [c['numero'] for c in client.get('/api/carros').get_json()['carros']]
    r = client.post('/api/carros/asignar-orden',
                    json={'numero_carro': 12, 'proyecto_nombre': 'P', 'archivo': 'a.xlsx'})
    assert r.status_code == 200, r.get_json()


@pytest.mark.parametrize('numero', [0, -1, 10_000_000, '7', 1.5, None])
def test_anadir_carro_rechaza_numero_no_valido(client, numero):
    assert client.post('/api/carros', json={'numero': numero}).status_code == 400


def test_generar_desde_gestion_acepta_numeros_altos(client):
    client.post('/api/carros', json={'numero': 9})
    r = client.post('/api/bonos/generar', json={'nombre': 'B', 'carros': [9]})
    # Sin proyecto en el carro: lo que falla es el contenido, no el número.
    assert r.status_code == 409
    assert client.post('/api/bonos/generar', json={'nombre': 'B', 'carros': list(range(1, 8))}).status_code == 400


def _bd_antigua(ruta):
    """BD como las desplegadas: con el CHECK, un carro en bono y una orden en él."""
    with open(os.path.join(RAIZ, 'schema_sqlite.sql'), encoding='utf-8') as f:
        esquema = f.read()
    actual = 'numero INTEGER PRIMARY KEY,'
    assert actual in esquema
    conn = sqlite3.connect(ruta)
    conn.executescript(esquema.replace(actual, 'numero INTEGER PRIMARY KEY CHECK (numero BETWEEN 1 AND 6),'))
    conn.execute("INSERT INTO bonos (id, nombre) VALUES ('b1', 'B1')")
    conn.execute("INSERT INTO carros (numero, bono_id, estado) VALUES (3, 'b1', 'en_proceso')")
    conn.execute("INSERT INTO ordenes_produccion (id, codigo_corte, numero, bono_id, carro_numero) "
                 "VALUES ('o1', 'H1', '600', 'b1', 3)")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute('INSERT INTO carros (numero) VALUES (7)')
    conn.close()


def test_migracion_quita_el_tope_sin_perder_nada(tmp_path):
    ruta = str(tmp_path / 'antigua.db')
    _bd_antigua(ruta)

    _apply_migrations(ruta)
    _apply_migrations(ruta)  # en cada arranque: la segunda vez no hace nada

    conn = sqlite3.connect(ruta)
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('INSERT INTO carros (numero) VALUES (7)')
    assert conn.execute('SELECT bono_id, estado FROM carros WHERE numero = 3').fetchone() == ('b1', 'en_proceso')
    assert conn.execute("SELECT carro_numero FROM ordenes_produccion WHERE id = 'o1'").fetchone() == (3,)
    objetos = {r[0] for r in conn.execute('SELECT name FROM sqlite_master')}
    assert {'idx_carros_bono', 'idx_carros_estado', 'trg_carros_updated_at', 'vw_bonos_con_carros'} <= objetos
    assert 'carros_nueva' not in objetos
    assert conn.execute("SELECT total_carros FROM vw_bonos_con_carros WHERE bono_id = 'b1'").fetchone() == (1,)
    # La orden sigue atada a la tabla de carros nueva.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE ordenes_produccion SET carro_numero = 999 WHERE id = 'o1'")
    conn.close()
