"""
Elementos compartidos por todos los módulos de rutas: el blueprint 'main',
el acceso a la base de datos y los helpers comunes.
"""
from flask import Blueprint, jsonify, current_app
from datetime import datetime
import os

import pandas as pd

try:
    from zoneinfo import ZoneInfo
    _TZ_LOCAL = ZoneInfo('Europe/Madrid')
except Exception:
    _TZ_LOCAL = None


# Blueprint compartido: todos los módulos registran sus rutas aquí.
# El nombre 'main' se mantiene para que los url_for('main.x') no cambien.
bp = Blueprint('main', __name__)


class _DBProxy:
    """Proxy al objeto DB real, asignado en init_routes().

    Permite que los módulos hagan 'from app.routes.base import db' en el
    momento del import, antes de que la base de datos esté inicializada.
    """
    _real = None

    def __getattr__(self, name):
        if _DBProxy._real is None:
            raise RuntimeError('Base de datos no inicializada (¿falta init_routes?)')
        return getattr(_DBProxy._real, name)


db = _DBProxy()


def set_db(db_real):
    """Apunta el proxy al objeto DB real (lo llama init_routes)."""
    _DBProxy._real = db_real


# ==================== MODULOS DE LA APP (permisos por operario) ====================
#
# Fuente unica de verdad de que modulos existen: la usan las casillas de
# permisos en Admin -> Operarios, el filtrado de la rejilla de /modules y el
# gate de login (requiere_operario, en app/auth.py). 'admin' esta incluido
# para controlar si el operario ve el boton de Admin en /modules; el panel
# de administracion en si esta protegido por su propio PIN, de forma ortogonal.
MODULOS_APP = {
    'engastado':     {'label': 'Engastado',      'endpoint': 'main.index_v3'},
    'mangueras':     {'label': 'Mangueras',       'endpoint': 'main.mangueras'},
    'manguitos':     {'label': 'Manguitos',       'endpoint': 'main.manguitos'},
    'admin':         {'label': 'Administración',  'endpoint': 'main.admin'},
    'produccion':    {'label': 'Producción',      'endpoint': None},  # popup Bonos+Ordenes
    'visualizacion': {'label': 'Visualización',   'endpoint': 'main.visualizacion'},
    'etiquetas':     {'label': 'Etiquetas',       'endpoint': 'main.etiquetas'},
}


def modulos_permitidos_de(modulos_permitidos_raw):
    """Parsea operarios.modulos_permitidos (JSON en texto, o None) a un set
    de slugs. None/valor invalido -> None, que significa "sin restriccion
    explicita" y se interpreta en la UI como "todos menos Administración"
    para no conceder admin por defecto tras migraciones. Una lista vacia
    explicita ('[]') si significa "ninguno"."""
    if modulos_permitidos_raw is None:
        return None
    try:
        import json as _json
        lista = _json.loads(modulos_permitidos_raw)
        if not isinstance(lista, list):
            return None
        return {m for m in lista if m in MODULOS_APP}
    except Exception:
        return None


def _ahora_iso() -> str:
    """Hora local real (Europe/Madrid) en isoformat naive.

    El servidor (PythonAnywhere) corre en UTC; sin esto las fechas se guardaban
    2 horas por detrás. Devolvemos la hora local de España para que el report
    anote la hora real.
    """
    if _TZ_LOCAL is not None:
        return datetime.now(_TZ_LOCAL).replace(tzinfo=None).isoformat()
    return datetime.now().isoformat()


def _detectar_hoja(filepath: str) -> str:
    """Devuelve 'Format' si existe en el archivo, sino la primera hoja disponible."""
    xl = pd.ExcelFile(filepath)
    return 'Format' if 'Format' in xl.sheet_names else xl.sheet_names[0]


def allowed_file(filename):
    """Verificar si el archivo tiene una extensión permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def _ruta_upload_segura(nombre_archivo):
    """Ruta absoluta del archivo dentro de UPLOAD_FOLDER, o None si el
    nombre está vacío o intenta salirse de la carpeta (path traversal)."""
    nombre_archivo = (nombre_archivo or '').strip()
    if not nombre_archivo:
        return None
    base = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    ruta = os.path.abspath(os.path.join(base, nombre_archivo))
    if os.path.commonpath([ruta, base]) != base:
        return None
    return ruta


def _ruta_progreso_bono(nombre_bono):
    """Ruta del JSON de progreso de un bono, garantizada dentro de DATA_DIR.

    Neutraliza cualquier intento de path traversal en el nombre del bono:
    os.path.basename descarta separadores y '..', de modo que la ruta nunca
    se sale de la carpeta de datos. Siempre devuelve una ruta válida (no None),
    para que los llamadores no necesiten un guard extra.
    """
    base = os.path.abspath(current_app.config['DATA_DIR'])
    seguro = os.path.basename(f'progreso_bono_{nombre_bono or ""}.json')
    return os.path.join(base, seguro)


def _es_error_nombre_bono_duplicado(error):
    """Detectar si un IntegrityError proviene del UNIQUE de bonos.nombre"""
    mensaje = str(getattr(error, 'orig', error)).lower()
    return 'unique' in mensaje and 'bonos.nombre' in mensaje


def error_interno(e, mensaje_usuario='Error interno del servidor', status=500, clave='message'):
    """
    Maneja un error sin filtrar detalles internos al cliente.

    Genera un ID corto de error, registra el traceback completo en el log
    con ese ID, y devuelve un JSON genérico (sin str(e)) con la referencia.
    Por defecto responde 500; se puede pasar status=200 para endpoints cuyo
    JS no comprueba el código HTTP y trataría un 500 como fallo de red.
    El parámetro clave permite usar otra clave JSON (p.ej. 'error') cuando el
    consumidor lee el mensaje desde ahí en vez de 'message'.
    """
    import uuid
    error_id = uuid.uuid4().hex[:8]
    current_app.logger.exception(f"[{error_id}] {mensaje_usuario}: {e}")
    return jsonify({
        'success': False,
        clave: f'{mensaje_usuario} (ref: {error_id})'
    }), status
