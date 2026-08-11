"""OTA de aplicación del ESP32 por WiFi (manifiesto, ficheros y disparo)."""


def _version_servidor(client):
    return client.get('/api/esp32/firmware/version').get_json()['version']


def test_firmware_version_y_manifiesto(client):
    d = client.get('/api/esp32/firmware/version').get_json()
    assert d['version']            # FW_VERSION declarada en main_wifi.py
    nombres = [f['name'] for f in d['files']]
    assert 'app.py' in nombres
    main = next(f for f in d['files'] if f['name'] == 'app.py')
    assert main['size'] > 0 and len(main['sha256']) == 64


def test_firmware_file_sirve_bytes_con_sha(client):
    manifest = client.get('/api/esp32/firmware/version').get_json()['files']
    main = next(f for f in manifest if f['name'] == 'app.py')
    r = client.get('/api/esp32/firmware/file?name=app.py')
    assert r.status_code == 200
    assert len(r.data) == main['size']
    assert r.headers.get('X-SHA256') == main['sha256']


def test_firmware_file_nombre_invalido(client):
    assert client.get('/api/esp32/firmware/file?name=../config.py').status_code == 404
    assert client.get('/api/esp32/firmware/file?name=noexiste.py').status_code == 404


def test_ota_requiere_admin(client):
    client.get('/api/esp32/current?id=aabbcc')   # registra la pantalla
    assert client.post('/api/esp32/devices/aabbcc/ota').status_code == 401


def test_ota_pedido_se_ofrece_y_se_limpia(client, admin_client):
    client.get('/api/esp32/current?id=aabbcc&fw=vieja-0.0')
    assert admin_client.post('/api/esp32/devices/aabbcc/ota').get_json()['success']

    ver = _version_servidor(client)
    # La pantalla, aún con versión vieja, recibe la orden de actualizar
    d = client.get('/api/esp32/current?id=aabbcc&fw=vieja-0.0').get_json()
    assert d['ota'] and d['ota']['update'] and d['ota']['version'] == ver
    assert any(f['name'] == 'app.py' for f in d['ota']['files'])

    # Cuando reporta ya la versión nueva, se limpia y deja de ofrecerse
    d2 = client.get(f'/api/esp32/current?id=aabbcc&fw={ver}').get_json()
    assert d2['ota'] is None
    d3 = client.get(f'/api/esp32/current?id=aabbcc&fw={ver}').get_json()
    assert d3['ota'] is None


def test_ota_device_inexistente(admin_client):
    assert admin_client.post('/api/esp32/devices/nadie/ota').status_code == 404


def test_devices_incluye_fw_y_version(client, admin_client):
    client.get('/api/esp32/current?id=aabbcc&fw=vieja-0.0')
    d = admin_client.get('/api/esp32/devices').get_json()
    assert d['firmware_version'] == _version_servidor(client)
    dev = next(x for x in d['devices'] if x['id'] == 'aabbcc')
    assert dev['fw'] == 'vieja-0.0'
