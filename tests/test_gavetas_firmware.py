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
    mcp.CANALES = 16
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


# ── Tests del modo prueba de cableado ────────────────────────────────────────

class TiraFalsa:
    """Simula un objeto NeoPixel: lista indexable + write()."""
    def __init__(self, n):
        self._pixeles = [(0, 0, 0)] * n
        self.escrituras = 0

    def __setitem__(self, i, color):
        self._pixeles[i] = color

    def __getitem__(self, i):
        return self._pixeles[i]

    def write(self):
        self.escrituras += 1

    def __len__(self):
        return len(self._pixeles)


class PlacaConTira:
    """Placa con tira y expansores simulados para los tests de modo prueba."""

    def __init__(self, n_gavetas=8):
        import types

        class ExpFalso:
            def __init__(self, bits=0):
                self._bits = bits
                self.direccion = 0x20

            def leer(self):
                return self._bits

        mcp_mod = types.ModuleType('mcp23017')
        mcp_mod.CANALES = 16
        mcp_mod.MCP23017 = ExpFalso

        n_exp = (n_gavetas + 15) // 16
        expansores = [ExpFalso(bits=0) for _ in range(n_exp)]
        tira = TiraFalsa(n_gavetas)
        buzzer = type('Buz', (), {'on': lambda s: None, 'off': lambda s: None})()

        import sys
        previo_mcp = sys.modules.get('mcp23017')
        sys.modules['mcp23017'] = mcp_mod
        try:
            import gavetas as gmod
        finally:
            if previo_mcp is None:
                sys.modules.pop('mcp23017', None)
            else:
                sys.modules['mcp23017'] = previo_mcp

        # Construir la instancia a mano sin pasar por crear()
        obj = object.__new__(gmod.Gavetas)
        obj.expansores = expansores
        obj.tira = tira
        obj.buzzer = buzzer
        obj.device_id = 'test'
        obj.n_gavetas = n_gavetas
        obj.objetivo = None
        obj.recogida = False
        obj.equivocadas = set()
        obj.fuera = set()
        obj._ultima_lectura_ms = 0
        obj._cambio_pendiente = {}
        obj._zumbido_hasta_ms = 0
        obj._zumbido_encendido = False
        obj._beep_hasta_ms = 0
        obj._en_prueba = False
        obj._servidor = None
        self.obj = obj
        self.tira = tira
        self.expansores = expansores

    def responder(self, cuerpo):
        import gavetas as gmod
        return gmod.Gavetas._responder(self.obj, cuerpo)

    def aplicar_cambio(self, gaveta, ahora_fuera):
        import gavetas as gmod
        return gmod.Gavetas._aplicar_cambio(self.obj, gaveta, ahora_fuera)


@pytest.fixture
def placa_con_tira(gavetas):
    """Placa con 8 gavetas y tira simulada, importando el modulo ya cargado."""
    import types

    mcp_mod = types.ModuleType('mcp23017')
    mcp_mod.CANALES = 16

    class ExpFalso:
        def __init__(self):
            self._bits = 0
            self.direccion = 0x20

        def leer(self):
            return self._bits

    n = 8
    expansores = [ExpFalso()]
    tira = TiraFalsa(n)
    buzzer = type('Buz', (), {'on': lambda s: None, 'off': lambda s: None})()

    obj = object.__new__(gavetas.Gavetas)
    obj.expansores = expansores
    obj.tira = tira
    obj.buzzer = buzzer
    obj.device_id = 'test'
    obj.n_gavetas = n
    obj.objetivo = None
    obj.recogida = False
    obj.equivocadas = set()
    obj.fuera = set()
    obj._ultima_lectura_ms = 0
    obj._cambio_pendiente = {}
    obj._zumbido_hasta_ms = 0
    obj._zumbido_encendido = False
    obj._beep_hasta_ms = 0
    obj._en_prueba = False
    obj._servidor = None

    return obj, tira, expansores


def test_test_led_enciende_solo_ese_pixel(gavetas, placa_con_tira):
    obj, tira, _ = placa_con_tira
    resp = gavetas.Gavetas._responder(obj, b'{"test_led": 3, "color": [100, 0, 0]}')
    assert resp['ok'] is True
    assert resp['test_led'] == 3
    assert tira[2] == (100, 0, 0)       # pixel 3 encendido (0-based)
    assert tira[0] == (0, 0, 0)         # resto apagados
    assert tira[7] == (0, 0, 0)
    assert tira.escrituras >= 1


def test_test_led_apaga_el_resto(gavetas, placa_con_tira):
    obj, tira, _ = placa_con_tira
    # Encendemos el 5 primero
    gavetas.Gavetas._responder(obj, b'{"test_led": 5, "color": [0, 100, 0]}')
    # Luego el 2: el 5 debe apagarse
    gavetas.Gavetas._responder(obj, b'{"test_led": 2, "color": [0, 100, 0]}')
    assert tira[1] == (0, 100, 0)
    assert tira[4] == (0, 0, 0)


def test_test_led_fuera_de_rango_devuelve_error(gavetas, placa_con_tira):
    obj, _, _ = placa_con_tira
    resp = gavetas.Gavetas._responder(obj, b'{"test_led": 99}')
    assert resp['ok'] is False
    assert 'rango' in resp['error']


def test_test_led_activa_modo_prueba(gavetas, placa_con_tira):
    obj, _, _ = placa_con_tira
    obj.objetivo = 3   # habia un objetivo activo
    gavetas.Gavetas._responder(obj, b'{"test_led": 1}')
    assert obj._en_prueba is True
    assert obj.objetivo is None   # lo limpia al entrar en prueba


def test_test_todos_enciende_n_gavetas(gavetas, placa_con_tira):
    obj, tira, _ = placa_con_tira
    resp = gavetas.Gavetas._responder(obj, b'{"test_todos": true, "color": [60, 60, 60]}')
    assert resp['ok'] is True
    assert resp['gavetas'] == 8
    for i in range(8):
        assert tira[i] == (60, 60, 60)


def test_test_micros_devuelve_fuera_y_puestas(gavetas, placa_con_tira):
    obj, _, expansores = placa_con_tira
    # Simulamos gaveta 1 y 3 fuera (bits 0 y 2 a 1)
    expansores[0]._bits = 0b00000101
    obj.fuera = set()
    resp = gavetas.Gavetas._responder(obj, b'{"test_micros": true}')
    assert resp['ok'] is True
    assert 1 in resp['fuera']
    assert 3 in resp['fuera']
    assert 2 not in resp['fuera']
    assert resp['total'] == 8


def test_test_fin_sale_del_modo_prueba_y_apaga(gavetas, placa_con_tira):
    obj, tira, _ = placa_con_tira
    # Entrar en prueba
    gavetas.Gavetas._responder(obj, b'{"test_led": 4, "color": [0, 0, 100]}')
    assert obj._en_prueba is True
    # Salir
    resp = gavetas.Gavetas._responder(obj, b'{"test_fin": true}')
    assert resp['ok'] is True
    assert obj._en_prueba is False
    assert all(tira[i] == (0, 0, 0) for i in range(8))


def test_en_modo_prueba_cambio_micro_no_toca_los_leds(gavetas, placa_con_tira):
    obj, tira, _ = placa_con_tira
    # Encender LED 5 en modo prueba
    gavetas.Gavetas._responder(obj, b'{"test_led": 5, "color": [0, 0, 100]}')
    color_antes = tira[4]
    assert color_antes == (0, 0, 100)
    # Simular que se abre el micro de la gaveta 2
    gavetas.Gavetas._aplicar_cambio(obj, 2, True)
    # El LED 5 no debe haberse tocado
    assert tira[4] == (0, 0, 100)
    # Y el buzzer tampoco debe haber sonado (obj.equivocadas vacio porque _iniciar_prueba lo limpia)
    assert not obj.equivocadas
