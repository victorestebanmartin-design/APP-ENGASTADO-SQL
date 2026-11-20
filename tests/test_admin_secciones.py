"""Admin: el menú, las secciones y la carga de cada sección encajan.

No hay tests de interfaz, y en Admin los nombres de sección se escriben a
mano en tres sitios (botón del menú, <section id="sec-...">, y las llamadas
adminNav('...') / adminAlAbrir('...')). Si uno se queda descolgado tras mover
tarjetas, la pantalla no falla: la sección sale vacía o el botón no hace
nada. Esto lo detecta.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _pagina(admin_client):
    respuesta = admin_client.get('/admin')
    assert respuesta.status_code == 200
    return respuesta.get_data(as_text=True)


def test_cada_entrada_del_menu_tiene_su_seccion(admin_client):
    html = _pagina(admin_client)
    secciones = set(re.findall(r'<section id="sec-([\w-]+)"', html))
    menu = re.findall(r'data-section="([\w-]+)"', html)
    assert menu, 'no se encuentra el menú de Admin'
    assert set(menu) <= secciones, set(menu) - secciones
    # Y al revés: ninguna sección queda sin entrada en el menú.
    assert secciones <= set(menu), secciones - set(menu)


def test_las_cargas_y_enlaces_apuntan_a_secciones_que_existen(admin_client):
    html = _pagina(admin_client)
    js = ''.join(f.read_text(encoding='utf-8')
                 for f in sorted((RAIZ / 'static' / 'js').glob('admin*.js')))
    secciones = set(re.findall(r'<section id="sec-([\w-]+)"', html))
    nombradas = set(re.findall(r"adminAlAbrir\('([\w-]+)'", html + js))
    nombradas |= set(re.findall(r"adminNav\('([\w-]+)'\)", html + js))
    assert nombradas, 'no se encuentran cargas de sección'
    assert nombradas <= secciones, nombradas - secciones


def test_adminAlAbrir_existe_antes_de_los_scripts_que_lo_usan(admin_client):
    """admin-nav.js va el primero: los demás scripts de Admin llaman a
    adminAlAbrir al leerse, y fallarían si aún no existe."""
    html = _pagina(admin_client)
    nav = (RAIZ / 'static' / 'js' / 'admin-nav.js').read_text(encoding='utf-8')
    assert 'function adminAlAbrir(' in nav
    orden = re.findall(r"js/(admin[\w-]*)\.js", html)
    assert orden[0] == 'admin-nav', orden
    # Y todo fichero de Admin que apunta cargas está de verdad en la página.
    for fichero in (RAIZ / 'static' / 'js').glob('admin*.js'):
        if "adminAlAbrir('" in fichero.read_text(encoding='utf-8'):
            assert fichero.stem in orden, fichero.name


def test_modulos_dicen_cuales_solo_se_dan_a_proposito(client):
    """La tabla de Operarios pinta las casillas de un operario sin permisos
    guardados (NULL) con este dato: si no coincidiera con el servidor, saldría
    marcado «Calidad» a alguien que en realidad no puede entrar."""
    from app.routes.base import MODULOS_SOLO_EXPLICITOS
    modulos = client.get('/api/modulos').get_json()['modulos']
    assert {m['slug'] for m in modulos if m['explicito']} == set(MODULOS_SOLO_EXPLICITOS)
