"""Los estaticos llevan version en la URL.

Sin esto, desplegar un cambio de JS o CSS no lo hace llegar: Flask sirve
/static con 12 horas de cache y el navegador se queda con el fichero viejo.
El sintoma es peor que "no se ve el cambio": el HTML viene fresco del servidor
y el JS de la cache, asi que media pantalla es nueva y la otra media no.
"""
import os
import re

import pytest

from flask import url_for


def test_una_url_de_static_lleva_la_fecha_del_fichero(app):
    with app.test_request_context():
        url = url_for('static', filename='js/gestion-puestos.js')
    m = re.search(r'\?v=(\d+)$', url)
    assert m, 'la URL de un estatico tiene que llevar ?v=<fecha>: %s' % url

    ruta = os.path.join(app.static_folder, 'js', 'gestion-puestos.js')
    assert int(m.group(1)) == int(os.stat(ruta).st_mtime)


def test_dos_ficheros_distintos_llevan_su_propia_version(app):
    """Una version global obligaria a recargarlo todo por tocar un fichero."""
    ruta = os.path.join(app.static_folder, 'js', 'gestion-puestos.js')
    os.utime(ruta, (1700000000, 1700000000))
    with app.test_request_context():
        uno = url_for('static', filename='js/gestion-puestos.js')
        otro = url_for('static', filename='js/admin.js')
    assert uno.endswith('?v=1700000000')
    assert not otro.endswith('?v=1700000000')


def test_un_estatico_que_no_existe_no_revienta_el_render(app):
    """Un nombre mal escrito tiene que dar un 404 al pedirlo, no un 500 al pintar."""
    with app.test_request_context():
        url = url_for('static', filename='js/no-existe-esto.js')
    assert '?v=' not in url


@pytest.mark.parametrize('pagina', ['/gestion-puestos', '/v3', '/admin'])
def test_las_paginas_no_dejan_ningun_estatico_sin_versionar(client, pagina):
    """Un ?v= puesto a mano detras del url_for dejaria '?v=123?v=13'."""
    html = client.get(pagina, follow_redirects=True).get_data(as_text=True)
    for url in re.findall(r'/static/[^"\')\s]+', html):
        assert url.count('?') <= 1, 'URL con dos ? en %s: %s' % (pagina, url)
        if not url.endswith(('.webmanifest',)):
            assert '?v=' in url, 'estatico sin versionar en %s: %s' % (pagina, url)
