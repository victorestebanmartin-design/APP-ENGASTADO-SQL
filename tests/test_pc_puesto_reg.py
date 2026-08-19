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


def test_por_defecto_va_al_usuario_para_no_pedir_administrador(admin_client):
    """Abrir un .reg NO eleva permisos: si escribiera en HKLM, el doble clic
    fallaría con "error de acceso al registro"."""
    texto = _texto(admin_client)
    assert 'HKEY_CURRENT_USER' in texto
    assert 'HKEY_LOCAL_MACHINE' not in texto


def test_la_version_de_equipo_usa_hklm_y_avisa_de_que_hace_falta_admin(admin_client):
    texto = admin_client.get('/api/red/pc-puesto.reg?ambito=equipo').get_data().decode('utf-8-sig')
    assert 'HKEY_LOCAL_MACHINE' in texto
    assert 'HKEY_CURRENT_USER' not in texto
    assert 'administrador' in texto
    assert 'reg import' in texto


def test_el_bat_exige_pin(client):
    assert client.get('/api/red/pc-puesto.bat').status_code == 401


def _bat(admin_client):
    r = admin_client.get('/api/red/pc-puesto.bat')
    assert r.status_code == 200
    return r.get_data().decode('cp1252')


def test_el_bat_se_autoeleva(admin_client):
    """Es lo que resuelve el caso de la cuenta sin permisos: los .reg no
    tienen "Ejecutar como administrador", un .bat puede pedirlo el solo."""
    texto = _bat(admin_client)
    assert 'net session' in texto
    assert '-Verb RunAs' in texto


def test_el_bat_escribe_para_todo_el_equipo(admin_client):
    texto = _bat(admin_client)
    assert r'HKLM\SOFTWARE\Policies\Google\Chrome' in texto
    assert r'HKLM\SOFTWARE\Policies\Microsoft\Edge' in texto
    assert 'HKCU' not in texto


def test_el_bat_lleva_los_origenes_reales(app):
    from app.routes.sistema import _origenes_de_la_app
    with app.test_request_context('/', base_url='http://192.168.50.1:5001'):
        origenes = _origenes_de_la_app()
    assert 'http://192.168.50.1:5001' in origenes


def test_el_bat_se_descarga_con_extension_bat(admin_client):
    cd = admin_client.get('/api/red/pc-puesto.bat').headers['Content-Disposition']
    assert 'attachment' in cd
    assert cd.strip().endswith('.bat')


def test_el_bat_usa_saltos_de_linea_de_windows(admin_client):
    """Un .bat con saltos LF se ejecuta mal en cmd."""
    crudo = admin_client.get('/api/red/pc-puesto.bat').get_data()
    assert b'\r\n' in crudo
    assert b'\n' not in crudo.replace(b'\r\n', b'')


def test_cada_ambito_se_descarga_con_su_propio_nombre(admin_client):
    usuario = admin_client.get('/api/red/pc-puesto.reg')
    equipo = admin_client.get('/api/red/pc-puesto.reg?ambito=equipo')
    assert 'COJOsw-pc-de-puesto.reg' in usuario.headers['Content-Disposition']
    assert 'COJOsw-pc-de-puesto-equipo.reg' in equipo.headers['Content-Disposition']


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
