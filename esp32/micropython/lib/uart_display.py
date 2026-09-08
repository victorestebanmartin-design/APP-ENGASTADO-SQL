"""Enlace serie opcional con una pantalla secundaria.

El modulo no conoce la logica del carro: recibe un diccionario ya construido,
lo serializa como una linea JSON y nunca deja que un fallo de UART tumbe el
bucle principal.
"""

import json


class DisplayUart:
    """UART para una pantalla secundaria, desactivada si no hay pines fijados."""

    def __init__(self, uart_id=1, tx_pin=None, rx_pin=None, baudrate=115200):
        self.uart = None
        self.error = ''
        if tx_pin is None or rx_pin is None:
            return
        try:
            from machine import UART, Pin
            self.uart = UART(
                uart_id,
                baudrate=baudrate,
                bits=8,
                parity=None,
                stop=1,
                tx=Pin(tx_pin),
                rx=Pin(rx_pin),
            )
        except Exception as exc:
            self.error = str(exc)

    @property
    def activa(self):
        return self.uart is not None

    def enviar(self, mensaje):
        """Envía una trama JSON terminada en salto de línea."""
        if self.uart is None:
            return False
        try:
            linea = json.dumps(mensaje, separators=(',', ':')) + '\n'
            self.uart.write(linea)
            return True
        except Exception as exc:
            self.error = str(exc)
            return False

    def leer(self):
        """Lee una línea completa, si existe, sin bloquear."""
        if self.uart is None:
            return None
        try:
            linea = self.uart.readline()
            if not linea:
                return None
            if isinstance(linea, bytes):
                linea = linea.decode('utf-8', 'ignore')
            return json.loads(linea)
        except Exception as exc:
            self.error = str(exc)
            return None