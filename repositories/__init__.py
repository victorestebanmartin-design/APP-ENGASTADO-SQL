"""
Inicialización de la capa de repositorios (Data Access Layer)
"""
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
        for _cod, _hex in _INITIAL_COLORS:
            _conn.execute(_text(
                "INSERT OR IGNORE INTO cable_colores (cod_cable, color_hex) VALUES (:c, :h)"
            ), {'c': _cod, 'h': _hex})
        _conn.commit()

    # ── Seed: puestos, máquinas, carros, maquinas_terminales ──────────────
    _PUESTOS = [
        ('puesto_001', 'TERMINALES AMP',  'Terminales AMP FORRADOS'),
        ('puesto_002', 'PINES RACK',       'Puesto secundario línea de producción 2'),
        ('puesto_3',   'PUNTERAS',         ''),
        ('puesto_4',   'MANUAL',           ''),
        ('puesto_005', 'MECATRACION',      ''),
    ]
    _MAQUINAS = [
        ('965d3fd8-a303-43e9-8697-73c7c69af473', 'puesto_001', 'AMP ROJA',          'AMP (47386) (TERMINALES ROJOS)'),
        ('0560d7b0-bd18-49cb-9671-edda662adbae', 'puesto_001', 'AMP AZUL',          'KOMAX Alpha 455'),
        ('5ebe085f-3839-4a71-96de-d0f5dd626ba0', 'puesto_001', 'AMP AMARILLOS',     ''),
        ('10823d83-f9ee-4645-ae00-6dfec2ec91c4', 'puesto_002', 'Harting 1mm',       'Pines 1mm'),
        ('50be0819-3273-4379-bdf3-fcde7d769fc3', 'puesto_002', 'Harting 0,5mm',     'Pines 0,5mm'),
        ('d748360d-af71-4e06-8896-9465b5c76b87', 'puesto_3',   'PUNTERAS',          ''),
        ('a4d166c9-8b53-4d7c-9992-44f031544786', 'puesto_3',   'WEIDMULLEER PZ10',  ''),
        ('e7fc8ea4-c3d9-48cc-abed-9297da959c80', 'puesto_4',   'DMC AZUL SH463',    ''),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', 'puesto_4',   'TAMBOR VERDE E',    ''),
        ('53411894-adea-4aa5-aa5e-1c554d8f6213', 'puesto_4',   'TAMBOR ROJO',       ''),
        ('243866c8-31fa-4eac-b888-3ccd43378c82', 'puesto_4',   'AMP SIMABLOCK',     ''),
        ('7bcff112-ee20-4345-b29f-102f7dc5faa2', 'puesto_4',   'DMC AZUL TH163',    ''),
        ('81651463-341f-46c1-9c1a-26232d87babb', 'puesto_4',   'HARTING AZUL',      ''),
        ('34ca90f9-0a1f-427e-9045-c9a8f4362649', 'puesto_4',   'POWER SIGNAL',      ''),
        ('47dd5926-0caf-4737-9cf9-8e1224e3259f', 'puesto_4',   'TAMBOR VERDE C',    ''),
        ('db1dae58-eaf1-4768-9b74-7bda5088c24e', 'puesto_4',   'TAMBOR VERDE D',    ''),
        ('maq_017',    'puesto_005', 'TH1',    'ROJA'),
        ('maq_018',    'puesto_005', 'TH2',    'AZUL'),
        ('maq_019',    'puesto_005', 'TH3',    'AMARILLA'),
        ('maq_020',    'puesto_005', 'TH3-2',  'AMARILLA AISLANTE GRUESO'),
    ]
    _MAQ_TERMINALES = [
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '640204'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '640243'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '640210'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '640230'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '640243A'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '641H002'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '641H039'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '641H056'),
        ('965d3fd8-a303-43e9-8697-73c7c69af473', '640260'),
        ('0560d7b0-bd18-49cb-9671-edda662adbae', '640205'),
        ('0560d7b0-bd18-49cb-9671-edda662adbae', '640211'),
        ('0560d7b0-bd18-49cb-9671-edda662adbae', '640261'),
        ('5ebe085f-3839-4a71-96de-d0f5dd626ba0', '640245'),
        ('5ebe085f-3839-4a71-96de-d0f5dd626ba0', '640206'),
        ('5ebe085f-3839-4a71-96de-d0f5dd626ba0', '640209'),
        ('5ebe085f-3839-4a71-96de-d0f5dd626ba0', '640212'),
        ('5ebe085f-3839-4a71-96de-d0f5dd626ba0', '641H057'),
        ('10823d83-f9ee-4645-ae00-6dfec2ec91c4', '641M155'),
        ('50be0819-3273-4379-bdf3-fcde7d769fc3', '641M10100'),
        ('d748360d-af71-4e06-8896-9465b5c76b87', '641H10055'),
        ('d748360d-af71-4e06-8896-9465b5c76b87', '641H10057'),
        ('d748360d-af71-4e06-8896-9465b5c76b87', '641H10058'),
        ('d748360d-af71-4e06-8896-9465b5c76b87', '641H10056'),
        ('a4d166c9-8b53-4d7c-9992-44f031544786', 'H0337649'),
        ('e7fc8ea4-c3d9-48cc-abed-9297da959c80', '641M10293'),
        ('e7fc8ea4-c3d9-48cc-abed-9297da959c80', '641M10295'),
        ('e7fc8ea4-c3d9-48cc-abed-9297da959c80', '641M10292'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M600'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M082'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M644'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M026'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M027'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M645'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M532'),
        ('1de662fd-4d78-4921-a490-266cfc283fb3', '641M029'),
        ('53411894-adea-4aa5-aa5e-1c554d8f6213', '641M937'),
        ('53411894-adea-4aa5-aa5e-1c554d8f6213', '641M936'),
        ('243866c8-31fa-4eac-b888-3ccd43378c82', '640304D'),
        ('243866c8-31fa-4eac-b888-3ccd43378c82', '640305'),
        ('7bcff112-ee20-4345-b29f-102f7dc5faa2', '641M10196'),
        ('81651463-341f-46c1-9c1a-26232d87babb', '641M10091'),
        ('81651463-341f-46c1-9c1a-26232d87babb', '641M239'),
        ('34ca90f9-0a1f-427e-9045-c9a8f4362649', '641M10045'),
        ('47dd5926-0caf-4737-9cf9-8e1224e3259f', '641M613'),
        ('47dd5926-0caf-4737-9cf9-8e1224e3259f', '641M594'),
        ('db1dae58-eaf1-4768-9b74-7bda5088c24e', '641M10078'),
        ('db1dae58-eaf1-4768-9b74-7bda5088c24e', '641M577'),
        ('db1dae58-eaf1-4768-9b74-7bda5088c24e', '641M466'),
        ('db1dae58-eaf1-4768-9b74-7bda5088c24e', '641M531'),
        ('db1dae58-eaf1-4768-9b74-7bda5088c24e', '641M574'),
        ('db1dae58-eaf1-4768-9b74-7bda5088c24e', '641M576'),
        ('maq_017', '641H10001'),
        ('maq_017', '641H10003'),
        ('maq_017', '641H10006'),
        ('maq_017', '641H10009'),
        ('maq_017', '641H10039'),
        ('maq_017', '641H10043'),
        ('maq_017', '641H10047'),
        ('maq_017', '641H10048'),
        ('maq_017', '641H10069'),
        ('maq_017', '641H10014'),
        ('maq_018', ''),  # placeholder, TH2 sin terminales asignados
        ('maq_019', ''),  # placeholder, TH3 sin terminales asignados
        ('maq_020', ''),  # placeholder, TH3-2 sin terminales asignados
    ]
    with engine.connect() as _conn:
        # Carros 1-6
        for _n in range(1, 7):
            _conn.execute(_text(
                "INSERT OR IGNORE INTO carros (numero) VALUES (:n)"
            ), {'n': _n})
        # Puestos
        for _id, _nom, _desc in _PUESTOS:
            _conn.execute(_text(
                "INSERT OR IGNORE INTO puestos (id, nombre, descripcion) VALUES (:i,:n,:d)"
            ), {'i': _id, 'n': _nom, 'd': _desc})
        # Máquinas
        for _id, _pid, _nom, _mod in _MAQUINAS:
            _conn.execute(_text(
                "INSERT OR IGNORE INTO maquinas (id, puesto_id, nombre, modelo) VALUES (:i,:p,:n,:m)"
            ), {'i': _id, 'p': _pid, 'n': _nom, 'm': _mod})
        # Terminales por máquina (saltar filas placeholder vacías)
        for _maq, _term in _MAQ_TERMINALES:
            if not _term:
                continue
            _conn.execute(_text(
                "INSERT OR IGNORE INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES (:m,:t)"
            ), {'m': _maq, 't': _term})
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
