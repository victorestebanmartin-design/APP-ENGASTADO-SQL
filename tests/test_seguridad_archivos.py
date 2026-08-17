"""Tests de path traversal: ningún nombre de archivo puede salirse de data/cortes."""
import os

from app.excel_manager import ExcelManager


def test_delete_file_rechaza_traversal(admin_client, app, tmp_path):
    victima = tmp_path / 'victima.txt'
    victima.write_text('no me borres')

    r = admin_client.post('/api/delete_file', json={'filename': '../victima.txt'})
    assert r.status_code == 400
    assert victima.exists()


def test_delete_file_legitimo_funciona(admin_client, app):
    upload = app.config['UPLOAD_FOLDER']
    ruta = os.path.join(upload, 'borrar.xlsx')
    with open(ruta, 'w') as f:
        f.write('x')

    r = admin_client.post('/api/delete_file', json={'filename': 'borrar.xlsx'})
    assert r.status_code == 200
    assert r.get_json()['success']
    assert not os.path.exists(ruta)


def test_add_corte_rechaza_traversal(admin_client):
    r = admin_client.post('/api/add_corte', json={
        'codigo_barras': 'X123',
        'archivo': '../../etc/passwd',
    })
    assert r.status_code == 400


def test_datos_trabajo_v3_rechaza_traversal(client):
    r = client.get('/api/datos_trabajo_v3?archivo=../../etc/passwd&terminal=X')
    assert not r.get_json()['success']


def test_regenerar_no_expone_rutas_internas(admin_client):
    r = admin_client.post('/api/etiquetas/regenerar', json={'archivo': 'no_existe.xlsx'})
    assert r.status_code == 404
    msg = r.get_json()['message']
    assert 'no_existe.xlsx' in msg
    assert '/home/' not in msg and ':\\' not in msg


def test_manguitos_excel_rechaza_traversal_en_nombre(client, tmp_path, monkeypatch):
    """El nombre del Excel subido no puede escapar del directorio temporal.

    Werkzeug NO sanea FileStorage.filename, así que sin secure_filename un
    nombre como '../evil.xlsx' se guardaría fuera del tmpdir. Se fija el
    tmpdir a una ruta conocida para poder comprobar de forma determinista
    que no se escribe en su directorio padre.
    """
    import io
    import tempfile

    jaula = tmp_path / 'jaula'
    jaula.mkdir()
    monkeypatch.setattr(tempfile, 'mkdtemp', lambda *a, **kw: str(jaula))

    centinela = tmp_path / 'evil.xlsx'
    payload = {
        'excel': (io.BytesIO(b'no es un excel real'), '../evil.xlsx'),
        'ref': 'PC_CAB_BADEN',
        'edicion': 'ed_04',
    }
    client.post('/api/manguitos/generar-txt-desde-excel',
                data=payload, content_type='multipart/form-data')

    # El Excel es basura, así que la petición falla igualmente; lo que importa
    # es que no haya escrito nada fuera del directorio temporal.
    assert not centinela.exists()


def test_excel_manager_ruta_segura(tmp_path):
    em = ExcelManager(str(tmp_path))
    assert em._ruta_segura('normal.xlsx') is not None
    assert em._ruta_segura('../fuera.xlsx') is None
    assert em._ruta_segura('../../etc/passwd') is None
    assert em._ruta_segura('sub/../normal.xlsx') is not None
