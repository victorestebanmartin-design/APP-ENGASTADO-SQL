"""
WSGI entry point para despliegue en producción (Railway, Render, etc.)
Uso: gunicorn wsgi:app
"""
from consola_utf8 import forzar_utf8
forzar_utf8()

import os
from config import Config
from sqlite_setup import inicializar_sqlite


def _init_sqlite_db():
    """Crear archivo de base de datos SQLite si no existe"""
    db_path = Config.DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if not os.path.exists(db_path):
        schema_path = os.path.join(os.path.dirname(__file__), 'schema_sqlite.sql')
        if os.path.exists(schema_path):
            inicializar_sqlite(db_path, schema_path)


_init_sqlite_db()

from app import create_app  # noqa: E402 (importación después de init)
app = create_app(Config)
