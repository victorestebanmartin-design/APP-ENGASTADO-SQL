"""Estado compartido en ficheros JSON, con lectura y escritura seguras.

Varios endpoints guardan estado vivo (latidos de placas, estado del
pick-to-light, PCs vistos, eventos recientes...) en ficheros JSON dentro de
``data/``. Con una sola placa eso funcionaba; con 8 carros + 10 lectores
sondeando en bucle no:

* ``open('w') + json.dump`` no es atómico -> otro hilo puede leer el fichero a
  medio escribir y ``json.load`` revienta (se traga como ``{}`` y el estado
  "parpadea").
* read-modify-write sin candado -> dos peticiones leen, las dos modifican, la
  última escritura pisa a la otra (*lost update*).

Aquí el servidor corre en un solo proceso (``waitress`` con un pool de hilos),
así que un ``threading.Lock`` por ruta serializa de verdad el acceso. La
escritura va a un temporal en el mismo directorio y se hace visible con
``os.replace`` (atómico en el mismo volumen, también en Windows).

Uso:

    from app.estado_json import cargar, guardar, actualizar

    datos = cargar(ruta, {})                 # lectura bajo candado
    guardar(ruta, datos)                     # escritura atómica bajo candado

    def _touch(d):                           # read-modify-write atómico
        d.setdefault(dev_id, {})['last_seen'] = ahora
        return d
    actualizar(ruta, {}, _touch)
"""
import json
import os
import tempfile
import threading

__all__ = ["cargar", "guardar", "actualizar", "lock_de"]

# Un RLock por ruta absoluta. RLock (reentrante) para que ``actualizar`` pueda
# reutilizar ``guardar`` sin bloquearse a sí mismo.
_locks: dict[str, "threading.RLock"] = {}
_locks_meta = threading.Lock()


def lock_de(path: str) -> "threading.RLock":
    """Devuelve (creándolo si hace falta) el candado asociado a esa ruta."""
    clave = os.path.abspath(path)
    with _locks_meta:
        lk = _locks.get(clave)
        if lk is None:
            lk = _locks[clave] = threading.RLock()
        return lk


def _leer_sin_candado(path: str, por_defecto):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        # OSError: no existe / permisos. ValueError: JSON inválido o a medias.
        return _copia(por_defecto)


def _copia(valor):
    """Copia superficial del valor por defecto para no compartir el mismo
    dict/list mutable entre llamadas."""
    if isinstance(valor, dict):
        return dict(valor)
    if isinstance(valor, list):
        return list(valor)
    return valor


def _escribir_sin_candado(path: str, datos) -> None:
    directorio = os.path.dirname(path) or "."
    os.makedirs(directorio, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directorio, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cargar(path: str, por_defecto):
    """Lee el JSON de ``path`` bajo candado. Devuelve ``por_defecto`` (copiado)
    si no existe o está corrupto -- nunca lanza."""
    with lock_de(path):
        return _leer_sin_candado(path, por_defecto)


def guardar(path: str, datos) -> None:
    """Escribe ``datos`` en ``path`` de forma atómica y bajo candado."""
    with lock_de(path):
        _escribir_sin_candado(path, datos)


def actualizar(path: str, por_defecto, fn):
    """read-modify-write atómico: lee, aplica ``fn(datos)`` y guarda, todo bajo
    el mismo candado. ``fn`` puede devolver el dato modificado o ``None`` (en
    cuyo caso se guarda el objeto que recibió, asumiendo mutación in situ).
    Devuelve lo que quedó guardado."""
    with lock_de(path):
        datos = _leer_sin_candado(path, por_defecto)
        resultado = fn(datos)
        if resultado is None:
            resultado = datos
        _escribir_sin_candado(path, resultado)
        return resultado
