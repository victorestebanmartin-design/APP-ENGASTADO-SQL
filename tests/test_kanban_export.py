"""Exportar/importar los datos del kanban de un servidor a otro.

El stock y la gaveta de cada terminal se teclean a mano y solo viven en la BD,
que no va al repositorio. Cuando la app corre en PythonAnywhere y en el PC de
planta, ese trabajo tiene que poder viajar de uno a otro sin tocar consolas.
"""
import io
import json


def _fichero(datos):
    """Empaqueta un dict como el .json que sube el navegador."""
    contenido = json.dumps(datos, ensure_ascii=False).encode('utf-8')
    return {'fichero': (io.BytesIO(contenido), 'kanban_stock.json')}


def _sembrar(admin_client):
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'F1-G3'})
    admin_client.put('/api/terminal-stock/640204',
                     json={'stock_actual': 4000, 'stock_minimo': 1500, 'notas': 'AMP roja'})
    admin_client.put('/api/terminal-stock/640205',
                     json={'stock_actual': 400, 'stock_minimo': 200})


# ── Exportación ───────────────────────────────────────────────────────────────

def test_export_devuelve_gavetas_y_stock(admin_client):
    _sembrar(admin_client)

    r = admin_client.get('/api/kanban-terminales/export-datos')
    assert r.status_code == 200
    assert 'attachment' in r.headers['Content-Disposition']
    assert 'kanban_stock_' in r.headers['Content-Disposition']

    datos = json.loads(r.data.decode('utf-8'))
    # El numero de version sube cuando el formato gana campos (v2: el LED de
    # cada gaveta), asi que se compara con la constante, no con un literal.
    from app.routes.puestos import KANBAN_DATOS_VERSION
    assert datos['version'] == KANBAN_DATOS_VERSION
    assert datos['gavetas'] == [{'terminal_codigo': '640204', 'gaveta': 'F1-G3', 'led': None}]

    por_codigo = {s['terminal_codigo']: s for s in datos['stock']}
    assert por_codigo['640204']['stock_actual'] == 4000
    assert por_codigo['640204']['stock_minimo'] == 1500
    assert por_codigo['640204']['notas'] == 'AMP roja'
    assert por_codigo['640205']['stock_actual'] == 400


def test_export_con_la_base_vacia_no_falla(admin_client):
    r = admin_client.get('/api/kanban-terminales/export-datos')
    assert r.status_code == 200
    datos = json.loads(r.data.decode('utf-8'))
    assert datos['gavetas'] == [] and datos['stock'] == []


# ── Ida y vuelta ──────────────────────────────────────────────────────────────

def test_ida_y_vuelta_recupera_los_datos(admin_client):
    """Lo exportado en un servidor, importado en otro, da lo mismo."""
    _sembrar(admin_client)
    original = json.loads(
        admin_client.get('/api/kanban-terminales/export-datos').data.decode('utf-8'))

    # Simula el servidor de destino, que arranca con el kanban en blanco
    admin_client.delete('/api/terminal-gaveta/640204')
    admin_client.put('/api/terminal-stock/640204', json={'stock_actual': 0, 'stock_minimo': 0})
    admin_client.put('/api/terminal-stock/640205', json={'stock_actual': 0, 'stock_minimo': 0})

    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data=_fichero(original), content_type='multipart/form-data')
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo['success'] and cuerpo['gavetas'] == 1 and cuerpo['stock'] == 2

    vuelta = json.loads(
        admin_client.get('/api/kanban-terminales/export-datos').data.decode('utf-8'))
    assert vuelta['gavetas'] == original['gavetas']
    assert vuelta['stock'] == original['stock']


def test_import_sobrescribe_lo_que_trae_y_respeta_lo_demas(admin_client):
    _sembrar(admin_client)
    # Un terminal que solo existe en el servidor de destino
    admin_client.put('/api/terminal-stock/999999', json={'stock_actual': 77, 'stock_minimo': 7})

    datos = {
        'version': 1,
        'gavetas': [{'terminal_codigo': '640204', 'gaveta': 'A2-G1'}],
        'stock':   [{'terminal_codigo': '640204', 'stock_actual': 123,
                     'stock_minimo': 45, 'notas': None}],
    }
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data=_fichero(datos), content_type='multipart/form-data')
    assert r.status_code == 200

    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['gaveta'] == 'A2-G1'
    final = json.loads(
        admin_client.get('/api/kanban-terminales/export-datos').data.decode('utf-8'))
    por_codigo = {s['terminal_codigo']: s for s in final['stock']}
    assert por_codigo['640204']['stock_actual'] == 123
    assert por_codigo['999999']['stock_actual'] == 77   # intacto: no se borra nada


def test_import_acepta_acentos_y_flechas(admin_client):
    """Las notas viajan en UTF-8 aunque el servidor sea Windows (ver CLAUDE.md)."""
    datos = {
        'version': 1,
        'gavetas': [{'terminal_codigo': 'T1', 'gaveta': 'Estantería → 3'}],
        'stock':   [{'terminal_codigo': 'T1', 'stock_actual': 1,
                     'stock_minimo': 0, 'notas': 'Pedir en la próxima revisión →'}],
    }
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data=_fichero(datos), content_type='multipart/form-data')
    assert r.status_code == 200

    vuelta = json.loads(
        admin_client.get('/api/kanban-terminales/export-datos').data.decode('utf-8'))
    assert vuelta['gavetas'][0]['gaveta'] == 'Estantería → 3'
    assert vuelta['stock'][0]['notas'] == 'Pedir en la próxima revisión →'


# ── Ficheros equivocados: el motivo se dice, no se esconde en un 500 ──────────

def test_import_sin_fichero(admin_client):
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data={}, content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'fichero' in r.get_json()['message'].lower()


def test_import_json_invalido(admin_client):
    data = {'fichero': (io.BytesIO(b'esto no es json'), 'cualquiera.json')}
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data=data, content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'JSON' in r.get_json()['message']


def test_import_json_de_otra_cosa(admin_client):
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data=_fichero({'puestos': [], 'maquinas': []}),
                          content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'kanban' in r.get_json()['message'].lower()


def test_import_de_version_futura(admin_client):
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data=_fichero({'version': 99, 'gavetas': [], 'stock': []}),
                          content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'ACTUALIZAR.bat' in r.get_json()['message']


def test_filas_basura_se_saltan_sin_tumbar_la_importacion(admin_client):
    datos = {
        'version': 1,
        'gavetas': [{'terminal_codigo': '', 'gaveta': 'X'},          # sin código
                    {'terminal_codigo': 'T2', 'gaveta': ''},          # sin gaveta
                    {'terminal_codigo': 'T3', 'gaveta': 'B1'}],
        'stock':   ['no soy un dict',
                    {'terminal_codigo': 'T4', 'stock_actual': 'muchos'},
                    {'terminal_codigo': 'T5', 'stock_actual': 10, 'stock_minimo': 2}],
    }
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data=_fichero(datos), content_type='multipart/form-data')
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo['gavetas'] == 1 and cuerpo['stock'] == 1


# ── Permisos ─────────────────────────────────────────────────────────────────

def test_export_e_import_requieren_pin(client):
    assert client.get('/api/kanban-terminales/export-datos').status_code == 401
    assert client.post('/api/kanban-terminales/import-datos',
                       data=_fichero({'version': 1, 'gavetas': [], 'stock': []}),
                       content_type='multipart/form-data').status_code == 401
