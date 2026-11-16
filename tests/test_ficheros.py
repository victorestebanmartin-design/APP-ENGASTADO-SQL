"""En Windows, os.replace falla con «Acceso denegado» si alguien tiene abierto
el destino en ese instante. app/ficheros.py reintenta; aquí se comprueba que
lo hace y que nadie en app/ vuelve a llamar a os.replace por su cuenta."""
import ast
import os

import pytest

from app import ficheros

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def sin_esperas(monkeypatch):
    monkeypatch.setattr(ficheros.time, 'sleep', lambda s: None)


def _replace_que_falla(monkeypatch, veces, error=PermissionError(13, 'Acceso denegado')):
    """os.replace que falla `veces` veces y luego funciona. Devuelve el contador."""
    real = os.replace
    llamadas = []

    def falso(origen, destino):
        llamadas.append(1)
        if len(llamadas) <= veces:
            raise error
        return real(origen, destino)

    monkeypatch.setattr(ficheros.os, 'replace', falso)
    return llamadas


def test_sustituye_el_fichero(tmp_path):
    origen, destino = tmp_path / 'nuevo', tmp_path / 'bueno'
    origen.write_text('nuevo', encoding='utf-8')
    destino.write_text('viejo', encoding='utf-8')
    ficheros.reemplazar_con_reintento(str(origen), str(destino))
    assert destino.read_text(encoding='utf-8') == 'nuevo'
    assert not origen.exists()


def test_reintenta_si_windows_niega_el_acceso(tmp_path, monkeypatch, sin_esperas):
    origen, destino = tmp_path / 'nuevo', tmp_path / 'bueno'
    origen.write_text('nuevo', encoding='utf-8')
    llamadas = _replace_que_falla(monkeypatch, veces=3)
    ficheros.reemplazar_con_reintento(str(origen), str(destino))
    assert len(llamadas) == 4
    assert destino.read_text(encoding='utf-8') == 'nuevo'


def test_si_no_lo_sueltan_acaba_fallando(tmp_path, monkeypatch, sin_esperas):
    origen = tmp_path / 'nuevo'
    origen.write_text('nuevo', encoding='utf-8')
    llamadas = _replace_que_falla(monkeypatch, veces=999)
    with pytest.raises(PermissionError):
        ficheros.reemplazar_con_reintento(str(origen), str(tmp_path / 'bueno'))
    assert len(llamadas) == 20


def test_otros_errores_no_se_reintentan(tmp_path, monkeypatch, sin_esperas):
    llamadas = _replace_que_falla(monkeypatch, veces=999, error=FileNotFoundError(2, 'No existe'))
    with pytest.raises(FileNotFoundError):
        ficheros.reemplazar_con_reintento(str(tmp_path / 'no_esta'), str(tmp_path / 'bueno'))
    assert len(llamadas) == 1


def _excel(ruta):
    from openpyxl import Workbook
    libro = Workbook()
    libro.active.title = 'Format'
    libro.active.append(['Cable', 'De Terminal'])
    libro.save(ruta)


def _sin_recolector():
    """Un Excel sin cerrar solo molesta hasta que pasa el recolector: se apaga
    para que el test no dependa de cuándo le toque."""
    import gc
    gc.collect()
    gc.disable()
    return gc


def test_mirar_las_hojas_no_deja_el_excel_abierto(tmp_path):
    """pd.ExcelFile sin cerrar deja el fichero cogido: en Windows no se podía
    sustituir después (revertir una propuesta devolvía 403)."""
    from app.routes.base import _detectar_hoja
    ruta = str(tmp_path / 'corte.xlsx')
    _excel(ruta)
    gc = _sin_recolector()
    try:
        assert _detectar_hoja(ruta) == 'Format'
        os.replace(ruta, ruta + '.movido')
    finally:
        gc.enable()


def test_subir_un_excel_no_lo_deja_abierto(app, admin_client):
    import io
    origen = os.path.join(app.config['DATA_DIR'], 'origen.xlsx')
    _excel(origen)
    with open(origen, 'rb') as f:
        contenido = f.read()
    gc = _sin_recolector()
    try:
        r = admin_client.post('/api/upload', data={'file': (io.BytesIO(contenido), 'corte.xlsx')},
                              content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        subido = os.path.join(app.config['UPLOAD_FOLDER'], 'corte.xlsx')
        os.replace(subido, subido + '.movido')
    finally:
        gc.enable()


def test_los_tests_no_llegan_a_una_placa_de_verdad():
    """La red de seguridad de conftest.py (sin_placas_de_verdad) está puesta."""
    import subprocess
    import sys
    r = subprocess.run([sys.executable, '-m', 'mpremote', 'connect', 'COM5', 'reset'],
                       capture_output=True, text=True, timeout=5)
    assert r.returncode == 1
    assert 'desactivado en los tests' in r.stderr
    r = subprocess.run([sys.executable, '-m', 'esptool', '--port', 'COM5', 'erase_flash'],
                       capture_output=True, text=True, timeout=5)
    assert r.returncode == 1
    serial = pytest.importorskip('serial')
    with pytest.raises(serial.SerialException):
        serial.Serial('COM5', 115200)


def test_nadie_en_app_llama_a_os_replace_directamente():
    """Si salta: usa app.ficheros.reemplazar en vez de os.replace."""
    culpables = []
    for carpeta, _, nombres in os.walk(os.path.join(RAIZ, 'app')):
        for nombre in nombres:
            ruta = os.path.join(carpeta, nombre)
            if not nombre.endswith('.py') or os.path.samefile(ruta, ficheros.__file__):
                continue
            with open(ruta, encoding='utf-8') as f:
                arbol = ast.parse(f.read())
            for nodo in ast.walk(arbol):
                if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                        and nodo.func.attr in ('replace', 'rename')
                        and isinstance(nodo.func.value, ast.Name) and nodo.func.value.id == 'os'):
                    culpables.append(f'{os.path.relpath(ruta, RAIZ)}:{nodo.lineno}')
    assert culpables == []
