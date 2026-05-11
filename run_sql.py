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

# Verificar dependencias
try:
    import sqlalchemy
    from flask import Flask
except ImportError as e:
    print("=" * 80)
    print("❌ ERROR: Faltan dependencias")
    print("=" * 80)
    print(f"Detalle: {e}")
    print("\nPor favor ejecuta:")
    print("  python -m pip install -r requirements.txt")
    print("=" * 80)
    sys.exit(1)

from config import Config


def init_sqlite_db_file():
    """Crear archivo de base de datos SQLite si no existe"""
    db_path = Config.DB_PATH
    
    # Crear directorio data si no existe
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Si la BD no existe, crearla desde schema_sqlite.sql
    if not os.path.exists(db_path):
        print(f"Base de datos no existe, creando: {db_path}")
        schema_path = 'schema_sqlite.sql'
        
        if os.path.exists(schema_path):
            try:
                conn = sqlite3.connect(db_path)
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                conn.executescript(schema_sql)
                conn.close()
                print(f"Base de datos creada: {db_path}")
            except Exception as e:
                print(f"Error creando base de datos: {e}")
                sys.exit(1)
        else:
            print(f"No se encontro schema_sqlite.sql")
            print("   Se creara la base de datos vacia")
    else:
        print(f"Usando base de datos existente: {db_path}")


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


if __name__ == '__main__':
    # Verificar SQLite
    try:
        conn = sqlite3.connect(":memory:")
        sqlite_version = sqlite3.sqlite_version
        conn.close()
    except Exception:
        sqlite_version = "desconocida"
    
    print("=" * 80)
    print("SISTEMA DE ENGASTADO AUTOMATICO - SQLite V2.0")
    print("=" * 80)
    print(f"SQLite version: {sqlite_version}")
    print("NO requiere permisos de administrador")
    print("Soporta 4-10 usuarios concurrentes (WAL mode)")
    print("=" * 80)
    
    # Inicializar archivo de base de datos
    init_sqlite_db_file()
    
    # Crear aplicación Flask
    from app import create_app
    app = create_app(Config)
    
    # Configurar servidor
    local_ip = get_local_ip()
    port = int(os.environ.get('PORT', 5001))  # Puerto 5001 para distinguir del viejo
    
    print(f"\nServidor iniciado en:")
    print(f"   Local:      http://localhost:{port}")
    print(f"   Red local:  http://{local_ip}:{port}")
    print(f"\nEntorno: {'development' if app.debug else 'production'}")
    print(f"Base de datos: SQLite -> {Config.DB_PATH}")
    print("=" * 80)
    print("Para acceder desde otros dispositivos:")
    print(f"  1. Asegurate de estar en la misma red")
    print(f"  2. Abre un navegador y ve a: http://{local_ip}:{port}")
    print("=" * 80)
    print("\nNOTA: Esta es la nueva app SQL corriendo en PARALELO")
    print("   La app vieja JSON sigue en puerto 5000")
    print("   Esta app usa SQLite con WAL mode (multi-reader + single-writer)")
    print("\nPresiona Ctrl+C para detener el servidor")
    print("=" * 80)
    print()
    
    # Arrancar servidor
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=True
    )
