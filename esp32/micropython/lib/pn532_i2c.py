# pn532_i2c.py — Driver minimo del PN532 (NFC MODULE V3) por I2C, para
# MicroPython. Solo hace lo que necesita la pantalla del carro: leer el UID de
# una tarjeta que se acerca. Nada de escribir, ni de leer bloques.
#
# El modulo tiene que estar en modo I2C (mira la tabla serigrafiada en la
# propia placa para la posicion de los dos micro-interruptores).
#
# Uso:
#     from pn532_i2c import PN532
#     nfc = PN532(sda=6, scl=5)      # lanza excepcion si no responde
#     uid = nfc.leer_uid(timeout_ms=80)   # "A1B2C3D4" o None
#
# Diseñado para NO bloquear: leer_uid() manda la orden, espera como mucho
# timeout_ms a que haya respuesta y se va. La pantalla lo llama cada pocos
# cientos de ms desde el bucle principal.

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
        self.i2c = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=freq)
        self.addr = addr
        # Si el modulo no esta ahi, esto revienta y quien nos crea decide
        self.version = self.firmware()
        self.sam_config()

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
        """El PN532 por I2C antepone un byte de estado: 0x01 = tengo respuesta."""
        fin = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(fin, time.ticks_ms()) > 0:
            try:
                if self.i2c.readfrom(self.addr, 1)[0] & 0x01:
                    return True
            except OSError:
                pass          # el modulo aun no contesta: reintentar
            time.sleep_ms(5)
        return False

    def _leer(self, n, timeout_ms=100):
        """Lee una respuesta completa y devuelve solo los datos utiles."""
        if not self._esperar_listo(timeout_ms):
            return None
        # 1 byte de estado + preambulo + cabecera + datos + checksum + postambulo
        bruto = self.i2c.readfrom(self.addr, n + 9)
        if bruto[0] & 0x01 == 0:
            return None
        trama = bruto[1:]
        i = trama.find(_PREAMBLE)
        if i < 0:
            return None
        largo = trama[i + 3]
        ini = i + 5                       # saltar preambulo, largo, LCS y 0xD5
        return trama[ini + 1:ini + largo - 1]

    def _tragar_ack(self, timeout_ms=100):
        if not self._esperar_listo(timeout_ms):
            return False
        return _ACK in self.i2c.readfrom(self.addr, 7)

    # ── Ordenes ───────────────────────────────────────────────────────────────

    def firmware(self):
        """Version del firmware del PN532. Sirve de 'ping': si no contesta,
        el modulo no esta o esta mal cableado."""
        self._escribir([_CMD_GETFIRMWAREVERSION])
        if not self._tragar_ack(200):
            raise OSError("PN532 no responde (revisa cableado y modo I2C)")
        r = self._leer(4, 200)
        if not r or len(r) < 4:
            raise OSError("PN532 sin version")
        return "%d.%d" % (r[1], r[2])

    def sam_config(self):
        """Modo lector normal, sin SAM y sin timeout interno."""
        self._escribir([_CMD_SAMCONFIGURATION, 0x01, 0x14, 0x01])
        self._tragar_ack(200)
        self._leer(0, 200)

    def leer_uid(self, timeout_ms=80):
        """UID de una tarjeta ISO14443A cercana, en hex y mayusculas.

        Devuelve None si no hay ninguna (lo normal la mayoria de las veces).
        Nunca lanza excepcion: un fallo de bus se trata como 'no hay tarjeta'.
        """
        try:
            self._escribir([_CMD_INLISTPASSIVETARGET, 0x01, 0x00])
            if not self._tragar_ack(timeout_ms):
                return None
            r = self._leer(19, timeout_ms)
            # r = [nº targets, nº target, SENS_RES x2, SEL_RES, largo UID, UID...]
            if not r or len(r) < 6 or r[0] < 1:
                return None
            largo = r[5]
            if largo == 0 or len(r) < 6 + largo:
                return None
            return ''.join('%02X' % b for b in r[6:6 + largo])
        except OSError:
            return None
