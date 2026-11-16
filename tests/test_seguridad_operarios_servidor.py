"""Tres puertas que estaban abiertas a cualquier equipo de la red.

  1. Dar de alta, cambiar o dar de baja operarios (y sus tarjetas) sin sesión
     de administración.
  2. Un nombre de operario con HTML, que Admin pintaba tal cual: se ejecutaba
     con la sesión del administrador.
  3. Hacerse pasar por el servidor -- que entra sin tarjeta ni permisos -- con
     una cookie escrita a mano o con la cabecera X-Forwarded-For.
"""
import json
import os

from conftest import admin_de

IP_PLANTA = '192.168.50.30'
OTRA_IP_PLANTA = '192.168.50.31'


def _desde(ip):
    return {'environ_overrides': {'REMOTE_ADDR': ip}}


def _activar_gate(app):
    ruta = os.path.join(app.config['DATA_DIR'], 'operario_gate.json')
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'enabled': True}, f)


def _modulo_del_pc(client, ip, **kwargs):
    return client.get('/api/pc', **_desde(ip), **kwargs).get_json()['modulo']


# ==================== 1. Operarios: solo Administración ====================

def test_sin_sesion_admin_no_se_crea_un_operario(client):
    r = client.post('/api/operarios', json={'nombre': 'Intruso'})
    assert r.status_code == 401
    assert client.get('/api/operarios').get_json()['operarios'] == []


def test_sin_sesion_admin_no_se_toca_un_operario(client, admin_client):
    op = admin_client.post('/api/operarios', json={'nombre': 'Marta'}).get_json()['operario']
    admin_client.put(f"/api/operarios/{op['id']}", json={'tag_uid': 'A1B2C3D4'})

    ruta = f"/api/operarios/{op['id']}"
    assert client.put(ruta, json={'tag_uid': 'DEADBEEF'}).status_code == 401
    assert client.put(ruta, json={'nombre': 'Otra'}).status_code == 401
    assert client.delete(ruta).status_code == 401
    assert client.post(ruta + '/activar').status_code == 401

    fila = client.get('/api/operarios').get_json()['operarios'][0]
    assert (fila['nombre'], fila['tag_uid'], fila['activo']) == ('Marta', 'A1B2C3D4', 1)


def test_la_lista_de_operarios_sigue_abierta(client, admin_client):
    """El login manual y Engastado V3 la leen sin sesión de administración."""
    admin_client.post('/api/operarios', json={'nombre': 'Marta'})
    assert client.get('/api/operarios').status_code == 200


# ==================== 2. Nombres que no son nombres ====================

def test_un_nombre_con_html_se_rechaza(admin_client):
    r = admin_client.post('/api/operarios', json={'nombre': '<img src=x onerror=alert(1)>'})
    assert r.status_code == 400
    assert admin_client.get('/api/operarios').get_json()['operarios'] == []


def test_un_nombre_con_html_tampoco_entra_al_renombrar(admin_client):
    op = admin_client.post('/api/operarios', json={'nombre': 'Marta'}).get_json()['operario']
    r = admin_client.put(f"/api/operarios/{op['id']}", json={'nombre': '<script>x</script>'})
    assert r.status_code == 400
    assert admin_client.get('/api/operarios').get_json()['operarios'][0]['nombre'] == 'Marta'


def test_un_nombre_larguisimo_se_rechaza(admin_client):
    assert admin_client.post('/api/operarios', json={'nombre': 'A' * 61}).status_code == 400


def test_los_nombres_normales_siguen_valiendo(admin_client):
    for nombre in ("María José Núñez", "O'Brien", 'Jean-Luc 2'):
        assert admin_client.post('/api/operarios', json={'nombre': nombre}).status_code == 200, nombre


def test_admin_escapa_lo_que_pinta_de_operarios():
    """La defensa del servidor no basta: quedan nombres antiguos en la BD y
    los logins manuales aceptan cualquier texto."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, 'templates', 'admin.html'), encoding='utf-8') as f:
        plantilla = f.read()
    assert '${op.nombre}' not in plantilla
    assert '${l.operario}' not in plantilla
    assert '${_opEsc(op.nombre)}' in plantilla
    assert '${_opEsc(l.operario)}' in plantilla


# ==================== 3. El rol servidor no se autoproclama ====================

def test_la_cookie_de_servidor_escrita_a_mano_no_vale(app, client):
    _activar_gate(app)
    client.set_cookie('pc_modulo', 'servidor')
    assert _modulo_del_pc(client, IP_PLANTA) is None
    r = client.get('/modules', **_desde(IP_PLANTA))
    assert r.status_code == 302
    assert '/puesto/seleccionar' in r.headers['Location']


def test_un_pc_de_planta_no_se_configura_como_servidor(client):
    r = client.post('/api/pc/configurar', json={'modulo': 'servidor'}, **_desde(IP_PLANTA))
    assert r.status_code == 401
    assert _modulo_del_pc(client, IP_PLANTA) is None


def test_un_pc_de_planta_si_se_configura_para_su_modulo(client):
    """La configuración inicial de un equipo normal sigue siendo autoservicio."""
    r = client.post('/api/pc/configurar', json={'modulo': 'manguitos'}, **_desde(IP_PLANTA))
    assert r.status_code == 200
    assert _modulo_del_pc(client, IP_PLANTA) == 'manguitos'


def test_el_propio_servidor_se_configura_sin_pin(client):
    """Desde localhost (lo que abre el icono de arranque) no se pide nada."""
    assert client.post('/api/pc/configurar', json={'modulo': 'servidor'}).status_code == 200
    assert _modulo_del_pc(client, '127.0.0.1') == 'servidor'


def test_con_sesion_admin_otro_equipo_puede_ser_servidor(app, admin_client):
    _activar_gate(app)
    r = admin_client.post('/api/pc/configurar', json={'modulo': 'servidor'}, **_desde(IP_PLANTA))
    assert r.status_code == 200
    assert admin_client.get('/modules', **_desde(IP_PLANTA)).status_code == 200


def test_la_cookie_firmada_sobrevive_a_un_cambio_de_ip(admin_client):
    admin_client.post('/api/pc/configurar', json={'modulo': 'servidor'}, **_desde(IP_PLANTA))
    assert _modulo_del_pc(admin_client, OTRA_IP_PLANTA) == 'servidor'


def test_una_firma_inventada_no_vale(client):
    client.set_cookie('pc_modulo', 'servidor')
    client.set_cookie('pc_servidor', 'InNlcnZpZG9yIg.firma-falsa')
    assert _modulo_del_pc(client, IP_PLANTA) is None


def test_x_forwarded_for_no_suplanta_la_ip_del_servidor(app, client):
    client.post('/api/pc/configurar', json={'modulo': 'servidor'})   # anota 127.0.0.1
    intruso = app.test_client()
    suplantada = {'X-Forwarded-For': '127.0.0.1'}
    assert _modulo_del_pc(intruso, IP_PLANTA, headers=suplantada) is None
    r = intruso.post('/api/pc/configurar', json={'modulo': 'servidor'},
                     headers=suplantada, **_desde(IP_PLANTA))
    assert r.status_code == 401


def test_con_proxy_declarado_si_se_usa_x_forwarded_for(app, client):
    """PythonAnywhere: sin la cabecera todos los clientes serían la IP del proxy."""
    app.config['CONFIAR_PROXY'] = True
    cabecera = {'X-Forwarded-For': f'{IP_PLANTA}, 10.0.0.1'}
    client.post('/api/pc/configurar', json={'modulo': 'manguitos'},
                headers=cabecera, **_desde('10.0.0.1'))
    otro = app.test_client()
    assert _modulo_del_pc(otro, '10.0.0.1', headers=cabecera) == 'manguitos'
    assert _modulo_del_pc(otro, '10.0.0.1') is None
