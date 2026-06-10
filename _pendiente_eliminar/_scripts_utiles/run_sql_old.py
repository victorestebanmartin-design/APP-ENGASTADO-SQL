"""
Script principal para ejecutar la aplicación SQL
Versión 2.0 - SQLite (sin permisos admin)
"""
import socket
import sys
import logging
from logging.handlers import RotatingFileHandler
import os
import sqlite3

# Verificar dependencias antes de importar
try:
    import sqlalchemy
    from flask import Flask
except ImportError as e:
    print("=" * 80)
    print("❌ ERROR: Faltan dependencias")
    print("=" * 80)
    print(f"Detalle: {e}")
    print("\nPor favor ejecuta:")
    print("  pip install -r requirements.txt")
    print("=" * 80)
    sys.exit(1)

"""
Script principal para ejecutar la aplicación SQL
Versión 2.0 - SQLite (sin permisos admin)
"""
import socket
import sys
import logging
from logging.handlers import RotatingFileHandler
import os
import sqlite3

# Verificar dependencias antes de importar
try:
    import sqlalchemy
    from flask import Flask
except ImportError as e:
    print("=" * 80)
    print("❌ ERROR: Faltan dependencias")
    print("=" * 80)
    print(f"Detalle: {e}")
    print("\nPor favor ejecuta:")
    print("  pip install -r requirements.txt")
    print("=" * 80)
    sys.exit(1)

from config import Config

def create_app():
    """Crear y configurar la aplicación Flask"""
    
    # Configurar logging
    setup_logging()
    
    # Inicializar base de datos SQLite
    init_sqlite_db()
    
    # Verificar conexión SQLite
    if not verificar_conexion_sqlite():
        logger = logging.getLogger(__name__)
        logger.error("No se pudo conectar a la base de datos SQLite")
        print("\n⚠️  ADVERTENCIA: No hay conexión a la base de datos")
        print("Verifica que existe data/engastado.db\n")
    
    # Usar el factory de app
    from app import create_app as app_factory
    app = app_factory(Config)
    
    return app

                "db_path": app.config['DB_PATH']
            }
        except Exception as e:
            return {
                "status": "error",
                "database": "disconnected",
                "error": str(e)
            }, 500
    
    return app

def init_sqlite_db(app):
    """Inicializar base de datos SQLite si no existe"""
    db_path = app.config['DB_PATH']
    
    # Crear directorio data si no existe
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Si la BD no existe, crearla desde schema_sqlite.sql
    if not os.path.exists(db_path):
        app.logger.info(f"❗ Base de datos no existe, creando: {db_path}")
        schema_path = os.path.join(app.config['BASE_DIR'], 'schema_sqlite.sql')
        
        if os.path.exists(schema_path):
            try:
                conn = sqlite3.connect(db_path)
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                conn.executescript(schema_sql)
                conn.close()
                app.logger.info("✅ Base de datos SQLite creada exitosamente")
                print(f"✅ Base de datos creada: {db_path}")
            except Exception as e:
                app.logger.error(f"❌ Error creando base de datos: {e}")
                print(f"❌ Error creando base de datos: {e}")
        else:
            app.logger.warning(f"⚠️  No se encontró schema_sqlite.sql en {schema_path}")
            print(f"⚠️  No se encontró schema_sqlite.sql")
    else:
        app.logger.info(f"✅ Base de datos existe: {db_path}")
        print(f"✅ Usando base de datos: {db_path}")

def setup_logging(app):
    """Configurar sistema de logs"""
    if not app.debug:
        # Crear directorio de logs
        log_dir = os.path.join(app.config['BASE_DIR'], 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Handler de archivo con rotación
        file_handler = RotatingFileHandler(
            app.config['LOG_FILE'],
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
    
    app.logger.setLevel(logging.INFO)
    app.logger.info('Aplicación iniciando...')

def verificar_conexion_sqlite(app):
    """Verificar que se puede conectar a SQLite"""
    try:
        from sqlalchemy import text
        from repositories import db
        
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.scalar()
            # Verificar WAL mode
            result = conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            if mode == 'wal':
                app.logger.info("✅ SQLite WAL mode habilitado (mejor concurrencia)")
        
        app.logger.info("✅ Conexión a SQLite exitosa")
        return True
    except Exception as e:
        app.logger.error(f"❌ Error conectando a SQLite: {e}")
        return False

def get_local_ip():
    """Obtiene la IP local de la máquina"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "[IP no disponible]"

def verificar_drivers_odbc():
    """SQLite no necesita drivers ODBC, retornar info de SQLite"""
    try:
        conn = sqlite3.connect(":memory:")
        version = sqlite3.sqlite_version
        conn.close()
        return version
    except Exception as e:
        return None

if __name__ == '__main__':
    # Obtener versión de SQLite
    sqlite_version = verificar_drivers_odbc()
    
    print("=" * 80)
    print("🚀 SISTEMA DE ENGASTADO AUTOMÁTICO - SQLite V2.0")
    print("=" * 80)
    
    if sqlite_version:
        print(f"✅ SQLite versión: {sqlite_version}")
        print("✅ NO requiere permisos de administrador")
        print("✅ Soporta 4-10 usuarios concurrentes (WAL mode)")
    else:
        print("⚠️  No se pudo verificar versión de SQLite")
    
    print("=" * 80)
    
    # Crear app
    env = os.environ.get('FLASK_ENV', 'development')
    app = create_app(env)
    
    local_ip = get_local_ip()
    port = int(os.environ.get('PORT', 5001))  # Puerto 5001 para no conflictuar con app vieja
    
    print(f"\n📍 Servidor iniciado en:")
    print(f"   Local:      http://localhost:{port}")
    print(f"   Red local:  http://{local_ip}:{port}")
    print(f"\n💡 Entorno: {env}")
    print(f"💾 Base de datos: SQLite (archivo: {app.config.get('DB_PATH', 'data/engastado.db')})")
    print(f"🖨️  Impresora: {'Simulación' if app.config.get('PRINTER_SIMULATION_MODE') else 'Real'}")
    print("=" * 80)
    print("Para acceder desde otros dispositivos:")
    print(f"  1. Asegúrate de estar en la misma red")
    print(f"  2. Abre un navegador y ve a: http://{local_ip}:{port}")
    print("=" * 80)
    print("\n⚠️  NOTA: Esta es la nueva app SQLite corriendo en paralelo")
    print("   La app vieja JSON sigue en puerto 5000")
    print("   SQLite soporta múltiples lectores + 1 escritor simultáneo")
    print("\nPresiona Ctrl+C para detener el servidor")
    print("=" * 80)
    print()
    
    # Arrancar servidor
    app.run(
        host='0.0.0.0',
        port=port,
        debug=(env == 'development'),
        use_reloader=True
    )
