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
INTERVALO_MICROS_MS = 40    # cada cuanto se relee el bus I2C
ANTIRREBOTE_MS = 80         # un micro rebota unos ms al abrir y al cerrar
BEEP_OK_MS = 120            # confirmacion corta de recogida correcta
ZUMBIDO_ON_MS = 400         # el zumbido de error late para que no se ignore
ZUMBIDO_OFF_MS = 120
TIMEOUT_AVISO_S = 2         # avisar al servidor no puede frenar el bucle


class Gavetas:
    def __init__(self, expansores, tira, buzzer, device_id):
        self.expansores = expansores
        self.tira = tira
        self.buzzer = buzzer
        self.device_id = device_id
        self.n_gavetas = mcp23017.CANALES * len(expansores)

        self.objetivo = None        # numero de gaveta que hay que abrir
        self.recogida = False       # ya se abrio la correcta
        self.equivocadas = set()    # gavetas mal abiertas y aun sin devolver

        self.fuera = self._leer_micros()   # foto inicial: lo que ya estaba fuera
        self._ultima_lectura_ms = time.ticks_ms()
        self._cambio_pendiente = {}        # gaveta -> ticks del primer cambio

        self._zumbido_hasta_ms = 0
        self._zumbido_encendido = False
        self._beep_hasta_ms = 0

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

    def encender(self, gaveta):
        """Marca una gaveta como objetivo y la pone en verde."""
        if not 1 <= gaveta <= self.n_gavetas:
            return False, "La gaveta %d no existe (esta placa tiene %d)" % (
                gaveta, self.n_gavetas)
        self.apagar()
        self.objetivo = gaveta
        self.recogida = False
        # Foto nueva: una gaveta que YA estaba fuera antes de esta orden no es
        # un error del operario, asi que no debe hacer sonar nada.
        self.fuera = self._leer_micros()
        self._pintar(gaveta, COLOR_EN_USO if gaveta in self.fuera else COLOR_OBJETIVO)
        if gaveta in self.fuera:
            self.recogida = True
        return True, ""

    def apagar(self):
        """Todo apagado y sin objetivo: la placa vuelve a estar en reposo."""
        self.objetivo = None
        self.recogida = False
        self.equivocadas.clear()
        self._parar_zumbido()
        self._apagar_tira()

    def estado(self):
        return {
            "expansores": len(self.expansores),
            "gavetas": self.n_gavetas,
            "objetivo": self.objetivo,
            "recogida": self.recogida,
            "fuera": sorted(self.fuera),
        }

    # ── Zumbador (sin bloquear el bucle) ────────────────────────────────────

    def _parar_zumbido(self):
        self._zumbido_hasta_ms = 0
        self._zumbido_encendido = False
        self._beep_hasta_ms = 0
        try:
            self.buzzer.off()
        except Exception:
            pass

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

        # Sin objetivo no hay ni acierto ni error: alguien esta reponiendo o
        # dejo un cajon abierto. Se avisa al servidor y no suena nada.
        if self.objetivo is None:
            self._avisar(gaveta, ahora_fuera, "sin_objetivo")
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
                {"device_id": self.device_id, "led": gaveta,
                 "fuera": fuera, "resultado": resultado,
                 "gavetas": self.n_gavetas, "expansores": len(self.expansores)},
                port=backend_cfg.BACKEND_PORT,
                use_ssl=backend_cfg.BACKEND_USE_SSL,
                timeout=TIMEOUT_AVISO_S)
        except Exception as e:
            print("Gavetas: aviso al servidor fallido:", e)

    # ── Servidor HTTP (el PC empuja la orden, no se sondea) ─────────────────

    def _abrir_servidor(self):
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", PUERTO_HTTP))
            s.listen(1)
            s.settimeout(0)     # accept() no bloquea: si no hay nadie, error
            return s
        except Exception as e:
            print("Gavetas: no se pudo abrir el puerto %d:" % PUERTO_HTTP, e)
            return None

    def _atender_http(self):
        if self._servidor is None:
            return
        try:
            cliente, _ = self._servidor.accept()
        except Exception:
            return      # nadie llamando, que es el caso normal
        try:
            cliente.settimeout(1)
            peticion = cliente.read(1024) or b""
            respuesta = self._responder(peticion)
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

    def _responder(self, peticion):
        corte = peticion.find(b"\r\n\r\n")
        cuerpo = peticion[corte + 4:] if corte >= 0 else b""
        datos = _json_carga(cuerpo)

        if datos.get("apagar"):
            self.apagar()
            return {"ok": True, "estado": self.estado()}

        led = datos.get("led")
        if led is None:
            return {"ok": True, "estado": self.estado()}
        try:
            led = int(led)
        except (TypeError, ValueError):
            return {"ok": False, "error": "led no es un numero"}

        ok, motivo = self.encender(led)
        return {"ok": ok, "error": motivo, "estado": self.estado()}

    # ── Bucle ───────────────────────────────────────────────────────────────

    def actualizar(self):
        """Se llama desde el bucle principal, junto al sondeo del RC522."""
        ahora = time.ticks_ms()
        self._atender_http()
        self._atender_micros(ahora)
        self._atender_zumbador(ahora)


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
