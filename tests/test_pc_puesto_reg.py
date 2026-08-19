"""Fichero .reg que quita el aviso "No es seguro" en un PC de puesto.

La app no puede aplicarlo sola (una web no toca el registro del equipo que la
abre), pero sí puede generarlo ya relleno con los origenes correctos para que
en el puesto solo haya que abrirlo.
"""


def test_exige_pin(client):
    assert client.get('/api/red/pc-puesto.reg').status_code == 401


def test_se_descarga_como_fichero_reg(admin_client):
    r = admin_client.get('/api/red/pc-puesto.reg')
    assert r.status_code == 200
    assert '.reg' in r.headers['Content-Disposition']
    assert 'attachment' in r.headers['Content-Disposition']


def _texto(admin_client, **kwargs):
    return admin_client.get('/api/red/pc-puesto.reg', **kwargs).get_data().decode('utf-8-sig')


def test_tiene_la_cabecera_que_espera_regedit(admin_client):
    texto = _texto(admin_client)
    assert texto.startswith('Windows Registry Editor Version 5.00')
    # regedit necesita CRLF: con LF a secas lo rechaza
    assert '\r\n' in texto


def test_cubre_chrome_y_edge(admin_client):
    texto = _texto(admin_client)
    assert r'SOFTWARE\Policies\Google\Chrome\OverrideSecurityRestrictionsOnInsecureOrigin' in texto
    assert r'SOFTWARE\Policies\Microsoft\Edge\OverrideSecurityRestrictionsOnInsecureOrigin' in texto


def test_los_origenes_van_numerados_como_lista(admin_client):
    """La politica es una lista: los valores son "1", "2"... no un solo valor."""
    texto = _texto(admin_client)
    assert '"1"="http://' in texto


def test_el_origen_no_lleva_barra_final(admin_client):
    """La politica no reconoce un origen acabado en '/': tiene que ser
    esquema + host + puerto y nada mas."""
    for linea in _texto(admin_client).splitlines():
        if linea.startswith('"') and '"="http' in linea:
            assert not linea.rstrip().endswith('/"'), linea


def test_incluye_el_origen_por_el_que_se_entra(app):
    """El origen tiene que coincidir letra por letra con la barra del navegador."""
    from app.routes.sistema import _origenes_de_la_app
    with app.test_request_context('/', base_url='http://192.168.50.1:5001'):
        origenes = _origenes_de_la_app()
    assert 'http://192.168.50.1:5001' in origenes


def test_incluye_tambien_la_ip_de_planta_si_se_baja_desde_el_servidor(app):
    """Bajado desde el propio servidor el origen seria 'localhost', que en un
    PC de puesto no vale para nada: hay que añadir el de la red."""
    from app.routes.sistema import _origenes_de_la_app
    with app.test_request_context('/', base_url='http://localhost:5001'):
        origenes = _origenes_de_la_app()
    assert 'http://localhost:5001' in origenes
    assert any('localhost' not in o for o in origenes), origenes
