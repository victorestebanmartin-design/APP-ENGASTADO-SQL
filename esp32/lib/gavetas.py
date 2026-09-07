# gavetas.py -- Pick-to-light de gavetas para la placa lectora RFID.
#
# Enciende el LED de la gaveta que el operario acaba de elegir en engastado y
# vigila los micro-interruptores que dicen si cada gaveta esta puesta o fuera.
# El esquema electrico esta en esp32/HARDWARE_PICK_TO_LIGHT.md.
#
# Dos ideas gobiernan este fichero:
#
# 1. ES OPCIONAL. Si no hay expansores en el bus I2C, crear() devuelve None y
#    la placa se comporta exactamente como antes. La misma version de firmware
#    vale para los lectores que llevan gavetas y para los que no, sin
#    configurar nada por placa (igual que el lector NFC opcional del carro).
#
# 2. NADA BLOQUEA. actualizar() se llama desde el bucle principal, que tambien
#    lee tarjetas: ni un sleep largo, ni un accept() que espere. El zumbido de
#    "gaveta equivocada" es una maquina de estados, no un bucle de pitidos.
#
# Quien decide si la gaveta es la correcta es ESTA placa, no el servidor: el
# operario ya tiene la mano en el cajon y no puede esperar a un ida y vuelta.

import socket
import time

from machine import Pin, SoftI2C

import mcp23017

try:
    import neopixel
except ImportError:      # firmware de MicroPython sin el modulo
    neopixel = None

try:
    import http_client
    import backend_config as backend_cfg
except ImportError:      # sin red no se avisa al servidor, pero las luces van
    http_client = None
    backend_cfg = None

EVENTO_PATH = "/api/esp32/rfid/gaveta"

# Pines por defecto. Se pueden cambiar en wifi_config.py, pero van con getattr
# para que las placas ya instaladas cojan el OTA sin visita con cable USB.
LED_PIN_DEF = 13
SDA_PIN_DEF = 21
SCL_PIN_DEF = 26

# Colores ya atenuados: un WS2813 a tope deslumbra a medio metro y se come
# 60 mA por pixel. Con estos valores un puesto entero encendido no llega a 1 A.
COLOR_OBJETIVO = (0, 70, 0)     # verde: la gaveta a la que hay que ir
COLOR_EN_USO   = (0, 0, 90)     # azul: sacada y en uso
COLOR_ERROR    = (110, 0, 0)    # rojo: esta no era
COLOR_APAGADO  = (0, 0, 0)

PUERTO_HTTP = 80
REINTENTO_SERVIDOR_MS = 5000  # cada cuanto se reintenta abrir el puerto 80
TIMEOUT_PETICION_S = 1      # leer la peticion ya recibida es cosa de ms
MAX_CUERPO = 512            # el JSON que manda el PC son unos 30 bytes
INTERVALO_MICROS_MS = 40    # cada cuanto se relee el bus I2C
ANTIRREBOTE_MS = 80         # un micro rebota unos ms al abrir y al cerrar
BEEP_OK_MS = 120            # confirmacion corta de recogida correcta
# Alarma de gaveta robada: corta y rapida molesta mucho mas que un pitido
# largo, y es la unica forma de que alguien suelte el cajon y lo devuelva.
ZUMBIDO_ON_MS = 120
ZUMBIDO_OFF_MS = 90
PARPADEO_MS = 250           # el rojo de la gaveta robada parpadea, no fijo
TIMEOUT_AVISO_S = 2         # avisar al servidor no puede frenar el bucle


class Gavetas:
    def __init__(self, expansores, tira, buzzer, device_id):
        self.expansores = expansores
        self.tira = tira
        self.buzzer = buzzer
        self.device_id = device_id
        self.n_gavetas = mcp23017.CANALES * len(expansores)

        self.objetivo = None        # numero de gaveta que hay que abrir
        self.terminal = ""          # terminal en curso, solo para el display
        self.recogida = False       # ya se abrio la correcta
        self.equivocadas = set()    # gavetas mal abiertas y aun sin devolver
        # Numeros de LED con un terminal de verdad detras, segun el servidor.
        # None = sin lista todavia (firmware recien arrancado o servidor
        # viejo): no se restringe nada, que es como se comportaba siempre.
        self.validas = None

        self.fuera = self._leer_micros()   # foto inicial: lo que ya estaba fuera
        self._ultima_lectura_ms = time.ticks_ms()
        self._cambio_pendiente = {}        # gaveta -> ticks del primer cambio

        self._zumbido_hasta_ms = 0
        self._zumbido_encendido = False
        self._beep_hasta_ms = 0
        self._parpadeo_hasta_ms = 0
        self._parpadeo_encendido = True

        self._en_prueba = False   # modo prueba de cableado
        self._reintento_servidor_ms = 0

        self._servidor = self._abrir_servidor()
        self._apagar_tira()
        # Un aviso de arranque para que Admin -> Lectores RFID sepa cuantas
        # gavetas tiene esta placa sin esperar a que alguien abra un cajon.
        self._avisar(0, False, "arranque")

    # ── Hardware ────────────────────────────────────────────────────────────

    def _leer_micros(self):
        """Conjunto de gavetas (1..N) que estan FUERA ahora mismo."""
        fuera = set()
        for indice, exp in enumerate(self.expansores):
            try:
                bits = exp.leer()
            except Exception as e:
                # Un expansor que no contesta no puede tumbar a los demas ni
                # inventarse que le han sacado las 16 gavetas de golpe.
                print("Gavetas: expansor 0x%02X no responde:" % exp.direccion, e)
                continue
            base = indice * mcp23017.CANALES
            for canal in range(mcp23017.CANALES):
                if bits & (1 << canal):     # 1 = contacto abierto = gaveta fuera
                    fuera.add(base + canal + 1)
        return fuera

    def _pintar(self, gaveta, color):
        if self.tira is None or not 1 <= gaveta <= self.n_gavetas:
            return
        self.tira[gaveta - 1] = color
        self.tira.write()

    def _apagar_tira(self):
        if self.tira is None:
            return
        for i in range(self.n_gavetas):
            self.tira[i] = COLOR_APAGADO
        self.tira.write()

    # ── Ordenes que llegan del servidor ─────────────────────────────────────

    def encender(self, gaveta, terminal="", validas=None):
        """Marca una gaveta como objetivo y la pone en verde.

        'validas' es la lista de LEDs con un terminal de verdad detras en
        este puesto, segun el servidor; None deja la lista que ya hubiera
        (no todos los caminos que llaman a encender la conocen). El objetivo
        siempre cuenta como valida, aunque el servidor no la incluyera.
        """
        if not 1 <= gaveta <= self.n_gavetas:
            return False, "La gaveta %d no existe (esta placa tiene %d)" % (
                gaveta, self.n_gavetas)
        self.apagar()
        self.objetivo = gaveta
        self.terminal = terminal or ""
        if validas is not None:
            self.validas = set(validas)
            self.validas.add(gaveta)
        self.recogida = False
        self.fuera = self._leer_micros()
        # Al empezar un terminal, TODAS las demas gavetas del puesto tienen
        # que estar en su sitio. Una que ya estaba fuera es tan intrusa como
        # una que se saque despues: alguien se la ha llevado y el operario de
        # este puesto se quedaria sin ella a mitad del engaste. Un canal sin
        # gaveta configurada (sin microinterruptor cableado, o un hueco
        # vacio del armario) no cuenta: es ruido del expansor, no un robo.
        for otra in self.fuera:
            if otra != gaveta and self._es_gaveta_real(otra):
                self.equivocadas.add(otra)
                self._avisar(otra, True, "equivocada")
        self._pintar(gaveta, COLOR_EN_USO if gaveta in self.fuera else COLOR_OBJETIVO)
        if gaveta in self.fuera:
            self.recogida = True
        return True, ""

    def _es_gaveta_real(self, gaveta):
        """True si este canal tiene una gaveta configurada en este puesto.

        Sin lista (self.validas is None) no se restringe nada: es como se
        comportaba siempre, para una placa recien arrancada o un servidor
        viejo que aun no manda la lista.
        """
        return self.validas is None or gaveta in self.validas

    def apagar(self):
        """Todo apagado y sin objetivo: la placa vuelve a estar en reposo."""
        self.objetivo = None
        self.terminal = ""
        self.recogida = False
        self.equivocadas.clear()
        self._parar_zumbido()
        self._apagar_tira()

    def estado(self):
        return {
            "expansores": len(self.expansores),
            "gavetas": self.n_gavetas,
            "objetivo": self.objetivo,
            "terminal": self.terminal,
            "recogida": self.recogida,
            "equivocadas": sorted(self.equivocadas),
            "fuera": sorted(self.fuera),
            "validas": sorted(self.validas) if self.validas is not None else None,
            "http": self._servidor is not None,
        }

    # ── Zumbador (sin bloquear el bucle) ────────────────────────────────────

    def _parar_zumbido(self):
        self._zumbido_hasta_ms = 0
        self._zumbido_encendido = False
        self._beep_hasta_ms = 0
        self._parpadeo_hasta_ms = 0
        self._parpadeo_encendido = True
        try:
            self.buzzer.off()
        except Exception:
            pass

    def _iniciar_prueba(self):
        """Entra en modo prueba: pausa la logica normal para verificar el cableado."""
        self.objetivo = None
        self.recogida = False
        self.equivocadas.clear()
        self._parar_zumbido()
        self._en_prueba = True

    def _finalizar_prueba(self):
        self._en_prueba = False

    def ejecutar_test(self, datos):
        """Ejecuta un comando de prueba de cableado. None si no lo era.

        Publico a proposito: los mismos comandos llegan por dos caminos. En la
        red de planta el servidor los empuja al puerto 80; desde
        PythonAnywhere no puede (la placa esta en una IP privada) y los recoge
        el sondeo de main. La logica tiene que ser la misma por los dos lados.
        """
        test_led = datos.get("test_led")
        if test_led is not None:
            try:
                test_led = int(test_led)
            except (TypeError, ValueError):
                return {"ok": False, "error": "test_led no es un numero"}
            color = _color(datos.get("color"), (180, 180, 180))
            self._iniciar_prueba()
            if self.tira is None:
                return {"ok": False, "error": "Sin tira LED", "estado": self.estado()}
            if not 1 <= test_led <= self.n_gavetas:
                return {"ok": False,
                        "error": "LED %d fuera de rango (1-%d)" % (test_led, self.n_gavetas),
                        "estado": self.estado()}
            for i in range(self.n_gavetas):
                self.tira[i] = COLOR_APAGADO
            self.tira[test_led - 1] = color
            self.tira.write()
            return {"ok": True, "test_led": test_led, "color": list(color),
                    "estado": self.estado()}

        if datos.get("test_todos"):
            color = _color(datos.get("color"), (60, 60, 60))
            self._iniciar_prueba()
            if self.tira:
                for i in range(self.n_gavetas):
                    self.tira[i] = color
                self.tira.write()
            return {"ok": True, "gavetas": self.n_gavetas, "color": list(color),
                    "estado": self.estado()}

        if datos.get("test_micros"):
            leidas = self._leer_micros()
            puestas = sorted(g for g in range(1, self.n_gavetas + 1) if g not in leidas)
            return {"ok": True, "fuera": sorted(leidas), "puestas": puestas,
                    "total": self.n_gavetas, "estado": self.estado()}

        if datos.get("test_fin"):
            self._finalizar_prueba()
            self.apagar()
            return {"ok": True, "estado": self.estado()}

        return None

    def _beep_ok(self):
        self._beep_hasta_ms = time.ticks_add(time.ticks_ms(), BEEP_OK_MS)
        self.buzzer.on()

    def _atender_zumbador(self, ahora):
        # El beep corto de confirmacion manda sobre el zumbido de error: si
        # suenan a la vez, lo que el operario necesita oir es el "correcta".
        if self._beep_hasta_ms:
            if time.ticks_diff(ahora, self._beep_hasta_ms) >= 0:
                self._beep_hasta_ms = 0
                self.buzzer.off()
            return

        if not self.equivocadas:
            if self._zumbido_encendido:
                self._zumbido_encendido = False
                self.buzzer.off()
            return

        if time.ticks_diff(ahora, self._zumbido_hasta_ms) < 0:
            return
        self._zumbido_encendido = not self._zumbido_encendido
        if self._zumbido_encendido:
            self.buzzer.on()
            self._zumbido_hasta_ms = time.ticks_add(ahora, ZUMBIDO_ON_MS)
        else:
            self.buzzer.off()
            self._zumbido_hasta_ms = time.ticks_add(ahora, ZUMBIDO_OFF_MS)

    # ── Micro-interruptores ─────────────────────────────────────────────────

    def _atender_parpadeo(self, ahora):
        """El rojo de una gaveta robada parpadea: un fijo se deja de mirar."""
        if not self.equivocadas or self.tira is None:
            return
        if time.ticks_diff(ahora, self._parpadeo_hasta_ms) < 0:
            return
        self._parpadeo_hasta_ms = time.ticks_add(ahora, PARPADEO_MS)
        self._parpadeo_encendido = not self._parpadeo_encendido
        color = COLOR_ERROR if self._parpadeo_encendido else COLOR_APAGADO
        for gaveta in self.equivocadas:
            if 1 <= gaveta <= self.n_gavetas:
                self.tira[gaveta - 1] = color
        self.tira.write()

    def _atender_micros(self, ahora):
        if time.ticks_diff(ahora, self._ultima_lectura_ms) < INTERVALO_MICROS_MS:
            return
        self._ultima_lectura_ms = ahora

        leidas = self._leer_micros()

        # Antirrebote: un cambio solo cuenta si se mantiene ANTIRREBOTE_MS.
        for gaveta in set(leidas) ^ set(self.fuera):
            desde = self._cambio_pendiente.get(gaveta)
            if desde is None:
                self._cambio_pendiente[gaveta] = ahora
            elif time.ticks_diff(ahora, desde) >= ANTIRREBOTE_MS:
                del self._cambio_pendiente[gaveta]
                self._aplicar_cambio(gaveta, gaveta in leidas)
        # Un cambio que se deshizo solo (rebote) deja de estar pendiente
        for gaveta in list(self._cambio_pendiente):
            if (gaveta in leidas) == (gaveta in self.fuera):
                del self._cambio_pendiente[gaveta]

    def _aplicar_cambio(self, gaveta, ahora_fuera):
        if ahora_fuera:
            self.fuera.add(gaveta)
        else:
            self.fuera.discard(gaveta)

        if self._en_prueba:
            # En modo prueba solo se actualiza el estado; sin luces ni zumbido.
            return

        if gaveta == self.objetivo:
            if ahora_fuera:
                self.recogida = True
                self._pintar(gaveta, COLOR_EN_USO)
                self._beep_ok()
                self._avisar(gaveta, True, "ok")
            else:
                # Devolver la gaveta buena no apaga la luz: sigue siendo la del
                # trabajo en curso hasta que el servidor diga que se acabo.
                self._avisar(gaveta, False, "devuelta")
            return

        if not self._es_gaveta_real(gaveta):
            # Canal sin gaveta configurada en este puesto: sin microinterruptor
            # cableado o un hueco vacio del armario. Es ruido del expansor, no
            # una gaveta robada, y no debe avisar ni sonar por ella.
            return

        # Sin objetivo no hay ni acierto ni error: alguien esta reponiendo o
        # dejo un cajon abierto. Se avisa al servidor y no suena nada.
        if self.objetivo is None:
            self._avisar(gaveta, ahora_fuera, "sin_objetivo")
            return

        if ahora_fuera:
            self.equivocadas.add(gaveta)
            self._pintar(gaveta, COLOR_ERROR)
            self._avisar(gaveta, True, "equivocada")
        else:
            self.equivocadas.discard(gaveta)
            self._pintar(gaveta, COLOR_APAGADO)
            if not self.equivocadas:
                self._parar_zumbido()
            self._avisar(gaveta, False, "corregida")

    def _avisar(self, gaveta, fuera, resultado):
        """Cuenta al servidor lo que ha pasado. Si no llega, da igual: las
        luces y el zumbador ya han hecho su trabajo sin depender de la red."""
        if http_client is None or backend_cfg is None:
            return
        try:
            http_client.post_json(
                backend_cfg.BACKEND_HOST, EVENTO_PATH,
                # 'http' dice si el puerto 80 llego a abrirse. Sin este dato,
                # una placa que detecta las gavetas pero no puede escuchar se
                # ve identica a una sana desde Admin, y el unico sintoma es un
                # ConnectionRefusedError en el panel de pruebas.
                {"device_id": self.device_id, "led": gaveta,
                 "fuera": fuera, "resultado": resultado,
                 "gavetas": self.n_gavetas, "expansores": len(self.expansores),
                 "http": self._servidor is not None},
                port=backend_cfg.BACKEND_PORT,
                use_ssl=backend_cfg.BACKEND_USE_SSL,
                timeout=TIMEOUT_AVISO_S)
        except Exception as e:
            print("Gavetas: aviso al servidor fallido:", e)

    # ── Servidor HTTP (el PC empuja la orden, no se sondea) ─────────────────

    def _abrir_servidor(self):
        """Socket de escucha del puerto 80, o None si no se pudo abrir.

        La direccion se resuelve con getaddrinfo igual que en el resto del
        codigo que habla por red (http_client.py, lector_puesto.py): en
        MicroPython bind() espera el formato que devuelve getaddrinfo, y la
        tupla cruda ("0.0.0.0", 80) no es equivalente en todos los puertos.
        Cuando falla, falla en silencio y el puerto queda cerrado: la placa
        sigue leyendo tarjetas y encendiendo gavetas, pero nadie puede
        empujarle una orden y el PC solo ve un ConnectionRefusedError.

        El socket se cierra si algo peta a medias. Sin eso cada reintento
        dejaria un descriptor colgado hasta agotarlos.
        """
        s = None
        try:
            direccion = socket.getaddrinfo(
                "0.0.0.0", PUERTO_HTTP, 0, socket.SOCK_STREAM)[0][-1]
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(direccion)
            s.listen(2)   # dos peticiones pegadas no se pisan
            s.settimeout(0)     # accept() no bloquea: si no hay nadie, error
            print("Gavetas: puerto %d escuchando" % PUERTO_HTTP)
            return s
        except Exception as e:
            print("Gavetas: no se pudo abrir el puerto %d:" % PUERTO_HTTP, e)
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
            return None

    def _atender_http(self, ahora):
        if self._servidor is None:
            # Reintento espaciado. Al arrancar, la red puede no estar lista
            # todavia; sin el freno se abriria un socket nuevo por vuelta del
            # bucle (milisegundos) y se agotarian los descriptores.
            if time.ticks_diff(ahora, self._reintento_servidor_ms) < 0:
                return
            self._reintento_servidor_ms = time.ticks_add(ahora, REINTENTO_SERVIDOR_MS)
            self._servidor = self._abrir_servidor()
            if self._servidor is None:
                return
        try:
            cliente, _ = self._servidor.accept()
        except Exception:
            return      # nadie llamando, que es el caso normal
        try:
            cliente.settimeout(TIMEOUT_PETICION_S)
            respuesta = self._responder(self._leer_cuerpo(cliente))
            cuerpo = _json_bytes(respuesta)
            cliente.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                          b"Connection: close\r\nContent-Length: %d\r\n\r\n" % len(cuerpo))
            cliente.write(cuerpo)
        except Exception as e:
            print("Gavetas: peticion HTTP fallida:", e)
        finally:
            try:
                cliente.close()
            except Exception:
                pass

    def _leer_cuerpo(self, cliente):
        """Cuerpo del POST, leyendo la cabecera LINEA A LINEA.

        Antes esto era un read(1024) de golpe, y ahi estaba el fallo que hacia
        que la gaveta se encendiera y aun asi el PC dijera "la placa no
        responde": la peticion son unos 120 bytes y el cliente no cierra su
        lado (esta esperando la respuesta), asi que pedir 1024 se quedaba
        esperando bytes que no iban a llegar nunca. Solo salia de ahi al
        agotar el timeout, un segundo despues, cuando el PC ya habia desistido
        -- pero para entonces el LED ya se habia encendido.

        readline() vuelve en cuanto ve el fin de linea, y Content-Length dice
        exactamente cuanto cuerpo queda: ni una espera de mas.
        """
        longitud = 0
        while True:
            linea = cliente.readline()
            if not linea or linea == b"\r\n" or linea == b"\n":
                break
            if linea[:15].lower() == b"content-length:":
                try:
                    longitud = int(linea.split(b":", 1)[1].strip())
                except Exception:
                    longitud = 0
        if longitud <= 0:
            return b""      # un GET sin cuerpo: sirve para consultar el estado
        return cliente.read(min(longitud, MAX_CUERPO)) or b""

    def _responder(self, cuerpo):
        datos = _json_carga(cuerpo)

        if datos.get("apagar"):
            self.apagar()
            return {"ok": True, "estado": self.estado()}

        respuesta = self.ejecutar_test(datos)
        if respuesta is not None:
            return respuesta

        led = datos.get("led")
        if led is None:
            return {"ok": True, "estado": self.estado()}
        try:
            led = int(led)
        except (TypeError, ValueError):
            return {"ok": False, "error": "led no es un numero"}

        ok, motivo = self.encender(led, datos.get("terminal") or "", datos.get("validas"))
        return {"ok": ok, "error": motivo, "estado": self.estado()}

    # ── Bucle ───────────────────────────────────────────────────────────────

    def actualizar(self):
        """Se llama desde el bucle principal, junto al sondeo del lector."""
        ahora = time.ticks_ms()
        self._atender_http(ahora)
        self._atender_micros(ahora)
        self._atender_zumbador(ahora)
        self._atender_parpadeo(ahora)


def _color(crudo, por_defecto):
    """Terna RGB de lo que venga en el JSON, o el color por defecto."""
    try:
        return tuple(int(c) for c in (crudo or por_defecto)[:3])
    except Exception:
        return por_defecto


def _json_bytes(obj):
    import json
    return json.dumps(obj).encode("utf-8")


def _json_carga(datos):
    import json
    try:
        return json.loads(datos) or {}
    except Exception:
        return {}


def crear(cfg, buzzer, device_id):
    """Monta el pick-to-light si hay hardware; devuelve None si no lo hay.

    No lanza nunca: una placa con el bus mal soldado tiene que seguir leyendo
    tarjetas, que es su trabajo principal.
    """
    try:
        sda = Pin(getattr(cfg, "GAVETAS_SDA_PIN", SDA_PIN_DEF), Pin.OPEN_DRAIN, Pin.PULL_UP)
        scl = Pin(getattr(cfg, "GAVETAS_SCL_PIN", SCL_PIN_DEF), Pin.OPEN_DRAIN, Pin.PULL_UP)
        # Los pull-up internos (~45k) se piden aqui a proposito: con un solo
        # expansor y cables cortos evitan tener que soldar los de 4,7k.
        i2c = SoftI2C(scl=scl, sda=sda, freq=100000)
        expansores = mcp23017.detectar(i2c)
        if not expansores:
            print("Gavetas: sin expansores en el bus I2C, pick-to-light desactivado")
            return None

        tira = None
        if neopixel is not None:
            n = mcp23017.CANALES * len(expansores)
            tira = neopixel.NeoPixel(Pin(getattr(cfg, "GAVETAS_LED_PIN", LED_PIN_DEF)), n)
        else:
            print("Gavetas: sin modulo neopixel, se vigilan los micros sin luces")

        gav = Gavetas(expansores, tira, buzzer, device_id)
        print("Gavetas: %d expansor(es), %d gavetas" % (len(expansores), gav.n_gavetas))
        return gav
    except Exception as e:
        print("Gavetas: no se pudo arrancar el pick-to-light:", e)
        return None
