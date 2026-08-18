"""
Inicialización de la aplicación Flask con SQLite
"""
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException
from config import Config
import os
import re
import uuid
import logging
from logging.handlers import RotatingFileHandler
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
    if 'numero_etiqueta_original' not in cols:
        missing.append("ALTER TABLE etiquetas_elementos ADD COLUMN numero_etiqueta_original INTEGER")
    if 'es_padre_manual' not in cols:
        missing.append("ALTER TABLE etiquetas_elementos ADD COLUMN es_padre_manual INTEGER NOT NULL DEFAULT 0")

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

    # Migración: tabla operarios (identificación controlada)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operarios (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_operarios_activo ON operarios(activo)")
    conn.commit()

    # Migración: tarjeta NFC por operario (login por tarjeta y confirmaciones
    # en el carro identificadas por operario, no por puesto).
    cur.execute("PRAGMA table_info(operarios)")
    op_cols = {row[1] for row in cur.fetchall()}
    if op_cols and 'tag_uid' not in op_cols:
        cur.execute("ALTER TABLE operarios ADD COLUMN tag_uid TEXT")
        conn.commit()
    if op_cols:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_operarios_tag ON operarios(tag_uid)
            WHERE tag_uid IS NOT NULL AND activo = 1
        """)
        conn.commit()

    # Migración: permisos por operario (que módulos puede ver en /modules).
    # NULL = todos los modulos permitidos (asi nadie se queda fuera justo
    # tras esta migracion); '[]' explicito = ninguno. Ver
    # app/routes/base.py:modulos_permitidos_de().
    if op_cols and 'modulos_permitidos' not in op_cols:
        cur.execute("ALTER TABLE operarios ADD COLUMN modulos_permitidos TEXT")
        conn.commit()

    # Migración: tabla sesiones_trabajo (bloqueo de paquetes concurrente)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sesiones_trabajo (
            id TEXT PRIMARY KEY,
            maquina_id TEXT NOT NULL,
            terminal_codigo TEXT NOT NULL,
            archivo_excel TEXT NOT NULL,
            carro_numero TEXT,
            paquetes_json TEXT NOT NULL DEFAULT '[]',
            timestamp_inicio TEXT NOT NULL DEFAULT (datetime('now')),
            activo INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_maquina ON sesiones_trabajo(maquina_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_activas ON sesiones_trabajo(activo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_terminal ON sesiones_trabajo(terminal_codigo)")
    conn.commit()

    # Migración: identificación del puesto en la pantalla del carro
    # (boton = pulsador 1-7, tag_uid = tarjeta NFC)
    cur.execute("PRAGMA table_info(puestos)")
    p_cols = {row[1] for row in cur.fetchall()}
    if p_cols and 'boton' not in p_cols:
        cur.execute("ALTER TABLE puestos ADD COLUMN boton INTEGER")
        conn.commit()
    if p_cols and 'tag_uid' not in p_cols:
        cur.execute("ALTER TABLE puestos ADD COLUMN tag_uid TEXT")
        conn.commit()
    if p_cols:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_puestos_boton ON puestos(boton)
            WHERE boton IS NOT NULL AND activo = 1
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_puestos_tag ON puestos(tag_uid)
            WHERE tag_uid IS NOT NULL AND activo = 1
        """)
        conn.commit()

    # Migración: tabla operario_logins (login exclusivo de operarios en engastado)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operario_logins (
            id TEXT PRIMARY KEY,
            operario_nombre TEXT NOT NULL,
            timestamp_login TEXT NOT NULL DEFAULT (datetime('now')),
            ultimo_latido TEXT NOT NULL DEFAULT (datetime('now')),
            activo INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_operario_logins_activo ON operario_logins(activo)")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_operario_logins_nombre_activo
        ON operario_logins(operario_nombre) WHERE activo = 1
    """)
    conn.commit()

    # Migración: puesto_id en operario_logins. Cuando el login viene de un
    # lector RFID asignado a un puesto (Admin -> Lectores RFID), se guarda
    # aquí para que el navegador (que solo sondea /api/operarios/logins) sepa
    # a qué puesto saltar sin que el operario tenga que elegirlo a mano.
    try:
        cur.execute("ALTER TABLE operario_logins ADD COLUMN puesto_id TEXT")
        conn.commit()
    except Exception:
        pass  # ya existe

    # Migración: tabla terminales_imagenes (iconos/fotos de cada terminal)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS terminales_imagenes (
            terminal_codigo TEXT PRIMARY KEY,
            imagen_data     TEXT NOT NULL,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # Migración: tabla terminales_gavetas (ubicación física del terminal)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS terminales_gavetas (
            terminal_codigo TEXT PRIMARY KEY,
            gaveta          TEXT NOT NULL,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # Migración: columnas tipo_operacion y pdf_instrucciones en maquinas
    cur.execute("PRAGMA table_info(maquinas)")
    maq_cols = {row[1] for row in cur.fetchall()}
    if maq_cols:
        if 'tipo_operacion' not in maq_cols:
            cur.execute("ALTER TABLE maquinas ADD COLUMN tipo_operacion TEXT NOT NULL DEFAULT 'MANUAL'")
        if 'pdf_instrucciones' not in maq_cols:
            cur.execute("ALTER TABLE maquinas ADD COLUMN pdf_instrucciones TEXT")
        if 'lleva_regulacion' not in maq_cols:
            cur.execute("ALTER TABLE maquinas ADD COLUMN lleva_regulacion INTEGER NOT NULL DEFAULT 0")
        if 'pdf_regulacion' not in maq_cols:
            cur.execute("ALTER TABLE maquinas ADD COLUMN pdf_regulacion TEXT")
        conn.commit()

    # Migración: tabla terminales_stock (stock de terminales por pedido)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS terminales_stock (
            terminal_codigo TEXT PRIMARY KEY,
            stock_actual    INTEGER NOT NULL DEFAULT 0,
            stock_minimo    INTEGER NOT NULL DEFAULT 0,
            notas           TEXT,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # Migración: tabla esp32_ips (IP fija de cada placa ESP32).
    # La red de planta no tiene DHCP, asi que cada placa lleva su IP grabada
    # en el firmware; aqui se registra cual tiene cada una (device_id = MAC)
    # para no repetirlas y poder reflashear sin recordarlas a mano.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS esp32_ips (
            device_id  TEXT PRIMARY KEY,
            tipo       TEXT NOT NULL DEFAULT 'display',
            nombre     TEXT,
            ip         TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # UNIQUE sobre la IP: la unicidad se valida antes de escribir, pero el
    # indice la garantiza tambien si dos flasheos coinciden en el tiempo.
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_esp32_ips_ip ON esp32_ips(ip)")
    conn.commit()

    # Migración: tabla terminales_ignorados (terminales desactivados de la vista)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS terminales_ignorados (
            terminal_codigo TEXT PRIMARY KEY,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
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

    # Crear directorios necesarios (data, uploads, logs, ...)
    if hasattr(config_class, 'init_app'):
        config_class.init_app(app)

    # Configurar logging hacia fichero con rotación
    _configurar_logging(app)

    # Aviso si el módulo de administración no está protegido por PIN
    if not app.config.get('ADMIN_PIN_HASH'):
        aviso = ("ADVERTENCIA: el modulo de ADMINISTRACION esta SIN PROTEGER "
                 "(no hay ADMIN_PIN_HASH en el .env). Cualquiera con acceso a la "
                 "web puede entrar al panel de administracion. Genera un PIN con "
                 "'python _scripts_utiles/generar_pin_hash.py' y ponlo en el .env.")
        print("\n" + "=" * 70)
        print(aviso)
        print("=" * 70 + "\n")
        app.logger.warning(aviso)

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

    # Handler global para excepciones no controladas
    @app.errorhandler(Exception)
    def _manejar_excepcion_no_controlada(e):
        # Las HTTPException (404, 405, 400 abortados, ...) pasan sin tocar
        if isinstance(e, HTTPException):
            return e
        error_id = uuid.uuid4().hex[:8]
        app.logger.exception(f"[{error_id}] Excepción no controlada: {e}")
        return jsonify({
            'success': False,
            'message': f'Error interno del servidor (ref: {error_id})'
        }), 500

    return app


def _configurar_logging(app):
    """Configura un RotatingFileHandler hacia Config.LOG_FILE."""
    log_file = app.config.get('LOG_FILE')
    log_level = getattr(logging, str(app.config.get('LOG_LEVEL', 'INFO')).upper(), logging.INFO)

    if not log_file:
        return

    # Asegurar que el directorio de logs existe
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Evitar añadir el handler más de una vez (p.ej. con el reloader)
    ya_configurado = any(
        isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', None) == os.path.abspath(log_file)
        for h in app.logger.handlers
    )
    if ya_configurado:
        return

    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding='utf-8')
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(module)s: %(message)s'
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)
