"""
Configuración de la aplicación Flask con SQL Server
"""
import os
import secrets
from urllib.parse import quote_plus

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _cargar_env():
    """Carga el fichero .env (si existe) en os.environ, sin dependencias extra.

    No sobreescribe variables ya presentes en el entorno (setdefault).
    """
    env_path = os.path.join(_BASE_DIR, '.env')
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ.setdefault(key.strip(), value.strip())
    except OSError:
        pass


def _cargar_o_generar_secret_key():
    """Obtiene la SECRET_KEY real de cada instalación.

    Orden de prioridad:
      1. Variable de entorno SECRET_KEY.
      2. Fichero .secret_key junto a la app.
      3. Si no existe, GENERA una clave aleatoria, la guarda en .secret_key y la usa.

    Así cada instalación tiene su propia clave única sin tocar el código
    (importante porque este repositorio es público).
    """
    clave = os.environ.get('SECRET_KEY')
    if clave:
        return clave

    ruta = os.path.join(_BASE_DIR, '.secret_key')
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding='utf-8') as f:
                contenido = f.read().strip()
            if contenido:
                return contenido
        except OSError:
            pass

    clave = secrets.token_hex(32)
    try:
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(clave)
    except OSError:
        # Si no se puede escribir, al menos la app arranca con una clave válida
        pass
    return clave


# Cargar .env antes de leer cualquier variable de entorno en la clase Config
_cargar_env()


class Config:
    # =====================================================
    # CONFIGURACIÓN BÁSICA
    # =====================================================
    SECRET_KEY = _cargar_o_generar_secret_key()
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    # =====================================================
    # PROTECCIÓN MÓDULO ADMINISTRACIÓN (PIN)
    # =====================================================
    # Hash SHA-256 del PIN de administración. Se configura en el .env
    # (ADMIN_PIN_HASH=...). Si está vacío, la protección queda DESACTIVADA
    # y la app funciona como siempre (con un aviso en consola al arrancar).
    # Generar el hash con: python _scripts_utiles/generar_pin_hash.py
    ADMIN_PIN_HASH = os.environ.get('ADMIN_PIN_HASH', '').strip()
    # Duración de la sesión de administración (horas) antes de pedir el PIN otra vez.
    ADMIN_SESSION_HOURS = int(os.environ.get('ADMIN_SESSION_HOURS', '8'))

    # =====================================================
    # GATE DE LOGIN GLOBAL (tarjeta RFID + permisos por operario)
    # =====================================================
    # Interruptor maestro: con esto en False (por defecto), '/' y '/modules'
    # funcionan exactamente igual que siempre, sin pedir tarjeta. Se activa
    # solo cuando ya se han configurado los permisos reales de cada operario
    # desde Admin -> Operarios, para no bloquear a nadie el primer día tras
    # desplegar. También hay un interruptor visible en Admin -> Sistema que
    # sobreescribe esto en caliente sin tocar el .env.
    OPERARIO_GATE_ENABLED = os.environ.get('OPERARIO_GATE_ENABLED', 'False').lower() == 'true'

    # Rutas de directorios
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    UPLOAD_FOLDER = os.path.join(DATA_DIR, 'cortes')
    MAQUINAS_PDF_FOLDER = os.path.join(DATA_DIR, 'maquinas_pdf')
    
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
        os.makedirs(Config.MAQUINAS_PDF_FOLDER, exist_ok=True)
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
