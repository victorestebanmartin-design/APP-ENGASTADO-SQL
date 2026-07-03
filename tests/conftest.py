"""
Fixtures compartidas para los tests.

Cada test recibe una app Flask con su propia base de datos SQLite temporal
(creada desde schema_sqlite.sql), de forma que nunca se toca data/engastado.db.
"""
import hashlib
import os
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


@pytest.fixture
def app(tmp_path):
    """App Flask con BD y carpetas de datos temporales."""
    db_path = str(tmp_path / 'engastado_test.db')
    _crear_bd_temporal(db_path)

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
    aplicacion = create_app(TestConfig)

    # El contador anti fuerza bruta del PIN es global: limpiarlo entre tests
    from app import routes
    routes._PIN_INTENTOS.clear()

    yield aplicacion


@pytest.fixture
def client(app):
    """Cliente HTTP sin sesión de administración."""
    return app.test_client()


@pytest.fixture
def admin_client(app):
    """Cliente HTTP con sesión de administración ya verificada."""
    c = app.test_client()
    with c.session_transaction() as s:
        s['admin_verificado'] = True
        s['admin_verificado_ts'] = time.time()
    return c
