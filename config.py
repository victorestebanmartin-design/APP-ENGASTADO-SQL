"""
Configuración de la aplicación Flask con SQL Server
"""
import os
from urllib.parse import quote_plus

class Config:
    # =====================================================
    # CONFIGURACIÓN BÁSICA
    # =====================================================
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-SQL-2026-change-in-production'
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Rutas de directorios
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    UPLOAD_FOLDER = os.path.join(DATA_DIR, 'cortes')
    
    # Configuración de uploads
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    DEFAULT_SHEET = 'Format'
    
    # =====================================================
    # CONFIGURACIÓN BASE DE DATOS - SQLite
    # =====================================================
    # NOTA: Usando SQLite en lugar de SQL Server porque no hay permisos de admin
    # SQLite soporta 4-10 usuarios concurrentes con WAL mode habilitado
    
    # Ruta de la base de datos SQLite
    DB_PATH = os.path.join(BASE_DIR, 'data', 'engastado.db')
    
    # SQLAlchemy URI para SQLite
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    
    # Configuración SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Log de queries SQL (desactivado para reducir ruido en consola)
    
    # SQLite-specific settings para mejor concurrencia
    # WAL mode se habilita en el schema_sqlite.sql
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {
            'timeout': 30,  # Timeout de 30 segundos para bloqueos
            'check_same_thread': False,  # Permitir uso desde múltiples threads
        },
        'pool_pre_ping': True,  # Verificar conexiones antes de usar
        'pool_recycle': 3600,  # Recrear conexiones cada hora
    }
    
    # =====================================================
    # CONFIGURACIÓN IMPRESORA ZEBRA
    # =====================================================
    PRINTER_ENABLED = os.environ.get('PRINTER_ENABLED', 'True').lower() == 'true'
    PRINTER_NAME = os.environ.get('PRINTER_NAME', 'ZebraGK420T')
    PRINTER_SIMULATION_MODE = os.environ.get('PRINTER_SIMULATION_MODE', 'True').lower() == 'true'
    PRINTER_SIMULATION_DIR = os.path.join(DATA_DIR, 'etiquetas_simuladas')
    PRINTER_RETRY_ATTEMPTS = int(os.environ.get('PRINTER_RETRY_ATTEMPTS', '3'))
    PRINTER_TIMEOUT = int(os.environ.get('PRINTER_TIMEOUT', '10'))
    
    # =====================================================
    # CONFIGURACIÓN ETIQUETAS
    # =====================================================
    LABELS_PER_CARRO = int(os.environ.get('LABELS_PER_CARRO', '2'))
    PRINT_ON_BONO_GENERATION = os.environ.get('PRINT_ON_BONO_GENERATION', 'True').lower() == 'true'
    PRINT_ON_CARRO_COMPLETION = os.environ.get('PRINT_ON_CARRO_COMPLETION', 'True').lower() == 'true'
    
    # =====================================================
    # CONFIGURACIÓN CARROS
    # =====================================================
    NUM_CARROS = 6
    
    # =====================================================
    # LOGGING
    # =====================================================
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.path.join(BASE_DIR, 'logs', 'app.log')
    
    @staticmethod
    def init_app(app):
        """Inicialización adicional de la app"""
        # Crear directorios necesarios
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.PRINTER_SIMULATION_DIR, exist_ok=True)
        os.makedirs(os.path.join(Config.BASE_DIR, 'logs'), exist_ok=True)


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    PRINTER_SIMULATION_MODE = False


class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    DB_NAME = 'EngastadoDB_Test'


# Diccionario de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
