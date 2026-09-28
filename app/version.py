"""Version semantica de la app (X.Y.Z), leida de VERSION en la raiz.

No se calcula sola: subirla es una decision humana en cada commit que
merezca subirla -- patch para un cambio normal, minor para algo gordo, major
para algo gordisimo (ver CLAUDE.md). Vive en un fichero de texto suelto, no
en config.py, para que se pueda leer la version remota con
`git show origin/main:VERSION` sin tener que importar codigo Python (ver
app/routes/sistema.py:api_comprobar_actualizaciones).
"""
import os

_RUTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'VERSION')

_cache = '?'
_cache_mtime = None


def actual():
    """Version local, cacheada por mtime del fichero. '?' si no existe o falla."""
    global _cache, _cache_mtime
    try:
        mtime = os.path.getmtime(_RUTA)
    except OSError:
        return '?'
    if mtime != _cache_mtime:
        try:
            with open(_RUTA, 'r', encoding='utf-8') as f:
                _cache = f.read().strip() or '?'
            _cache_mtime = mtime
        except OSError:
            pass
    return _cache
