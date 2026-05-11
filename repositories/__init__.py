"""
Inicialización de la capa de repositorios (Data Access Layer)
"""
from sqlalchemy import create_engine
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
        pool_pre_ping=True  # Verificar conexiones antes de usar
    )
    
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
    
    # Crear tabla cable_colores si no existe y cargar valores iniciales
    _INITIAL_COLORS = [
        ('640361',      '#0f766e'),
        ('640362',      '#b45309'),
        ('640C10006A',  '#4d7c0f'),
        ('640C10008A',  '#7c3aed'),
        ('640C10014',   '#be185d'),
        ('640C10021A',  '#4f46e5'),
        ('640C10022A',  '#0891b2'),
        ('640C10023',   '#dc2626'),
        ('640C10024A',  '#65a30d'),
        ('640C10025A',  '#059669'),
        ('640C10040A',  '#0e7490'),
        ('640C10041',   '#db2777'),
        ('640D10002',   '#2563eb'),
        ('640D10009A',  '#1d4ed8'),
        ('640D10017',   '#d97706'),
        ('640D10023',   '#b91c1c'),
        ('640D10029A',  '#047857'),
        ('640D20000',   '#6d28d9'),
        ('GRUPO_SERIE', '#f59e0b'),
        ('H0211195',    '#831843'),
    ]
    from sqlalchemy import text as _text
    with engine.connect() as _conn:
        _conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS cable_colores (
                cod_cable TEXT PRIMARY KEY,
                color_hex TEXT NOT NULL
            )
        """))
        for _cod, _hex in _INITIAL_COLORS:
            _conn.execute(_text(
                "INSERT OR IGNORE INTO cable_colores (cod_cable, color_hex) VALUES (:c, :h)"
            ), {'c': _cod, 'h': _hex})
        _conn.commit()

    # Registrar teardown para cerrar sesiones
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.close_session()
    
    return db


# TODO: Importar repositorios cuando estén implementados
# from .proyecto_repository import ProyectoRepository
# from .orden_repository import OrdenRepository
# from .bono_repository import BonoRepository
# ...
