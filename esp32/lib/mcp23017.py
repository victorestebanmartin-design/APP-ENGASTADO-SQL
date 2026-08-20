# mcp23017.py -- Driver minimo del expansor I2C MCP23017 (16 canales) para
# MicroPython. Se usa en el pick-to-light de gavetas: cada canal lleva el
# micro-interruptor que detecta si la gaveta esta puesta.
#
# Aqui solo hace falta LEER entradas con pull-up, asi que el driver configura
# los 16 canales como entrada y expone una unica lectura de los dos puertos de
# golpe. Nada de interrupciones: el bucle principal sondea cada pocos ms, que
# es mas robusto frente a un flanco perdido y no gasta un GPIO mas.
#
# Registros en modo BANK=0 (el de fabrica), que es el que usamos.

IODIRA = 0x00   # 1 = entrada
IODIRB = 0x01
GPPUA  = 0x0C   # 1 = pull-up de 100k activado
GPPUB  = 0x0D
GPIOA  = 0x12   # lectura del puerto
GPIOB  = 0x13

DIRECCION_MIN = 0x20   # A2 A1 A0 = 000
DIRECCION_MAX = 0x27   # A2 A1 A0 = 111
CANALES = 16


class MCP23017:
    def __init__(self, i2c, direccion):
        self.i2c = i2c
        self.direccion = direccion
        self._todo_entradas_con_pullup()

    def _escribir(self, registro, valor):
        self.i2c.writeto_mem(self.direccion, registro, bytes([valor]))

    def _todo_entradas_con_pullup(self):
        self._escribir(IODIRA, 0xFF)
        self._escribir(IODIRB, 0xFF)
        self._escribir(GPPUA, 0xFF)
        self._escribir(GPPUB, 0xFF)

    def leer(self):
        """Los 16 canales como un entero: bit 0 = GPA0 ... bit 15 = GPB7.

        Con el pull-up interno, un contacto cerrado a masa lee 0 y uno abierto
        lee 1. En las gavetas: 0 = gaveta puesta, 1 = gaveta fuera.
        """
        datos = self.i2c.readfrom_mem(self.direccion, GPIOA, 2)
        return datos[0] | (datos[1] << 8)


def detectar(i2c):
    """Lista de MCP23017 presentes en el bus, ordenados por direccion.

    El orden ES la numeracion de gavetas: el primero lleva las gavetas 1-16, el
    segundo las 17-32, etc. Por eso se ordena por direccion y no por el orden en
    que conteste el escaneo.
    """
    encontrados = []
    try:
        presentes = i2c.scan()
    except Exception as e:
        print("MCP23017: no se pudo escanear el bus I2C:", e)
        return encontrados
    for direccion in sorted(presentes):
        if DIRECCION_MIN <= direccion <= DIRECCION_MAX:
            try:
                encontrados.append(MCP23017(i2c, direccion))
            except Exception as e:
                print("MCP23017: fallo al inicializar 0x%02X:" % direccion, e)
    return encontrados
