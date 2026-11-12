"""El codigo de orden acepta el /M del Code 39 extendido como guion.

Etiquetas reales: se imprime *H0564725-60263165-1* pero la pistola entrega
H0564725/M60263165/M1, y no hay ajuste de la pistola que lo traduzca.
"""
from app.codigo_orden import normalizar_codigo_escaneado, separar_codigo_orden


def test_guion_normal():
    assert separar_codigo_orden('H0564725-60263165-1') == ('H0564725', '60263165', '1')


def test_code39_extendido_con_barra_m():
    assert separar_codigo_orden('H0564725/M60263165/M1') == ('H0564725', '60263165', '1')
    assert separar_codigo_orden('  H0564725/m60263165/M1 \r\n') == ('H0564725', '60263165', '1')


def test_mezcla_y_basura():
    assert separar_codigo_orden('H0564725/M60263165-1') == ('H0564725', '60263165', '1')
    assert separar_codigo_orden('H0564725/60263165/1') is None
    assert separar_codigo_orden('basura') is None
    assert separar_codigo_orden(None) is None
    assert normalizar_codigo_escaneado(123) == ''
