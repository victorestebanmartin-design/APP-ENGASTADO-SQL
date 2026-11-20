"""
Fixtures compartidas para los tests.

Cada test recibe una app Flask con su propia base de datos SQLite temporal
(creada desde schema_sqlite.sql), de forma que nunca se toca data/engastado.db.
"""
import hashlib
import logging
import os
import shutil
import sqlite3
import sys
import time

import pytest

# Raíz del proyecto en el path para poder importar app/ y repositories/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from config import Config  # noqa: E402

PIN_TEST = '1234'
PIN_TEST_HASH = hashlib.sha256(PIN_TEST.encode()).hexdigest()


def _crear_bd_temporal(db_path):
    """Crea una BD nueva desde schema_sqlite.sql."""
    schema_path = os.path.join(BASE_DIR, 'schema_sqlite.sql')
    conn = sqlite3.connect(db_path)
    with open(schema_path, encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.close()


def _crear_app(tmp_path, db_path):
    """App Flask sobre esa BD, con sus carpetas de datos dentro de tmp_path."""
    data_dir = tmp_path / 'data'
    upload_dir = data_dir / 'cortes'
    upload_dir.mkdir(parents=True)

    class TestConfig(Config):
        TESTING = True
        DB_PATH = db_path
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
        DATA_DIR = str(data_dir)
        UPLOAD_FOLDER = str(upload_dir)
        PRINTER_SIMULATION_DIR = str(data_dir / 'etiquetas_simuladas')
        LOG_FILE = str(tmp_path / 'logs' / 'app.log')
        ADMIN_PIN_HASH = PIN_TEST_HASH

        @staticmethod
        def init_app(app):
            os.makedirs(TestConfig.DATA_DIR, exist_ok=True)
            os.makedirs(TestConfig.UPLOAD_FOLDER, exist_ok=True)
            os.makedirs(TestConfig.PRINTER_SIMULATION_DIR, exist_ok=True)

    from app import create_app
    return create_app(TestConfig)


def _soltar_app(aplicacion):
    """Cierra lo que la app deja abierto: conexiones a la BD y el log.

    Todas las apps comparten el logger 'app'. Sin quitar su handler, cada test
    dejaba uno más colgado y cada línea de log se escribía en los ficheros de
    todos los tests anteriores: la suite iba cada vez más lenta. En Windows,
    además, un fichero abierto no deja borrar la carpeta temporal."""
    aplicacion.extensions['db'].engine.dispose()
    for handler in list(aplicacion.logger.handlers):
        if isinstance(handler, logging.FileHandler):
            aplicacion.logger.removeHandler(handler)
            handler.close()


@pytest.fixture(scope='session')
def _bd_plantilla(tmp_path_factory):
    """BD ya creada, migrada y con el seed, hecha UNA vez por sesión.

    Crear la BD desde schema_sqlite.sql y pasarle todas las migraciones de
    create_app costaba un tercio de segundo por test, y hay más de mil. Cada
    test parte de una copia de este fichero: create_app vuelve a repasar las
    migraciones, pero ya no encuentra nada que hacer."""
    carpeta = tmp_path_factory.mktemp('plantilla')
    db_path = str(carpeta / 'plantilla.db')
    _crear_bd_temporal(db_path)
    _soltar_app(_crear_app(carpeta, db_path))
    # Todo lo escrito tiene que estar en el .db: lo que siga en el -wal no
    # viajaría con la copia.
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()
    return db_path


@pytest.fixture
def app(tmp_path, _bd_plantilla, monkeypatch):
    """App Flask con BD y carpetas de datos temporales."""
    db_path = str(tmp_path / 'engastado_test.db')
    shutil.copyfile(_bd_plantilla, db_path)
    aplicacion = _crear_app(tmp_path, db_path)

    # El contador anti fuerza bruta del PIN es global: limpiarlo entre tests
    from app.routes import paginas
    paginas._PIN_INTENTOS.clear()
    # La pausa de 1 s tras cada PIN fallado solo es tiempo perdido en los tests
    monkeypatch.setattr(paginas, '_PIN_PAUSA_FALLO_SEG', 0)

    # Igual el freno del barrido de logins caducados: es global del módulo y,
    # si otro test barrió hace menos de 30 s, el de este se salta el barrido.
    from app.routes import operarios
    operarios._ultima_expiracion[0] = float('-inf')

    yield aplicacion
    _soltar_app(aplicacion)


@pytest.fixture
def client(app):
    """Cliente HTTP sin sesión de administración."""
    return app.test_client()


HERRAMIENTAS_DE_PLACA = ('mpremote', 'esptool')


@pytest.fixture(autouse=True)
def sin_placas_de_verdad(monkeypatch):
    """Ningún test habla con una placa real por USB.

    Los endpoints de flasheo lanzan mpremote/esptool contra el puerto que se
    les pasa. Un test que llegaba hasta ahí con 'COM5' esperaba medio minuto a
    que la herramienta se rindiera -- y con una placa enchufada en ese puerto
    le habría copiado el firmware, o borrado la flash. Aquí esas herramientas
    responden al momento como si no hubiera nada conectado, y el puerto serie
    no se deja abrir. El test que quiera simular una placa que contesta parchea
    por su cuenta (subprocess.run, _interrumpir_placa...), como ya hacían.
    """
    import subprocess
    real_run = subprocess.run

    def run(comando, *args, **kwargs):
        if isinstance(comando, (list, tuple)) and any(h in comando for h in HERRAMIENTAS_DE_PLACA):
            return subprocess.CompletedProcess(
                comando, 1, stdout='',
                stderr='Puerto serie desactivado en los tests: no hay placa conectada')
        return real_run(comando, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', run)

    # La pantalla grande (P4) se compila y graba con arduino-cli por Popen:
    # aquí falla al momento, como si no hubiera placa ni toolchain.
    from app import pantalla_p4

    def sin_arduino(comando, timeout, al_linea):
        al_linea('arduino-cli desactivado en los tests')
        return 1, False

    monkeypatch.setattr(pantalla_p4, '_ejecutar', sin_arduino)

    try:
        import serial
    except ImportError:
        return

    def sin_puerto(*args, **kwargs):
        raise serial.SerialException('Puerto serie desactivado en los tests')

    monkeypatch.setattr(serial, 'Serial', sin_puerto)


def _cliente_admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['admin_verificado'] = True
        s['admin_verificado_ts'] = time.time()
    return c


def admin_de(client):
    """Cliente con sesión de administración sobre la misma app que `client`.

    Para preparar datos que solo Administración puede tocar (alta de
    operarios, sus tarjetas...) sin darle la sesión de admin al cliente que
    luego hace de operario o de PC de planta en el test."""
    return _cliente_admin(client.application)


@pytest.fixture
def admin_client(app):
    """Cliente HTTP con sesión de administración ya verificada."""
    return _cliente_admin(app)
