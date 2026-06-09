"""
Inicialización de la aplicación Flask con SQLite
"""
from flask import Flask
from config import Config
import os
import re
import sqlite3


def _apply_migrations(db_path):
    """Aplica migraciones necesarias a la BD existente."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Obtener columnas actuales de etiquetas_elementos
    cur.execute("PRAGMA table_info(etiquetas_elementos)")
    cols = {row[1] for row in cur.fetchall()}

    # Columnas que pueden faltar
    missing = []
    if 'sub_numero' not in cols:
        missing.append("ALTER TABLE etiquetas_elementos ADD COLUMN sub_numero INTEGER NOT NULL DEFAULT 0")
    if 'es_grupo_padre' not in cols:
        missing.append("ALTER TABLE etiquetas_elementos ADD COLUMN es_grupo_padre INTEGER NOT NULL DEFAULT 0")
    if 'grupo_serie' not in cols:
        missing.append("ALTER TABLE etiquetas_elementos ADD COLUMN grupo_serie TEXT")

    for sql in missing:
        cur.execute(sql)
    conn.commit()

    # Comprobar si el UNIQUE constraint incluye sub_numero
    # (un ALTER TABLE añade la columna al SQL pero NO modifica el UNIQUE inline)
    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='etiquetas_elementos'"
    )
    row = cur.fetchone()
    table_sql = row[0] if row else ''
    unique_match = re.search(r'UNIQUE\s*\(([^)]+)\)', table_sql, re.IGNORECASE)
    unique_cols = unique_match.group(1) if unique_match else ''
    needs_recreate = 'sub_numero' not in unique_cols

    if needs_recreate:
        # Recrear tabla con el UNIQUE correcto preservando datos
        cur.executescript("""
            BEGIN;
            CREATE TABLE etiquetas_elementos_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archivo_excel TEXT NOT NULL,
                codigo_corte TEXT,
                orden_id TEXT,
                numero_etiqueta INTEGER NOT NULL,
                sub_numero INTEGER NOT NULL DEFAULT 0,
                es_grupo_padre INTEGER NOT NULL DEFAULT 0,
                grupo_serie TEXT,
                cod_cable TEXT NOT NULL,
                elemento TEXT NOT NULL,
                descripcion TEXT,
                seccion TEXT,
                longitud REAL,
                de_terminal TEXT,
                num_cables INTEGER DEFAULT 0,
                num_terminales INTEGER DEFAULT 0,
                fecha_generacion TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (orden_id) REFERENCES ordenes_produccion(id) ON DELETE CASCADE,
                UNIQUE(archivo_excel, numero_etiqueta, sub_numero)
            );
            INSERT OR IGNORE INTO etiquetas_elementos_new
                SELECT id, archivo_excel, codigo_corte, orden_id, numero_etiqueta,
                       COALESCE(sub_numero, 0), COALESCE(es_grupo_padre, 0),
                       grupo_serie, cod_cable, elemento, descripcion, seccion,
                       longitud, de_terminal, num_cables, num_terminales, fecha_generacion
                FROM etiquetas_elementos;
            DROP TABLE etiquetas_elementos;
            ALTER TABLE etiquetas_elementos_new RENAME TO etiquetas_elementos;
            CREATE INDEX IF NOT EXISTS idx_etiquetas_archivo ON etiquetas_elementos(archivo_excel);
            CREATE INDEX IF NOT EXISTS idx_etiquetas_codigo ON etiquetas_elementos(codigo_corte);
            CREATE INDEX IF NOT EXISTS idx_etiquetas_orden ON etiquetas_elementos(orden_id);
            CREATE INDEX IF NOT EXISTS idx_etiquetas_numero ON etiquetas_elementos(numero_etiqueta);
            CREATE INDEX IF NOT EXISTS idx_etiquetas_cable_elemento ON etiquetas_elementos(cod_cable, elemento);
            COMMIT;
        """)

    # Migración cable_colores.color_texto
    cur.execute("PRAGMA table_info(cable_colores)")
    cc_cols = {row[1] for row in cur.fetchall()}
    if cc_cols and 'color_texto' not in cc_cols:
        cur.execute("ALTER TABLE cable_colores ADD COLUMN color_texto TEXT")
        conn.commit()

    conn.close()


def create_app(config_class=Config):
    """
    Factory de aplicación Flask
    
    Args:
        config_class: Clase de configuración a usar
    
    Returns:
        Instancia de Flask configurada
    """
    # Rutas absolutas para templates y static (están en raíz del proyecto)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')
    
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir)
    app.config.from_object(config_class)
    
    # Inicializar base de datos
    from repositories import init_db
    db = init_db(app)

    # Aplicar migraciones pendientes
    db_path = app.config.get('DB_PATH', '')
    if db_path and os.path.exists(db_path):
        _apply_migrations(db_path)

    # Guardar extensión DB en app
    app.extensions['db'] = db
    
    # Registrar blueprints/rutas
    from app import routes
    routes.init_routes(app)
    
    return app
