"""
Configuración de la aplicación Flask con SQL Server
"""
import os
import secrets
import time
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


def _leer_secret_key(ruta):
    """Lee una clave ya publicada sin hacer depender la lectura de ``chmod``."""
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        # En Windows o en volúmenes compartidos chmod puede no estar disponible,
        # pero una clave legible sigue siendo preferible a generar otra distinta.
        pass
    try:
        with open(ruta, encoding='utf-8') as f:
            return f.read().strip() or None
    except OSError:
        return None


_SECRET_KEY_LOCK_TIMEOUT_S = 10.0
_SECRET_KEY_WAIT_TIMEOUT_S = 10.0
_SECRET_KEY_POLL_S = 0.01


def _adquirir_candado_secret_key(candado):
    """Devuelve True si este proceso gana el candado (crea el directorio).

    ``os.mkdir`` es una operación de creación exclusiva atómica tanto en
    POSIX como en Windows: si dos procesos la llaman a la vez con el mismo
    nombre, exactamente uno tiene éxito. Es el mismo principio que ``O_EXCL``
    pero sin depender de enlaces duros (``os.link``), que en Windows solo
    funcionan en volúmenes NTFS y no en todos los sistemas de archivos donde
    puede vivir esta carpeta.

    Si el candado ya existe pero es más viejo que el tiempo máximo que puede
    tardar en escribirse la clave, se considera abandonado (el proceso que lo
    creó murió entre el ``mkdir`` y el ``rmdir`` final) y se intenta liberar
    para no dejar a los demás procesos esperando para siempre.
    """
    try:
        os.mkdir(candado)
        return True
    except FileExistsError:
        try:
            antiguedad = time.time() - os.path.getmtime(candado)
        except OSError:
            return False
        if antiguedad > _SECRET_KEY_LOCK_TIMEOUT_S:
            try:
                os.rmdir(candado)
            except OSError:
                pass
        return False
    except OSError:
        return False


def _cargar_o_generar_secret_key():
    """Obtiene la SECRET_KEY real de cada instalación.

    Orden de prioridad:
      1. Variable de entorno SECRET_KEY.
      2. Fichero .secret_key junto a la app.
      3. Si no existe (o está vacío, herencia de una versión anterior que se
         cerró a medio escribir), GENERA una clave aleatoria, la guarda en
         .secret_key y la usa.

    Así cada instalación tiene su propia clave única sin tocar el código
    (importante porque este repositorio es público).

    Varios procesos (workers de Gunicorn, o dos arranques simultáneos) pueden
    llegar aquí a la vez. Deben terminar todos con la MISMA clave: si cada uno
    generase la suya, las cookies de sesión firmadas por un worker no
    validarían en otro y las sesiones fallarían de forma intermitente según
    qué worker atendiera cada petición.
    """
    clave = os.environ.get('SECRET_KEY')
    if clave:
        return clave

    ruta = os.path.join(_BASE_DIR, '.secret_key')

    contenido = _leer_secret_key(ruta) if os.path.exists(ruta) else None
    if contenido:
        return contenido

    # No hay clave publicada (o el fichero está vacío/ausente): solo un
    # proceso debe generarla y escribirla. El candado es un directorio
    # (``.secret_key.lock``), no el propio fichero, así que nunca hay que
    # borrar ni sobrescribir a ciegas algo que otro proceso pueda haber
    # publicado ya.
    candado = ruta + '.lock'
    if _adquirir_candado_secret_key(candado):
        try:
            # Releer con el candado en la mano: otro proceso pudo publicar la
            # clave entre nuestra primera lectura (sin candado) y ahora.
            contenido = _leer_secret_key(ruta) if os.path.exists(ruta) else None
            if contenido:
                return contenido

            clave = secrets.token_hex(32)
            temporal = f'{ruta}.{os.getpid()}.{secrets.token_hex(8)}.tmp'
            try:
                fd = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        f.write(clave)
                        f.flush()
                        os.fsync(f.fileno())
                    # os.replace es atómico tanto en POSIX como en Windows (a
                    # diferencia de os.rename, que en Windows falla si el
                    # destino ya existe): ningún proceso puede observar un
                    # .secret_key a medio escribir, y no hace falta borrar el
                    # fichero anterior (vacío o no) antes de publicar el nuevo.
                    os.replace(temporal, ruta)
                except BaseException:
                    try:
                        os.unlink(temporal)
                    except FileNotFoundError:
                        pass
                    raise
                return clave
            except OSError as exc:
                raise RuntimeError(
                    'No se puede persistir una SECRET_KEY compartida en '
                    f'{ruta!r}'
                ) from exc
        finally:
            try:
                os.rmdir(candado)
            except OSError:
                pass

    # Otro proceso tiene el candado: esperar a que publique la clave en vez
    # de arrancar con una clave transitoria propia que dejaría las sesiones
    # incoherentes entre procesos.
    limite = time.time() + _SECRET_KEY_WAIT_TIMEOUT_S
    while time.time() < limite:
        contenido = _leer_secret_key(ruta) if os.path.exists(ruta) else None
        if contenido:
            return contenido
        time.sleep(_SECRET_KEY_POLL_S)

    raise RuntimeError(
        'No se pudo obtener la SECRET_KEY compartida: otro proceso tiene el '
        'candado de generación y no ha publicado la clave a tiempo'
    )


# Cargar .env antes de leer cualquier variable de entorno en la clase Config
_cargar_env()


class Config:
    # =====================================================
    # CONFIGURACIÓN BÁSICA
    # =====================================================
    SECRET_KEY = _cargar_o_generar_secret_key()
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Activar en despliegues servidos exclusivamente por HTTPS. Se mantiene
    # configurable porque los puestos de fábrica acceden por HTTP en la LAN.
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'

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
    # Cada petición que pase de esto se registra como 'LENTA' en el log
    # (ver app/observabilidad.py). La carga por endpoint se ve en
    # GET /api/sistema/carga (solo admin).
    SLOW_REQUEST_MS = int(os.environ.get('SLOW_REQUEST_MS', '1000'))

    # =====================================================
    # COPIA DE SEGURIDAD AUTOMÁTICA (app/backup_auto.py)
    # =====================================================
    # Cada cuántas horas se copia data/ a data/backups_auto/. 0 = desactivada.
    AUTO_BACKUP_HORAS = os.environ.get('AUTO_BACKUP_HORAS', '6')
    AUTO_BACKUP_RETENER = int(os.environ.get('AUTO_BACKUP_RETENER', '20'))
    
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


# Diccionario de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
