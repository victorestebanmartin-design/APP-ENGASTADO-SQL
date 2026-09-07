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

    def encender(self, led, terminal=''):
        self.encendidos.append((led, terminal))
        return True, ''

    def ejecutar_test(self, datos):
        """Delega en el real: estas pruebas mandan ordenes normales, asi que
        tiene que devolver None y dejar pasar al manejo de 'led'."""
        import gavetas as modulo
        return modulo.Gavetas.ejecutar_test(self, datos)


def test_el_cuerpo_leido_acaba_encendiendo_la_gaveta(gavetas):
    """De los bytes del socket a la orden, que es el camino que se rompio."""
    placa = PlacaFalsa()
    cuerpo = gavetas.Gavetas._leer_cuerpo(placa, SocketFalso(_peticion(b'{"led": 7}')))
    respuesta = gavetas.Gavetas._responder(placa, cuerpo)
    assert placa.encendidos == [(7, '')]
    assert respuesta['ok'] is True


def test_el_terminal_llega_a_la_placa_para_el_display(gavetas):
    """Sin el, la pantalla solo puede decir un numero de cajon sin contexto."""
    placa = PlacaFalsa()
    respuesta = gavetas.Gavetas._responder(placa, b'{"led": 7, "terminal": "640204"}')
    assert placa.encendidos == [(7, '640204')]
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
        obj.terminal = ''
        obj.recogida = False
        obj.equivocadas = set()
        obj.fuera = set()
        obj._ultima_lectura_ms = 0
        obj._cambio_pendiente = {}
        obj._zumbido_hasta_ms = 0
        obj._zumbido_encendido = False
        obj._beep_hasta_ms = 0
        obj._parpadeo_hasta_ms = 0
        obj._parpadeo_encendido = True
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
    obj.terminal = ''
    obj.recogida = False
    obj.equivocadas = set()
    obj.fuera = set()
    obj._ultima_lectura_ms = 0
    obj._cambio_pendiente = {}
    obj._zumbido_hasta_ms = 0
    obj._zumbido_encendido = False
    obj._beep_hasta_ms = 0
    obj._parpadeo_hasta_ms = 0
    obj._parpadeo_encendido = True
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


def test_una_gaveta_ya_fuera_al_empezar_cuenta_como_robada(gavetas, placa_con_tira):
    """Al empezar un terminal, TODAS las demas tienen que estar en su sitio.

    Antes se tomaba una foto y lo que ya estaba fuera se daba por bueno: si
    alguien se habia llevado un cajon a otro puesto, nadie se enteraba hasta
    que el operario iba a por el a mitad del engaste.
    """
    obj, tira, expansores = placa_con_tira
    obj._avisar = lambda *a: None
    expansores[0]._bits = 0b00000100      # gaveta 3 fuera antes de empezar

    ok, _ = gavetas.Gavetas.encender(obj, 5, '640204')

    assert ok is True
    assert obj.equivocadas == {3}
    assert obj.terminal == '640204'
    assert tira[4] == gavetas.COLOR_OBJETIVO   # la 5 sigue pidiendose en verde


def test_el_rojo_de_la_gaveta_robada_parpadea(gavetas, placa_con_tira, monkeypatch):
    """Un rojo fijo se deja de mirar; el que parpadea, no."""
    obj, tira, _ = placa_con_tira
    # CPython no trae los ticks_* de MicroPython; en un contador que no
    # desborda son una resta y una suma normales.
    reloj = types.ModuleType('time')
    reloj.ticks_diff = lambda a, b: a - b
    reloj.ticks_add = lambda a, b: a + b
    monkeypatch.setattr(gavetas, 'time', reloj)

    obj.equivocadas = {3}
    obj._parpadeo_hasta_ms = 0
    obj._parpadeo_encendido = True

    gavetas.Gavetas._atender_parpadeo(obj, 10_000)
    assert tira[2] == gavetas.COLOR_APAGADO

    obj._parpadeo_hasta_ms = 0
    gavetas.Gavetas._atender_parpadeo(obj, 20_000)
    assert tira[2] == gavetas.COLOR_ERROR


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


# ── Apertura del puerto 80 ────────────────────────────────────────────────
#
# Una placa puede detectar sus expansores, encender gavetas y mandar latidos
# con el puerto 80 cerrado: desde Admin se ve sana y el unico sintoma es un
# ConnectionRefusedError al empujarle una orden. Estos dos tests fijan lo que
# costo encontrar ese fallo.

class _SocketEspia:
    """Socket de mentira que apunta como lo han llamado."""

    def __init__(self, registro, fallar_en=None):
        self._registro = registro
        self._fallar_en = fallar_en
        self.cerrado = False

    def _paso(self, nombre, *args):
        self._registro.append((nombre, args))
        if self._fallar_en == nombre:
            raise OSError(112, 'EADDRINUSE')

    def setsockopt(self, *a):
        self._paso('setsockopt')

    def bind(self, direccion):
        self._paso('bind', direccion)

    def listen(self, n):
        self._paso('listen')

    def settimeout(self, t):
        self._paso('settimeout')

    def close(self):
        self.cerrado = True


def _con_socket_falso(gavetas, monkeypatch, fallar_en=None):
    """Sustituye el modulo socket de gavetas.py y devuelve (registro, sockets)."""
    registro = []
    creados = []

    def socket_falso():
        s = _SocketEspia(registro, fallar_en)
        creados.append(s)
        return s

    def getaddrinfo(host, port, *a):
        registro.append(('getaddrinfo', (host, port)))
        # Se devuelve un valor DISTINTO de la tupla cruda a proposito: asi el
        # test puede distinguir un bind(getaddrinfo(...)) de un bind(("0.0.0.0",
        # 80)), que es justo el fallo que se esta fijando.
        return [(2, 1, 0, '', RESUELTA)]

    falso = types.SimpleNamespace(
        socket=socket_falso,
        SOCK_STREAM=1,
        SOL_SOCKET=1,
        SO_REUSEADDR=2,
        getaddrinfo=getaddrinfo,
    )
    monkeypatch.setattr(gavetas, 'socket', falso)
    return registro, creados


# Lo que "resuelve" el getaddrinfo de mentira: no se parece a la tupla cruda.
RESUELTA = ('0.0.0.0-resuelta', 80)


def test_el_puerto_80_se_abre_con_la_direccion_de_getaddrinfo(gavetas, monkeypatch):
    """bind() tiene que recibir lo que devuelve getaddrinfo, no una tupla cruda.

    En MicroPython no son equivalentes: con la tupla cruda el bind puede
    fallar en silencio y dejar la placa sin escuchar a nadie.
    """
    registro, _ = _con_socket_falso(gavetas, monkeypatch)
    placa = types.SimpleNamespace()

    servidor = gavetas.Gavetas._abrir_servidor(placa)

    assert servidor is not None
    pasos = dict(registro)
    assert pasos.get('getaddrinfo') == ('0.0.0.0', gavetas.PUERTO_HTTP)
    assert pasos.get('bind') == (RESUELTA,), 'bind no uso la direccion resuelta'
    nombres = [n for n, _ in registro]
    assert nombres.index('listen') < nombres.index('settimeout')


def test_si_el_bind_falla_el_socket_se_cierra(gavetas, monkeypatch):
    """Sin cerrarlo, cada reintento dejaria un descriptor colgado."""
    _, creados = _con_socket_falso(gavetas, monkeypatch, fallar_en='bind')
    placa = types.SimpleNamespace()

    assert gavetas.Gavetas._abrir_servidor(placa) is None
    assert creados and creados[0].cerrado, 'el socket fallido quedo sin cerrar'
