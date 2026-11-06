"""La hoja report de engastado: qué terminales salen y cómo sale el operario."""
import pandas as pd
import pytest
from sqlalchemy import text

from app.routes.base import db


def _sql(app, sentencia, **p):
    with app.app_context():
        db.session.execute(text(sentencia), p)
        db.session.commit()


@pytest.fixture
def bono(app):
    """Bono B1, carro 1, con un terminal normal, un pelado y uno desactivado."""
    df = pd.DataFrame(
        [['C1', '1', 'X1', 'T_OK', 'X2', 'KN-PELAR-6MM'],
         ['C2', '1', 'X3', 'T_OFF', 'X4', 'T_OK']],
        columns=['Cod. cable', 'Sección', 'De Elemento', 'De Terminal', 'Para Elemento', 'Para Terminal'])
    df.to_excel(f"{app.config['UPLOAD_FOLDER']}/corte.xlsx", index=False)
    _sql(app, "INSERT INTO bonos (id, nombre) VALUES ('b1', 'B1')")
    _sql(app, "INSERT INTO ordenes_produccion (id, codigo_corte, bono_id, numero, archivo_excel) "
              "VALUES ('o1', 'C1', 'b1', 'P1', 'corte.xlsx')")
    _sql(app, "INSERT INTO terminales_ignorados (terminal_codigo) VALUES ('T_OFF')")


def _report(client):
    return client.get('/report/bono/B1/carros').get_data(as_text=True)


def test_no_salen_pelados_ni_desactivados(bono, client):
    html = _report(client)
    assert 'T_OK' in html
    assert 'KN-PELAR-6MM' not in html
    assert 'T_OFF' not in html
    assert '0 de 1 engastados' in html


def test_desactivado_despues_de_engastarlo_sigue_saliendo(bono, client):
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T_OFF', 'carro': 1, 'operario': 'Ana'})
    assert 'T_OFF' in _report(client)


def test_operario_sale_con_su_numero(bono, client):
    assert client.post('/api/operarios', json={'nombre': 'Ana', 'numero_empleado': ' e-12 '}).status_code == 200
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T_OK', 'carro': 1, 'operario': 'Ana'})
    assert 'Ana · E-12' in _report(client)


def test_operario_sin_numero_sale_solo_con_nombre(bono, client):
    client.post('/api/operarios', json={'nombre': 'Ana'})
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T_OK', 'carro': 1, 'operario': 'Ana'})
    html = _report(client)
    assert 'Ana' in html and 'Ana ·' not in html


def test_el_registro_guarda_copia_del_numero(bono, client):
    r = client.post('/api/operarios', json={'nombre': 'Ana', 'numero_empleado': '12'})
    op_id = r.get_json()['operario']['id']
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T_OK', 'carro': 1, 'operario': 'Ana'})
    client.put(f'/api/operarios/{op_id}', json={'numero_empleado': '99'})
    assert 'Ana · 12' in _report(client)


def test_registro_antiguo_coge_el_numero_de_la_ficha(bono, client):
    """Lo engastado antes de dar de alta los números también sale con él."""
    r = client.post('/api/operarios', json={'nombre': 'Ana'})
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T_OK', 'carro': 1, 'operario': 'Ana'})
    client.put(f"/api/operarios/{r.get_json()['operario']['id']}", json={'numero_empleado': '12'})
    assert 'Ana · 12' in _report(client)


def test_nombre_repetido_no_se_inventa_el_numero(bono, client):
    client.post('/api/operarios', json={'nombre': 'Ana', 'numero_empleado': '12'})
    client.post('/api/operarios', json={'nombre': 'Ana', 'numero_empleado': '13'})
    client.post('/api/bonos/B1/progreso', json={'terminal': 'T_OK', 'carro': 1, 'operario': 'Ana'})
    html = _report(client)
    assert 'Ana · 12' not in html and 'Ana · 13' not in html


def test_numero_de_empleado_no_se_repite(client):
    client.post('/api/operarios', json={'nombre': 'Ana', 'numero_empleado': '12'})
    r = client.post('/api/operarios', json={'nombre': 'Luis', 'numero_empleado': '12'})
    assert r.status_code == 409 and 'Ana' in r.get_json()['error']

    otro = client.post('/api/operarios', json={'nombre': 'Luis'}).get_json()['operario']['id']
    r = client.put(f'/api/operarios/{otro}', json={'numero_empleado': '12'})
    assert r.status_code == 409 and 'Ana' in r.get_json()['error']


def test_numero_de_empleado_se_puede_quitar_y_valida_formato(client):
    r = client.post('/api/operarios', json={'nombre': 'Ana', 'numero_empleado': '12'})
    op_id = r.get_json()['operario']['id']

    assert client.put(f'/api/operarios/{op_id}', json={'numero_empleado': '<b>'}).status_code == 400
    assert client.put(f'/api/operarios/{op_id}', json={'numero_empleado': ''}).get_json()['success']

    ops = client.get('/api/operarios').get_json()['operarios']
    assert ops[0]['nombre'] == 'Ana' and ops[0]['numero_empleado'] is None
