"""Impide restaurar datos mientras otra petición los está utilizando.

SQLite proporciona bloqueos compartidos/exclusivos entre hilos y procesos,
también en Windows. Esta BD de coordinación nunca forma parte del respaldo.
"""
import os
import sqlite3
from contextlib import closing
from flask import g, jsonify, request


def instalar_guardia(app):
    ruta = os.path.join(app.config['DATA_DIR'], '.maintenance.sqlite')
    with closing(sqlite3.connect(ruta)) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS guardia (id INTEGER)')
        conn.commit()
    exclusivos = {'main.api_importar_db', 'main.api_restaurar_backup',
                  'main.api_exportar_completo', 'main.api_exportar_db'}

    @app.before_request
    def adquirir():
        conn = sqlite3.connect(ruta, timeout=0.1, isolation_level=None)
        try:
            conn.execute('BEGIN EXCLUSIVE' if request.endpoint in exclusivos else 'BEGIN')
            conn.execute('SELECT * FROM guardia').fetchall()
        except sqlite3.OperationalError:
            conn.close()
            return jsonify(success=False, mensaje='Datos en uso. Espera unos segundos y vuelve a intentarlo.',
                           error='Datos en uso. Espera unos segundos y vuelve a intentarlo.'), 503, {'Retry-After': '2'}
        g.guard_datos = conn

    @app.teardown_request
    def liberar(error=None):
        conn = g.pop('guard_datos', None)
        if conn is not None:
            conn.rollback()
            conn.close()
