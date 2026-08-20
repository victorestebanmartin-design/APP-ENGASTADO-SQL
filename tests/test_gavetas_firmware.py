"""El mini servidor HTTP de la placa de gavetas.

Es MicroPython, pero el troceo de la peticion es Python normal y se puede
ejecutar aqui con las dependencias de hardware simuladas. Merece la pena
porque este trozo ya fallo una vez de la peor manera: la gaveta se encendia y
aun asi el PC decia "la placa no responde", asi que ni el operario ni el log
apuntaban al sitio.
"""
import os
import sys
import types

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(BASE, 'esp32', 'lib')


@pytest.fixture(scope='module')
def gavetas():
    """Importa esp32/lib/gavetas.py con el hardware simulado."""
    machine = types.ModuleType('machine')
    machine.Pin = type('Pin', (), {'OUT': 1, 'IN': 0, '__init__': lambda s, *a, **k: None})
    machine.SoftI2C = type('SoftI2C', (), {'__init__': lambda s, *a, **k: None})
    mcp = types.ModuleType('mcp23017')
    mcp.MCP23017 = type('MCP23017', (), {'__init__': lambda s, *a, **k: None})

    previos = {n: sys.modules.get(n) for n in ('machine', 'mcp23017', 'gavetas')}
    sys.modules['machine'] = machine
    sys.modules['mcp23017'] = mcp
    sys.path.insert(0, LIB)
    try:
        sys.modules.pop('gavetas', None)
        import gavetas as modulo
        yield modulo
    finally:
        sys.path.remove(LIB)
        for nombre, previo in previos.items():
            if previo is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = previo


class SocketFalso:
    """Socket que entrega la peticion y luego se queda callado, como el de verdad.

    La clave esta en `read`: el cliente NO cierra su lado mientras espera la
    respuesta, asi que pedir mas bytes de los que hay no devuelve b'' -- se
    queda esperando. Aqui eso es una excepcion, que es justo lo que en la placa
    era un timeout de un segundo.
    """
    def __init__(self, peticion):
        self._buffer = peticion

    def readline(self):
        corte = self._buffer.find(b'\n')
        if corte < 0:
            linea, self._buffer = self._buffer, b''
            return linea
        linea = self._buffer[:corte + 1]
        self._buffer = self._buffer[corte + 1:]
        return linea

    def read(self, n):
        if n > len(self._buffer):
            raise AssertionError(
                'pidio %d bytes y solo hay %d: en la placa esto se queda '
                'esperando hasta el timeout' % (n, len(self._buffer)))
        datos, self._buffer = self._buffer[:n], self._buffer[n:]
        return datos


def _peticion(cuerpo=b'', metodo=b'POST'):
    cabecera = (metodo + b' /gaveta HTTP/1.1\r\n'
                b'Host: 192.168.50.151\r\n'
                b'Content-Type: application/json\r\n')
    if cuerpo:
        cabecera += b'Content-Length: %d\r\n' % len(cuerpo)
    return cabecera + b'\r\n' + cuerpo


def _leer(gavetas, peticion):
    return gavetas.Gavetas._leer_cuerpo(None, SocketFalso(peticion))


def test_lee_el_cuerpo_sin_pedir_mas_bytes_de_los_que_hay(gavetas):
    """El fallo original: read(1024) para una peticion de 120 bytes."""
    assert _leer(gavetas, _peticion(b'{"led": 5}')) == b'{"led": 5}'


def test_un_get_sin_cuerpo_no_se_queda_esperando(gavetas):
    """Consultar el estado desde el navegador no puede colgar el bucle."""
    assert _leer(gavetas, _peticion(metodo=b'GET')) == b''


def test_una_cabecera_partida_en_varias_lineas_no_confunde_la_longitud(gavetas):
    cuerpo = b'{"apagar": true}'
    peticion = (b'POST /gaveta HTTP/1.1\r\nHost: x\r\n'
                b'User-Agent: Python-urllib/3.11\r\n'
                b'Content-Length: %d\r\nAccept: */*\r\n\r\n' % len(cuerpo)) + cuerpo
    assert _leer(gavetas, peticion) == cuerpo


def test_content_length_mentiroso_no_deja_leer_sin_limite(gavetas):
    """Una longitud enorme no puede hacer que la placa espere indefinidamente."""
    peticion = b'POST /gaveta HTTP/1.1\r\nContent-Length: 999999\r\n\r\n' + b'x' * 512
    assert len(_leer(gavetas, peticion)) == gavetas.MAX_CUERPO


class PlacaFalsa:
    """Lo justo de una Gavetas para ver a donde va cada orden."""
    def __init__(self):
        self.encendidos = []
        self.apagados = 0

    def estado(self):
        return {'objetivo': None}

    def apagar(self):
        self.apagados += 1

    def encender(self, led):
        self.encendidos.append(led)
        return True, ''


def test_el_cuerpo_leido_acaba_encendiendo_la_gaveta(gavetas):
    """De los bytes del socket a la orden, que es el camino que se rompio."""
    placa = PlacaFalsa()
    cuerpo = gavetas.Gavetas._leer_cuerpo(placa, SocketFalso(_peticion(b'{"led": 7}')))
    respuesta = gavetas.Gavetas._responder(placa, cuerpo)
    assert placa.encendidos == [7]
    assert respuesta['ok'] is True


def test_apagar_no_enciende_nada(gavetas):
    placa = PlacaFalsa()
    cuerpo = gavetas.Gavetas._leer_cuerpo(placa, SocketFalso(_peticion(b'{"apagar": true}')))
    gavetas.Gavetas._responder(placa, cuerpo)
    assert (placa.apagados, placa.encendidos) == (1, [])


def test_un_led_que_no_es_numero_se_rechaza_con_motivo(gavetas):
    placa = PlacaFalsa()
    respuesta = gavetas.Gavetas._responder(placa, b'{"led": "tres"}')
    assert respuesta['ok'] is False
    assert respuesta['error']
    assert placa.encendidos == []
