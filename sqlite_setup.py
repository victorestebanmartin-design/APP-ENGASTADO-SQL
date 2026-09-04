"""Utilidades compartidas para crear de forma segura la base de datos SQLite."""

import os
import sqlite3


def inicializar_sqlite(db_path, schema_path):
    """Crea ``db_path`` desde ``schema_path`` si todavía no existe.

    ``sqlite3.connect`` crea el fichero antes de ejecutar el esquema. Si el
    esquema falla y se deja ese fichero a medias, el siguiente arranque cree
    que la base ya está inicializada. Por eso eliminamos todos los artefactos
    de la creación fallida antes de propagar el error.

    Returns:
        ``True`` si se creó la base y ``False`` si ya existía.
    """
    if os.path.exists(db_path):
        return False

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = None
    try:
        with open(schema_path, encoding='utf-8') as schema_file:
            schema_sql = schema_file.read()

        conn = sqlite3.connect(db_path)
        conn.executescript(schema_sql)
        conn.close()
        conn = None
        return True
    except Exception:
        if conn is not None:
            conn.close()
        # WAL puede crear ficheros auxiliares incluso aunque el esquema no
        # llegue a completarse. Ninguno debe sobrevivir al intento fallido.
        for suffix in ('', '-wal', '-shm', '-journal'):
            try:
                os.remove(db_path + suffix)
            except FileNotFoundError:
                pass
        raise
