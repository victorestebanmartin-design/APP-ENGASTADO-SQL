"""Guardian de la codificacion: ningun open() de texto sin encoding.

Nace de un fallo real en planta. Los JSON de data/ se abrian asi:

    with open(fichero, 'w') as f:          # <- sin encoding
        json.dump(eventos, f, ensure_ascii=False)

Sin encoding, Python usa la del sistema. En Linux es UTF-8 y no se nota
nada; en el servidor Windows es cp1252, que no sabe escribir la flecha '→'
que llevan todos los consejos ("Admin → Operarios → Modulos permitidos").
Resultado: al registrar el rechazo de una tarjeta saltaba UnicodeEncodeError
y el operario veia "error interno del servidor" en vez de saber que su
tarjeta no tenia permiso. Costo dos rondas de diagnostico porque en
desarrollo todo iba bien.

Este test recorre el codigo con ast y falla si aparece un open() de texto
sin encoding, aunque nunca se llegue a ejecutar. Es la unica forma de que no
dependa de que alguien se acuerde.

esp32/ queda fuera a proposito: es MicroPython, y su open() no acepta
encoding (ademas de que ahi todo es ASCII).
"""
import ast
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# MicroPython (open() sin encoding), copias empaquetadas y entornos.
CARPETAS_FUERA = {'esp32', 'paquete_offline', 'micropython',
                  '.git', '__pycache__', 'venv', '.venv', 'node_modules'}


def _es_binario(llamada):
    """True si el open() es en modo binario (ahi encoding no aplica)."""
    modo = None
    if len(llamada.args) >= 2 and isinstance(llamada.args[1], ast.Constant):
        modo = llamada.args[1].value
    for kw in llamada.keywords:
        if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
            modo = kw.value.value
    return isinstance(modo, str) and 'b' in modo


def _ficheros_python():
    for base, dirs, ficheros in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in CARPETAS_FUERA]
        for nombre in ficheros:
            if nombre.endswith('.py'):
                yield os.path.join(base, nombre)


def test_ningun_open_de_texto_sin_encoding():
    culpables = []
    for ruta in _ficheros_python():
        with open(ruta, encoding='utf-8') as f:
            arbol = ast.parse(f.read(), filename=ruta)
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Name)
                    and nodo.func.id == 'open'):
                continue
            if _es_binario(nodo):
                continue
            if any(kw.arg == 'encoding' for kw in nodo.keywords):
                continue
            culpables.append('%s:%d' % (os.path.relpath(ruta, RAIZ), nodo.lineno))

    assert not culpables, (
        "open() de texto sin encoding='utf-8' (en Windows usaria cp1252 y "
        "petaria con acentos o con '→'):\n  " + '\n  '.join(culpables))
