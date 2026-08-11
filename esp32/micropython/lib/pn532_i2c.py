# pn532_i2c.py — Driver del PN532 (NFC MODULE V3) por I2C para MicroPython.
# Solo hace lo que necesita la pantalla del carro: leer el UID de una tarjeta.
# Nada de escribir en la tarjeta ni de leer bloques.
#
# El modulo tiene que estar en modo I2C (mira la tabla serigrafiada en la
# propia placa para la posicion de los dos micro-interruptores).
#
# Pensado para un taller, donde las cosas se cuelgan:
#   - Despierta al PN532 antes de hablarle (si no, tras un arranque raro no
#     contesta nunca).
#   - Valida las tramas (longitud y checksums) en vez de leer a ciegas.
#   - Sabe recuperar el bus I2C si un esclavo lo deja bloqueado a media
#     transferencia, que es la forma tipica de morir de estos modulos.
#   - Ninguna funcion publica lanza excepciones: devuelven None o False.
#
# Uso:
#     from pn532_i2c import PN532
#     nfc = PN532(sda=6, scl=5)           # no arranca el modulo todavia
#     if nfc.reiniciar(): ...             # True si el modulo responde
#     uid = nfc.leer_uid(timeout_ms=80)   # "A1B2C3D4" o None

import time
from machine import Pin, I2C

_ADDR = 0x24                       # direccion I2C del PN532
_PREAMBLE = b'\x00\x00\xFF'
_ACK = b'\x00\x00\xFF\x00\xFF\x00'

_CMD_SAMCONFIGURATION = 0x14
_CMD_INLISTPASSIVETARGET = 0x4A
_CMD_GETFIRMWAREVERSION = 0x02


class PN532:
    def __init__(self, sda, scl, freq=100000, addr=_ADDR):
        self.sda_pin = sda
        self.scl_pin = scl
        self.freq = freq
        self.addr = addr
        self.i2c = None
        self.version = ''

    # ── Bus ───────────────────────────────────────────────────────────────────

    def recuperar_bus(self):
        """Suelta el bus si un esclavo dejo SDA clavada a nivel bajo.

        Cuando el PN532 se cuelga a media transferencia (o el ESP32 se reinicia
        en mitad de una), SDA se queda baja y el bus no vuelve solo: hay que
        generar pulsos de reloj hasta que el esclavo suelte. Es el
        procedimiento estandar de recuperacion de I2C.
        """
        try:
            if self.i2c is not None:
                self.i2c = None
                time.sleep_ms(10)
            sda = Pin(self.sda_pin, Pin.IN, Pin.PULL_UP)
            scl = Pin(self.scl_pin, Pin.OUT, value=1)
            for _ in range(9):
                if sda.value():
                    break            # ya la ha soltado
                scl.value(0); time.sleep_us(10)
                scl.value(1); time.sleep_us(10)
            # Condicion de STOP a mano para dejar el bus en reposo
            sda_out = Pin(self.sda_pin, Pin.OUT, value=0)
            time.sleep_us(10)
            scl.value(1); time.sleep_us(10)
            sda_out.value(1); time.sleep_us(10)
        except Exception:
            pass

    def reiniciar(self):
        """(Re)arranca el modulo: recupera el bus, despierta y configura.

        Devuelve True si el PN532 contesta. Se puede llamar tantas veces como
        haga falta; es lo que usa la pantalla para reintentar en caliente.
        """
        self.version = ''
        try:
            self.recuperar_bus()
            self.i2c = I2C(0, sda=Pin(self.sda_pin), scl=Pin(self.scl_pin),
                           freq=self.freq)
        except Exception:
            self.i2c = None
            return False

        try:
            self._despertar()
            v = self._firmware()
            if not v:
                return False
            self.version = v
            return self._sam_config()
        except Exception:
            return False

    def _despertar(self):
        """El PN532 puede estar dormido: un preambulo largo lo levanta.

        No importa si falla (si ya estaba despierto puede no hacer ACK).
        """
        try:
            self.i2c.writeto(self.addr, b'\x55\x55\x00\x00\x00\x00\x00\x00\x00')
        except OSError:
            pass
        time.sleep_ms(20)

    # ── Trama PN532 ───────────────────────────────────────────────────────────

    def _escribir(self, datos):
        """Envuelve datos en una trama normal del PN532 y la manda."""
        cuerpo = bytes([0xD4]) + bytes(datos)
        largo = len(cuerpo)
        lcs = (~largo + 1) & 0xFF
        dcs = (~sum(cuerpo) + 1) & 0xFF
        trama = _PREAMBLE + bytes([largo, lcs]) + cuerpo + bytes([dcs, 0x00])
        self.i2c.writeto(self.addr, trama)

    def _esperar_listo(self, timeout_ms):
        """Por I2C el PN532 antepone un byte de estado: bit 0 = tengo respuesta."""
        fin = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(fin, time.ticks_ms()) > 0:
            try:
                if self.i2c.readfrom(self.addr, 1)[0] & 0x01:
                    return True
            except OSError:
                pass          # el modulo aun no contesta: reintentar
            time.sleep_ms(5)
        return False

    def _leer(self, n_max, timeout_ms=100):
        """Lee una respuesta y devuelve solo los datos, o None si no cuadra.

        Valida preambulo, longitud (LEN/LCS) y checksum (DCS) en vez de fiarse
        de posiciones fijas: una trama corta o corrupta devuelve None.
        """
        if not self._esperar_listo(timeout_ms):
            return None
        try:
            bruto = self.i2c.readfrom(self.addr, n_max + 10)
        except OSError:
            return None
        if not bruto or not (bruto[0] & 0x01):
            return None

        t = bruto[1:]
        i = t.find(_PREAMBLE)
        if i < 0 or len(t) < i + 5:
            return None
        largo = t[i + 3]
        lcs = t[i + 4]
        if largo == 0 or (largo + lcs) & 0xFF:
            return None                      # longitud incoherente
        ini = i + 5                          # primer byte del cuerpo (TFI)
        if len(t) < ini + largo + 1:
            return None
        cuerpo = t[ini:ini + largo]
        dcs = t[ini + largo]
        if (sum(cuerpo) + dcs) & 0xFF:
            return None                      # checksum malo
        if cuerpo[0] != 0xD5:
            return None                      # no es respuesta del modulo
        return cuerpo[2:]                    # sin TFI ni codigo de comando

    def _tragar_ack(self, timeout_ms=100):
        if not self._esperar_listo(timeout_ms):
            return False
        try:
            return _ACK in self.i2c.readfrom(self.addr, 7)
        except OSError:
            return False

    # ── Ordenes ───────────────────────────────────────────────────────────────

    def _firmware(self):
        """Version del firmware. Sirve de 'ping': si no contesta, no esta."""
        self._escribir([_CMD_GETFIRMWAREVERSION])
        if not self._tragar_ack(200):
            return ''
        r = self._leer(4, 200)
        if not r or len(r) < 3:
            return ''
        return "%d.%d" % (r[1], r[2])

    def _sam_config(self):
        """Modo lector normal, sin SAM y sin timeout interno."""
        self._escribir([_CMD_SAMCONFIGURATION, 0x01, 0x14, 0x01])
        if not self._tragar_ack(200):
            return False
        return self._leer(0, 200) is not None

    def leer_uid(self, timeout_ms=80):
        """UID de una tarjeta ISO14443A cercana, en hex y mayusculas.

        Devuelve None si no hay ninguna, que es lo normal casi siempre. Nunca
        lanza: un fallo de bus se trata como 'no hay tarjeta' y quien llama
        decide cuando dar el modulo por muerto (ver contador de fallos en
        main_wifi.py).
        """
        if self.i2c is None:
            return None
        try:
            self._escribir([_CMD_INLISTPASSIVETARGET, 0x01, 0x00])
            if not self._tragar_ack(timeout_ms):
                return None
            r = self._leer(20, timeout_ms)
            # r = [nº targets, nº target, SENS_RES x2, SEL_RES, largo UID, UID...]
            if not r or len(r) < 6 or r[0] < 1:
                return None
            largo = r[5]
            if largo == 0 or len(r) < 6 + largo:
                return None
            return ''.join('%02X' % b for b in r[6:6 + largo])
        except Exception:
            return None

    def vivo(self, timeout_ms=150):
        """True si el modulo sigue contestando (para decidir si hay que
        reiniciarlo tras varios fallos de lectura seguidos)."""
        if self.i2c is None:
            return False
        try:
            return bool(self._firmware())
        except Exception:
            return False
