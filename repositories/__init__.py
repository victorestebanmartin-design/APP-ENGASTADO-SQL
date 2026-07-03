"""
Inicialización de la capa de repositorios (Data Access Layer)
"""
import json
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base

# Base para modelos ORM (si se usa SQLAlchemy ORM)
Base = declarative_base()

# Variable global para la sesión
db = None

def init_db(app):
    """
    Inicializar conexión a base de datos
    
    Args:
        app: Instancia de Flask
    
    Returns:
        Objeto de base de datos configurado
    """
    global db
    
    # Crear engine
    engine = create_engine(
        app.config['SQLALCHEMY_DATABASE_URI'],
        echo=app.config.get('SQLALCHEMY_ECHO', False),
        pool_size=app.config.get('SQLALCHEMY_POOL_SIZE', 10),
        pool_recycle=app.config.get('SQLALCHEMY_POOL_RECYCLE', 3600),
        pool_timeout=app.config.get('SQLALCHEMY_POOL_TIMEOUT', 30),
        pool_pre_ping=True,  # Verificar conexiones antes de usar
        connect_args={'timeout': 30}
    )

    # PRAGMAs por conexión (SQLite los aplica por conexión, no globalmente)
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    
    # Crear sesión con scope thread-safe
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    
    # Guardar en objeto db
    class DB:
        def __init__(self, engine, session):
            self.engine = engine
            self.session = session
        
        def get_session(self):
            """Obtener sesión de base de datos"""
            return self.session()
        
        def close_session(self):
            """Cerrar sesión"""
            self.session.remove()
    
    db = DB(engine, Session)

    # Crear tabla cable_colores si no existe (instalaciones antiguas)
    from sqlalchemy import text as _text
    with engine.connect() as _conn:
        _conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS cable_colores (
                cod_cable TEXT PRIMARY KEY,
                color_hex TEXT NOT NULL,
                color_texto TEXT
            )
        """))
        # Migración: añadir color_texto si la tabla ya existía sin ella
        try:
            _conn.execute(_text("ALTER TABLE cable_colores ADD COLUMN color_texto TEXT"))
            _conn.commit()
        except Exception:
            pass  # ya existe

    # ── Seed inicial desde seed_inicial.json ──────────────────────────────
    # Los datos de la instalación (carros, puestos, máquinas, terminales y
    # colores de cables) viven en seed_inicial.json, no en el código.
    # INSERT OR IGNORE: solo se inserta lo que falte; lo gestionado desde el
    # panel de administración no se pisa.
    _seed_path = os.path.join(
        app.config.get('BASE_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'seed_inicial.json'
    )
    if os.path.exists(_seed_path):
        with open(_seed_path, encoding='utf-8') as _f:
            _seed = json.load(_f)
        with engine.connect() as _conn:
            for _n in _seed.get('carros', []):
                _conn.execute(_text(
                    "INSERT OR IGNORE INTO carros (numero) VALUES (:n)"
                ), {'n': _n})
            for _c in _seed.get('cable_colores', []):
                _conn.execute(_text(
                    "INSERT OR IGNORE INTO cable_colores (cod_cable, color_hex) VALUES (:c, :h)"
                ), {'c': _c['cod_cable'], 'h': _c['color_hex']})
            for _p in _seed.get('puestos', []):
                _conn.execute(_text(
                    "INSERT OR IGNORE INTO puestos (id, nombre, descripcion) VALUES (:i,:n,:d)"
                ), {'i': _p['id'], 'n': _p['nombre'], 'd': _p['descripcion']})
            for _m in _seed.get('maquinas', []):
                _conn.execute(_text(
                    "INSERT OR IGNORE INTO maquinas (id, puesto_id, nombre, modelo) VALUES (:i,:p,:n,:m)"
                ), {'i': _m['id'], 'p': _m['puesto_id'], 'n': _m['nombre'], 'm': _m['modelo']})
            for _mt in _seed.get('maquinas_terminales', []):
                _conn.execute(_text(
                    "INSERT OR IGNORE INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES (:m,:t)"
                ), {'m': _mt['maquina_id'], 't': _mt['terminal_codigo']})
            _conn.commit()
    else:
        app.logger.warning(f"seed_inicial.json no encontrado ({_seed_path}): BD sin datos iniciales")


    # Registrar teardown para cerrar sesiones
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.close_session()
    
    return db

