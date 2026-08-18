"""Host del servidor inyectado en el firmware de las placas.

La red de planta cambio de 192.168.1.x a 192.168.50.x: si el firmware se
sirve con el host del repo, la placa conecta al WiFi pero no encuentra al
servidor y nunca aparece en el admin.
"""


def _fijar_host(admin_client, host):
    return admin_client.post('/api/esp32/servidor', json={'host': host})


# ── Ajuste global ─────────────────────────────────────────────────────────

def test_host_se_guarda_y_se_devuelve(admin_client):
    assert _fijar_host(admin_client, '192.168.50.1').get_json()['success']
    assert admin_client.get('/api/esp32/servidor').get_json()['host'] == '192.168.50.1'


def test_host_admite_nombre_dns(admin_client):
    # El respaldo en PythonAnywhere es un nombre, no una IP
    assert _fijar_host(admin_client, 'viktor85.pythonanywhere.com').get_json()['success']


def test_host_invalido_se_rechaza(admin_client):
    for host in ('', '192.168.50.999', 'espacios no valen', 'http://192.168.50.1'):
        assert _fijar_host(admin_client, host).status_code == 400, host


def test_host_requiere_admin(client):
    assert client.get('/api/esp32/servidor').status_code == 401
    assert client.post('/api/esp32/servidor', json={'host': '192.168.50.1'}).status_code == 401


def test_sugerido_cae_en_lo_guardado(admin_client):
    _fijar_host(admin_client, '192.168.50.7')
    assert admin_client.get('/api/esp32/servidor').get_json()['sugerido'] == '192.168.50.7'


# ── Inyeccion en el OTA de la pantalla ────────────────────────────────────

def test_ota_pantalla_sirve_el_host_configurado(admin_client, client):
    _fijar_host(admin_client, '192.168.50.1')
    texto = client.get('/api/esp32/firmware/file?name=app.py').data.decode('utf-8')
    assert 'HOST_IP  = ' not in texto or "HOST_IP = '192.168.50.1'" in texto
    assert "HOST_IP = '192.168.50.1'" in texto


def test_ota_pantalla_manifiesto_cuadra_con_lo_servido(admin_client, client):
    """El sha256 del manifiesto tiene que ser el del contenido YA inyectado:
    si no, la placa descarga, no le cuadra el hash y no actualiza nunca."""
    import hashlib
    _fijar_host(admin_client, '192.168.50.1')
    manifest = client.get('/api/esp32/firmware/version').get_json()['files']
    entrada = next(f for f in manifest if f['name'] == 'app.py')
    r = client.get('/api/esp32/firmware/file?name=app.py')
    assert hashlib.sha256(r.data).hexdigest() == entrada['sha256']
    assert len(r.data) == entrada['size']
    assert r.headers['X-SHA256'] == entrada['sha256']


# ── Inyeccion en el OTA del lector RFID ───────────────────────────────────

def test_ota_rfid_sirve_el_host_configurado(admin_client, client):
    _fijar_host(admin_client, '192.168.50.1')
    texto = client.get('/api/esp32/rfid/firmware/file?name=backend_config.py').data.decode('utf-8')
    assert "BACKEND_HOST = '192.168.50.1'" in texto


def test_ota_rfid_manifiesto_cuadra_con_lo_servido(admin_client, client):
    import hashlib
    _fijar_host(admin_client, '192.168.50.1')
    manifest = client.get('/api/esp32/rfid/firmware/version').get_json()['files']
    entrada = next(f for f in manifest if f['name'] == 'backend_config.py')
    r = client.get('/api/esp32/rfid/firmware/file?name=backend_config.py')
    assert hashlib.sha256(r.data).hexdigest() == entrada['sha256']
    assert len(r.data) == entrada['size']


def test_cambiar_el_host_cambia_lo_que_se_sirve(admin_client, client):
    """Un OTA posterior no puede revertir el host al literal del repo."""
    _fijar_host(admin_client, '192.168.50.1')
    primero = client.get('/api/esp32/rfid/firmware/file?name=backend_config.py').data
    _fijar_host(admin_client, '192.168.50.9')
    segundo = client.get('/api/esp32/rfid/firmware/file?name=backend_config.py').data
    assert b"'192.168.50.9'" in segundo and primero != segundo


def test_ficheros_sin_host_se_sirven_intactos(admin_client, client):
    """Solo se tocan app.py y backend_config.py; los lib/*.py van tal cual."""
    import os
    _fijar_host(admin_client, '192.168.50.1')
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, 'esp32', 'lib', 'mfrc522.py'), 'rb') as f:
        en_disco = f.read()
    servido = client.get('/api/esp32/rfid/firmware/file?name=mfrc522.py').data
    assert servido == en_disco


# ── Flasheo por USB ───────────────────────────────────────────────────────

def test_flash_usb_display_rechaza_host_invalido(admin_client):
    r = admin_client.post('/api/esp32/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'ip_estatica': '192.168.50.21',
                                'host_servidor': 'no vale esto'})
    assert r.status_code == 400
    assert 'servidor' in r.get_json()['message']


def test_flash_usb_rfid_rechaza_host_invalido(admin_client):
    r = admin_client.post('/api/esp32/rfid/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'webrepl_password': 'y', 'ip_estatica': '192.168.50.21',
                                'host_servidor': '192.168.50.999'})
    assert r.status_code == 400


# ── El repo no puede volver a llevar la red vieja ─────────────────────────

def test_el_repo_no_apunta_a_la_red_antigua():
    """192.168.1.20 era el servidor de la red anterior. Si vuelve a colarse
    como valor por defecto, una placa flasheada a mano queda muda."""
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ('esp32/micropython/main_wifi.py', 'esp32/backend_config.py',
                'esp32/wifi_config.py'):
        with open(os.path.join(base, rel), encoding='utf-8') as f:
            assert '192.168.1.20' not in f.read(), rel
