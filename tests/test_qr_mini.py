"""El QR del bono se genera en la propia placa (esp32/micropython/lib/qr_mini.py).
Aqui se prueba en CPython: es el mismo codigo que corre en MicroPython."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'esp32', 'micropython', 'lib'))
import qr_mini  # noqa: E402


@pytest.mark.parametrize('texto,lado', [
    ('0000002_2026', 21),     # version 1
    ('A' * 20, 25),           # version 2
    ('B' * 40, 29),           # version 3
    ('C' * 100, 37),         # version 5 (el tope)
])
def test_tamano_segun_longitud(texto, lado):
    m = qr_mini.crear(texto)
    assert len(m) == len(m[0])
    assert len(m) == lado


def test_pasa_del_tope_devuelve_none():
    assert qr_mini.crear('Z' * 101) is None


def test_lleva_los_tres_buscadores():
    m = qr_mini.crear('0000002_2026')
    n = len(m)
    for x0, y0 in ((0, 0), (n - 7, 0), (0, n - 7)):
        assert all(m[y0][x0 + i] for i in range(7))              # borde superior
        assert all(m[y0 + 6][x0 + i] for i in range(7))          # borde inferior
        assert m[y0 + 3][x0 + 3] and not m[y0 + 1][x0 + 1]       # centro y anillo claro


def test_se_decodifica_con_un_lector_real():
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    det = cv2.QRCodeDetector()
    for texto in ('0000002_2026', 'ZEFIRO 26/10', 'X' * 40, 'ñandú 26/10'):
        m = qr_mini.crear(texto)
        n, esc, q = len(m), 8, 4
        img = np.full(((n + 2 * q) * esc,) * 2, 255, np.uint8)
        for y in range(n):
            for x in range(n):
                if m[y][x]:
                    img[(y + q) * esc:(y + q + 1) * esc, (x + q) * esc:(x + q + 1) * esc] = 0
        assert det.detectAndDecode(img)[0] == texto
