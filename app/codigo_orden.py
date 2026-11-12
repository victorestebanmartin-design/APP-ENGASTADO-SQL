"""El codigo de orden que se lee con la pistola: corte-orden-cantidad.

Hay etiquetas impresas en Code 39 "extendido" que codifican el guion como
/M, aunque en Code 39 el guion es un caracter propio y no lleva pareja. La
pistola (Datalogic QM2500) entrega ese /M tal cual: H0564725/M60263165/M1.
Activar el Full ASCII en la pistola no lo arregla, se probo: traduce las
parejas validas (+H -> h) pero no /M. Asi que se aceptan las dos formas.

Solo se aplica a este codigo: un corte, una orden y una cantidad no llevan
nunca una barra, asi que /M no puede ser otra cosa que un guion. Los QR de
bonos y carros no pasan por aqui.
"""
import re

CODIGO_ORDEN = re.compile(r'([A-Za-z0-9_]+)-(\d+)-([1-9]\d*)')


def normalizar_codigo_escaneado(codigo):
    """Quita espacios y cambia el /M del Code 39 extendido por un guion."""
    if not isinstance(codigo, str):
        return ''
    return re.sub(r'/[Mm]', '-', codigo.strip())


def separar_codigo_orden(codigo):
    """(corte, numero, cantidad_texto) o None si no es un codigo de orden."""
    coincidencia = CODIGO_ORDEN.fullmatch(normalizar_codigo_escaneado(codigo))
    return coincidencia.groups() if coincidencia else None
