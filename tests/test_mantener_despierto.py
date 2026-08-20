"""El PC servidor no puede dormirse: si se suspende, la app deja de existir.

El fallo que cubre esto no da error en ningun log: el PC de fabrica se
suspende por inactividad (nadie lo toca, solo sirve peticiones), y mientras
duerme los puestos ven "no se puede acceder a este sitio" y las placas ESP32
se quedan sin respuesta -> pitido de error tecnico. Al mover el raton vuelve
todo solo, asi que parece cosa de la red.

Aqui se comprueba lo que se puede comprobar en Linux: que la peticion a
Windows se hace con las banderas correctas, que un fallo suyo no tumba el
arranque, y que run_sql.py la llama de verdad antes de ponerse a servir.
"""
import ast
import ctypes
import os
import sys

import pytest

import mantener_despierto
from mantener_despierto import (ES_CONTINUOUS, ES_SYSTEM_REQUIRED,
                                mantener_despierto as pedir_no_dormir)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Kernel32Falso:
    """Remedo de kernel32: apunta la bandera y devuelve lo que se le diga."""

    def __init__(self, devuelve=ES_CONTINUOUS):
        self.devuelve = devuelve
        self.banderas = []

    def SetThreadExecutionState(self, banderas):
        self.banderas.append(banderas)
        if isinstance(self.devuelve, Exception):
            raise self.devuelve
        return self.devuelve


def _simular_windows(monkeypatch, kernel32):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'windll',
                        type('WinDLL', (), {'kernel32': kernel32})(),
                        raising=False)


def test_en_linux_no_hace_nada_y_lo_dice():
    """PythonAnywhere y los tests corren en Linux: ahi no hay que tocar nada."""
    aplicado, detalle = pedir_no_dormir()
    assert aplicado is False
    assert 'Windows' in detalle


def test_en_windows_pide_no_suspender_pero_deja_apagar_la_pantalla(monkeypatch):
    kernel32 = _Kernel32Falso()
    _simular_windows(monkeypatch, kernel32)

    aplicado, detalle = pedir_no_dormir()

    assert aplicado is True, detalle
    assert kernel32.banderas == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED]

    # ES_DISPLAY_REQUIRED (0x2) queda fuera a proposito: la pantalla puede
    # apagarse, eso no para el servidor, y un monitor encendido toda la noche
    # solo se gasta.
    assert not kernel32.banderas[0] & 0x00000002


@pytest.mark.parametrize('respuesta', [
    0,                                   # Windows rechaza la peticion
    OSError('kernel32 no disponible'),   # la llamada revienta
])
def test_si_windows_no_colabora_el_servidor_arranca_igual(monkeypatch, respuesta):
    """Sin siesta evitada se sirve peor, pero sin servidor no se sirve nada."""
    _simular_windows(monkeypatch, _Kernel32Falso(devuelve=respuesta))

    aplicado, detalle = pedir_no_dormir()

    assert aplicado is False
    assert detalle, 'un fallo silencioso deja la siesta sin diagnosticar'


def test_run_sql_lo_llama_antes_de_servir():
    """La peticion la guarda Windows por HILO y muere con el.

    Por eso tiene que hacerse desde el hilo principal de run_sql.py, que es el
    que se queda dentro de serve() mientras la app vive. Si alguien la mueve a
    un hilo auxiliar que termina, Windows se olvida y vuelve la siesta.
    """
    ruta = os.path.join(RAIZ, 'run_sql.py')
    with open(ruta, encoding='utf-8') as f:
        arbol = ast.parse(f.read(), filename=ruta)

    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call)
                and getattr(n.func, 'id', None) == 'mantener_despierto']
    assert llamadas, 'run_sql.py ya no evita que el PC se suspenda'

    dentro_de_funcion = {n for f in ast.walk(arbol)
                         if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                         for n in ast.walk(f)}
    assert not set(llamadas) & dentro_de_funcion, (
        'la llamada debe quedar en el hilo principal, no dentro de una funcion '
        'que pueda acabar ejecutandose en otro hilo')


def test_el_modulo_no_tiene_dependencias():
    """Como consola_utf8: se importa al arrancar, antes de comprobar nada."""
    ruta = mantener_despierto.__file__
    with open(ruta, encoding='utf-8') as f:
        arbol = ast.parse(f.read(), filename=ruta)

    modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    modulos |= {a.name.split('.')[0] for n in ast.walk(arbol)
                if isinstance(n, ast.Import) for a in n.names}
    assert modulos <= {'sys', 'ctypes'}, f'dependencias de mas: {modulos}'
