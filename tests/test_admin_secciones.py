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
    js = (RAIZ / 'static' / 'js' / 'admin.js').read_text(encoding='utf-8')
    secciones = set(re.findall(r'<section id="sec-([\w-]+)"', html))
    nombradas = set(re.findall(r"adminAlAbrir\('([\w-]+)'", html + js))
    nombradas |= set(re.findall(r"adminNav\('([\w-]+)'\)", html + js))
    assert nombradas, 'no se encuentran cargas de sección'
    assert nombradas <= secciones, nombradas - secciones


def test_adminAlAbrir_existe_antes_de_los_scripts_que_lo_usan(admin_client):
    """El bloque de navegación va el primero: admin.js y los demás bloques
    llaman a adminAlAbrir al leerse, y fallarían si aún no existe."""
    html = _pagina(admin_client)
    definicion = html.index('function adminAlAbrir(')
    for marca in ("adminAlAbrir('operarios'", "adminAlAbrir('colores'", 'js/admin.js'):
        assert html.index(marca) > definicion, marca
