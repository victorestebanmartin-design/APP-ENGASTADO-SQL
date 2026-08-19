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
    # Sin nada asignado, la propuesta arranca al principio del bloque display
    assert admin_client.get('/api/esp32/ips').get_json()['sugerida'] == '192.168.50.100'
    _asignar(admin_client, 'aaa1', '192.168.50.101')
    _asignar(admin_client, 'aaa2', '192.168.50.100')
    d = admin_client.get('/api/esp32/ips').get_json()
    assert [p['ip'] for p in d['placas']] == ['192.168.50.100', '192.168.50.101']
    assert d['sugerida'] == '192.168.50.102'


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
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x'})
    assert r.status_code == 400
    assert 'IP estática' in r.get_json()['message']


def test_flash_usb_rfid_rechaza_ip_fuera_de_rango(admin_client):
    r = admin_client.post('/api/esp32/rfid/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'ip_estatica': '192.168.50.300'})
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


# ── Que dos placas no puedan acabar con la misma IP ───────────────────────
#
# Paso de verdad: al flashear un lector no se pudo leer su MAC, la IP no se
# registro, y al flashear la siguiente placa el sistema volvio a ofrecer esa
# misma IP. Dos placas en 192.168.50.2 -> se pisan y parpadean.

def test_no_se_sugiere_una_ip_que_una_placa_ya_esta_usando(client, admin_client):
    """Aunque no haya fila en la BD: si una placa dice estar en esa IP, esta
    cogida. Mirar solo la BD fue justo el fallo."""
    client.get('/api/esp32/current?id=aabbccddee01&esp32_ip=192.168.50.100')
    assert admin_client.get('/api/esp32/ips').get_json()['sugerida'] == '192.168.50.101'


def test_la_ip_se_reserva_aunque_no_se_sepa_de_que_placa_es(admin_client):
    """Si al flashear no se pudo leer la MAC, la IP YA esta grabada en la
    placa: reservarla es obligatorio, o se le ofrece a la siguiente."""
    from app.routes import sistema
    with admin_client.application.test_request_context():
        ok, _ = sistema._ip_estatica_reservar_sin_placa('192.168.50.150', tipo='rfid')
    assert ok
    d = admin_client.get('/api/esp32/ips').get_json()
    assert d['sugeridas']['rfid'] == '192.168.50.151'
    reserva = next(p for p in d['placas'] if p['ip'] == '192.168.50.150')
    assert reserva['pendiente']


def test_la_reserva_se_retira_sola_al_identificar_la_placa(admin_client):
    """Cuando la placa aparece y se le asigna esa IP, la reserva a ciegas
    sobra: no puede quedarse ocupando sitio para siempre."""
    from app.routes import sistema
    with admin_client.application.test_request_context():
        sistema._ip_estatica_reservar_sin_placa('192.168.50.2', tipo='rfid')
    assert _asignar(admin_client, 'aabbccddee01', '192.168.50.2').get_json()['success']

    placas = admin_client.get('/api/esp32/ips').get_json()['placas']
    con_esa_ip = [p for p in placas if p['ip'] == '192.168.50.2']
    assert len(con_esa_ip) == 1 and con_esa_ip[0]['device_id'] == 'aabbccddee01'
    assert not con_esa_ip[0]['pendiente']


def test_se_avisa_cuando_dos_placas_dicen_tener_la_misma_ip(client, admin_client):
    """El sintoma en planta (placas parpadeando entre en linea y sin señal) es
    dificil de atribuir: hay que decirlo explicitamente."""
    client.get('/api/esp32/current?id=aabbccddee01&esp32_ip=192.168.50.2')
    client.get('/api/esp32/rfid/firmware/version?id=ffee00112233&ip=192.168.50.2&fw=x')

    d = admin_client.get('/api/esp32/ips').get_json()
    colisiones = d['colisiones']
    assert len(colisiones) == 1
    assert colisiones[0]['ip'] == '192.168.50.2'
    assert set(colisiones[0]['placas']) == {'aabbccddee01', 'ffee00112233'}
    assert all(p['colision'] for p in d['placas'] if p['ip_vista'] == '192.168.50.2')


def test_sin_colision_no_se_avisa_de_nada(client, admin_client):
    client.get('/api/esp32/current?id=aabbccddee01&esp32_ip=192.168.50.2')
    client.get('/api/esp32/rfid/firmware/version?id=ffee00112233&ip=192.168.50.3&fw=x')
    assert admin_client.get('/api/esp32/ips').get_json()['colisiones'] == []


# ── El control netsh del hotspot ya no existe ─────────────────────────────

def test_el_control_del_hotspot_por_netsh_ya_no_existe(admin_client):
    """La planta usa un punto de acceso fisico; ese mecanismo estaba obsoleto
    en Windows y solo podia dar problemas."""
    for ruta in ('/api/hotspot/estado',):
        assert admin_client.get(ruta).status_code == 404, ruta
    for ruta in ('/api/hotspot/iniciar', '/api/hotspot/detener'):
        assert admin_client.post(ruta).status_code == 404, ruta


def test_las_credenciales_wifi_siguen_guardandose(admin_client):
    """Eso si se queda: precarga los formularios de 'Subir por USB'."""
    assert admin_client.post('/api/hotspot/credenciales',
                             json={'ssid': 'TP-Link_5A40', 'password': 'x'}).get_json()['success']
    assert admin_client.get('/api/hotspot/credenciales').get_json()['ssid'] == 'TP-Link_5A40'


# ── Bloques por tipo de equipo ────────────────────────────────────────────
#
# Misma subred para todos (cambiar de subred romperia la red: el AP es un
# puente, no enruta). Los bloques son solo una convencion para saber que es
# cada equipo y no pisarse.

def test_cada_tipo_se_sugiere_dentro_de_su_bloque(admin_client):
    d = admin_client.get('/api/esp32/ips').get_json()
    assert d['sugeridas']['pc'] == '192.168.50.10'
    assert d['sugeridas']['display'] == '192.168.50.100'
    assert d['sugeridas']['rfid'] == '192.168.50.150'


def test_la_sugerencia_avanza_dentro_del_bloque(admin_client):
    _asignar(admin_client, 'disp1', '192.168.50.100', tipo='display')
    _asignar(admin_client, 'disp2', '192.168.50.101', tipo='display')
    d = admin_client.get('/api/esp32/ips').get_json()
    assert d['sugeridas']['display'] == '192.168.50.102'
    # Y no invade el bloque de otro tipo
    assert d['sugeridas']['rfid'] == '192.168.50.150'


def test_una_ip_fuera_de_su_bloque_se_acepta_pero_se_marca(admin_client):
    """No puede ser una camisa de fuerza: las placas ya flasheadas en .2/.3
    tienen que seguir funcionando y solo verse como pendientes de ordenar."""
    assert _asignar(admin_client, 'disp1', '192.168.50.2', tipo='display').get_json()['success']
    placa = next(p for p in admin_client.get('/api/esp32/ips').get_json()['placas']
                 if p['device_id'] == 'disp1')
    assert placa['fuera_de_bloque']


def test_dentro_del_bloque_no_se_marca(admin_client):
    _asignar(admin_client, 'disp1', '192.168.50.100', tipo='display')
    placa = next(p for p in admin_client.get('/api/esp32/ips').get_json()['placas']
                 if p['device_id'] == 'disp1')
    assert not placa['fuera_de_bloque']


# ── PCs de puesto ─────────────────────────────────────────────────────────

def test_un_pc_aparece_solo_al_hablar_con_el_servidor(client, admin_client):
    """La IP se detecta de la direccion de origen; no hay que apuntarla."""
    client.get('/api/operarios/logins', environ_overrides={'REMOTE_ADDR': '192.168.50.21'})
    pcs = [p for p in admin_client.get('/api/esp32/ips').get_json()['placas'] if p['tipo'] == 'pc']
    assert len(pcs) == 1 and pcs[0]['ip_vista'] == '192.168.50.21'


def test_al_pc_se_le_puede_poner_nombre_y_reservar_su_ip(client, admin_client):
    client.get('/api/operarios/logins', environ_overrides={'REMOTE_ADDR': '192.168.50.21'})
    pc = next(p for p in admin_client.get('/api/esp32/ips').get_json()['placas'] if p['tipo'] == 'pc')

    r = admin_client.post('/api/esp32/ips', json={'device_id': pc['device_id'],
                                                  'ip': '192.168.50.21', 'tipo': 'pc',
                                                  'nombre': 'PC PUNTERAS'})
    assert r.get_json()['success']
    d = admin_client.get('/api/esp32/ips').get_json()
    guardado = next(p for p in d['placas'] if p['device_id'] == pc['device_id'])
    assert guardado['nombre'] == 'PC PUNTERAS' and guardado['ip'] == '192.168.50.21'
    # Y a partir de ahi esa IP ya no se ofrece a nadie
    assert d['sugeridas']['pc'] != '192.168.50.21'


def test_no_se_registran_ips_de_fuera_de_la_red_de_planta(client, admin_client):
    """Un navegador de otra red (o localhost en pruebas) no es un PC de puesto."""
    client.get('/api/operarios/logins', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    client.get('/api/operarios/logins', environ_overrides={'REMOTE_ADDR': '10.0.0.5'})
    assert [p for p in admin_client.get('/api/esp32/ips').get_json()['placas']
            if p['tipo'] == 'pc'] == []


def test_el_servidor_y_el_ap_no_se_registran_como_pc(client, admin_client):
    for ip in ('192.168.50.1', '192.168.50.5'):
        client.get('/api/operarios/logins', environ_overrides={'REMOTE_ADDR': ip})
    assert [p for p in admin_client.get('/api/esp32/ips').get_json()['placas']
            if p['tipo'] == 'pc'] == []
