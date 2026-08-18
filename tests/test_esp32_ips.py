"""IP estática por placa ESP32 (red de planta 192.168.50.0/24 sin DHCP)."""


def _asignar(admin_client, device_id, ip, tipo='display'):
    return admin_client.post('/api/esp32/ips', json={
        'device_id': device_id, 'ip': ip, 'tipo': tipo})


# ── Validación del rango ──────────────────────────────────────────────────

def test_ip_dentro_del_rango_se_acepta(admin_client):
    assert _asignar(admin_client, 'aabbcc', '192.168.50.2').get_json()['success']
    assert _asignar(admin_client, 'ddeeff', '192.168.50.254').get_json()['success']


def test_ip_fuera_de_la_subred_se_rechaza(admin_client):
    for ip in ('192.168.1.20', '10.0.0.5', '192.168.51.7'):
        r = _asignar(admin_client, 'aabbcc', ip)
        assert r.status_code == 400, ip
        assert not r.get_json()['success']


def test_ip_fuera_del_rango_util_se_rechaza(admin_client):
    # .0 es la red y .255 el broadcast: ninguno vale para una placa
    for ip in ('192.168.50.0', '192.168.50.255', '192.168.50.300'):
        assert _asignar(admin_client, 'aabbcc', ip).status_code == 400, ip


def test_ip_no_ipv4_se_rechaza(admin_client):
    for ip in ('', 'no-es-una-ip', '192.168.50', '192.168.50.5.7'):
        assert _asignar(admin_client, 'aabbcc', ip).status_code == 400, ip


def test_ips_reservadas_se_rechazan(admin_client):
    # .1 = PC servidor, .5 = punto de acceso TL-WR802N
    for ip in ('192.168.50.1', '192.168.50.5'):
        r = _asignar(admin_client, 'aabbcc', ip)
        assert r.status_code == 400
        assert 'reservada' in r.get_json()['message']


# ── Unicidad entre placas ─────────────────────────────────────────────────

def test_ip_repetida_entre_placas_se_rechaza(admin_client):
    assert _asignar(admin_client, 'aabbcc', '192.168.50.21').get_json()['success']
    r = _asignar(admin_client, 'ddeeff', '192.168.50.21')
    assert r.status_code == 400
    assert 'ya está asignada' in r.get_json()['message']


def test_reasignar_la_misma_ip_a_la_misma_placa_vale(admin_client):
    # Reflashear una placa con su IP de siempre no es un duplicado
    assert _asignar(admin_client, 'aabbcc', '192.168.50.21').get_json()['success']
    assert _asignar(admin_client, 'aabbcc', '192.168.50.21').get_json()['success']


def test_liberar_una_ip_la_deja_disponible(admin_client):
    _asignar(admin_client, 'aabbcc', '192.168.50.21')
    assert admin_client.delete('/api/esp32/ips/aabbcc').get_json()['success']
    assert _asignar(admin_client, 'ddeeff', '192.168.50.21').get_json()['success']


def test_cambiar_la_ip_de_una_placa_libera_la_anterior(admin_client):
    _asignar(admin_client, 'aabbcc', '192.168.50.21')
    assert _asignar(admin_client, 'aabbcc', '192.168.50.22').get_json()['success']
    assert _asignar(admin_client, 'ddeeff', '192.168.50.21').get_json()['success']


# ── Listado ───────────────────────────────────────────────────────────────

def test_listado_requiere_admin(client):
    assert client.get('/api/esp32/ips').status_code == 401
    assert client.post('/api/esp32/ips', json={'device_id': 'aabbcc',
                                               'ip': '192.168.50.21'}).status_code == 401
    assert client.delete('/api/esp32/ips/aabbcc').status_code == 401


def test_listado_devuelve_placas_y_parametros_de_red(admin_client):
    _asignar(admin_client, 'aabbcc', '192.168.50.21', tipo='rfid')
    d = admin_client.get('/api/esp32/ips').get_json()
    assert d['red']['mascara'] == '255.255.255.0'
    assert d['red']['gateway'] == '192.168.50.5'
    assert d['red']['dns'] == '192.168.50.5'
    placa = next(p for p in d['placas'] if p['device_id'] == 'aabbcc')
    assert placa['ip'] == '192.168.50.21'
    assert placa['tipo'] == 'rfid'


def test_listado_ordena_por_ip_y_sugiere_la_primera_libre(admin_client):
    assert admin_client.get('/api/esp32/ips').get_json()['sugerida'] == '192.168.50.2'
    _asignar(admin_client, 'aaa1', '192.168.50.3')
    _asignar(admin_client, 'aaa2', '192.168.50.2')
    d = admin_client.get('/api/esp32/ips').get_json()
    assert [p['ip'] for p in d['placas']] == ['192.168.50.2', '192.168.50.3']
    # .4 es la siguiente libre (.1 y .5 están reservadas)
    assert d['sugerida'] == '192.168.50.4'


def test_listado_incluye_placas_detectadas_sin_ip(client, admin_client):
    client.get('/api/esp32/current?id=aabbcc')     # la pantalla se registra sola
    d = admin_client.get('/api/esp32/ips').get_json()
    placa = next(p for p in d['placas'] if p['device_id'] == 'aabbcc')
    assert placa['ip'] == '' and placa['detectada'] and placa['tipo'] == 'display'


def test_devices_expone_la_ip_estatica(client, admin_client):
    client.get('/api/esp32/current?id=aabbcc')
    _asignar(admin_client, 'aabbcc', '192.168.50.21')
    dev = next(x for x in admin_client.get('/api/esp32/devices').get_json()['devices']
               if x['id'] == 'aabbcc')
    assert dev['ip_estatica'] == '192.168.50.21'


# ── Flasheo por USB ───────────────────────────────────────────────────────

def test_flash_usb_display_exige_ip_estatica(admin_client):
    r = admin_client.post('/api/esp32/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x'})
    assert r.status_code == 400
    assert 'IP estática' in r.get_json()['message']


def test_flash_usb_display_rechaza_ip_invalida(admin_client):
    r = admin_client.post('/api/esp32/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'ip_estatica': '192.168.50.1'})
    assert r.status_code == 400
    assert 'reservada' in r.get_json()['message']


def test_flash_usb_rfid_exige_ip_estatica(admin_client):
    r = admin_client.post('/api/esp32/rfid/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'webrepl_password': 'y'})
    assert r.status_code == 400
    assert 'IP estática' in r.get_json()['message']


def test_flash_usb_rfid_rechaza_ip_fuera_de_rango(admin_client):
    r = admin_client.post('/api/esp32/rfid/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'webrepl_password': 'y', 'ip_estatica': '192.168.50.300'})
    assert r.status_code == 400
    assert '192.168.50.254' in r.get_json()['message']


def test_flash_usb_valida_la_ip_antes_de_tocar_la_placa(admin_client):
    """Una IP mala se rechaza sin llegar a mpremote: si no, la placa se
    quedaria a medio flashear por un error que se ve de antemano."""
    r = admin_client.post('/api/esp32/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'ip_estatica': '10.0.0.9'})
    assert r.status_code == 400
    # El mensaje es el de la IP, no el de "no se encuentra mpremote/el puerto"
    assert 'red de planta' in r.get_json()['message']


# ── Firmware: el bloque que se graba en la placa ──────────────────────────

def test_el_firmware_aplica_la_ip_antes_de_conectar():
    """boot.py (RFID) y main_wifi.py (pantalla) deben llamar a ifconfig()
    ANTES de connect(): al reves, la placa ya habria intentado conectar por
    DHCP en una red que no lo tiene."""
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for ruta in (os.path.join(base, 'esp32', 'boot.py'),
                 os.path.join(base, 'esp32', 'micropython', 'main_wifi.py')):
        with open(ruta, encoding='utf-8') as f:
            texto = f.read()
        assert 'ifconfig((' in texto, ruta
        assert texto.index('ifconfig((') < texto.index('.connect(SSID') if 'connect(SSID' in texto \
            else texto.index('ifconfig((') < texto.index('.connect(cfg.SSID')


def test_la_config_del_firmware_lleva_mascara_y_gateway_fijos():
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for ruta in (os.path.join(base, 'esp32', 'wifi_config.py'),
                 os.path.join(base, 'esp32', 'micropython', 'main_wifi.py')):
        with open(ruta, encoding='utf-8') as f:
            texto = f.read()
        assert '"255.255.255.0"' in texto, ruta
        assert '"192.168.50.5"' in texto, ruta


# ── Migración sobre una BD ya existente ───────────────────────────────────

def test_migracion_crea_la_tabla_en_una_bd_antigua(tmp_path):
    """Una instalación en marcha no recrea la BD desde schema_sqlite.sql:
    la tabla tiene que aparecer por la migración de app/__init__.py."""
    import sqlite3
    from app import _apply_migrations
    from conftest import _crear_bd_temporal

    db_path = str(tmp_path / 'antigua.db')
    _crear_bd_temporal(db_path)
    # Estado de una instalación anterior a este cambio: todo lo demás está,
    # esp32_ips no.
    conn = sqlite3.connect(db_path)
    conn.execute('DROP TABLE IF EXISTS esp32_ips')
    conn.commit()
    conn.close()

    _apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    tablas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'esp32_ips' in tablas
    # El UNIQUE de la IP tiene que estar: es la última red que impide que dos
    # placas acaben con la misma dirección.
    conn.execute("INSERT INTO esp32_ips (device_id, tipo, ip) VALUES ('a', 'rfid', '192.168.50.21')")
    try:
        conn.execute("INSERT INTO esp32_ips (device_id, tipo, ip) VALUES ('b', 'rfid', '192.168.50.21')")
        assert False, 'el UNIQUE de la IP no está aplicado'
    except sqlite3.IntegrityError:
        pass
    conn.close()
