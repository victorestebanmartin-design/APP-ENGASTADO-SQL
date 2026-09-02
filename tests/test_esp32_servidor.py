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
                                'ip_estatica': '192.168.50.21',
                                'host_servidor': '192.168.50.999'})
    assert r.status_code == 400


def test_flash_usb_rfid_rechaza_perfil_desconocido(admin_client):
    r = admin_client.post('/api/esp32/rfid/flash_usb',
                          json={'puerto': 'COM5', 'perfil': 'placa_inventada',
                                'ssid': 'COJO', 'ip_estatica': '192.168.50.21'})
    assert r.status_code == 400
    assert 'Perfil' in r.get_json()['message']


def test_flash_usb_rfid_rechaza_orientacion_desconocida(admin_client):
    r = admin_client.post('/api/esp32/rfid/flash_usb',
                          json={'puerto': 'COM5', 'perfil': 'gen4_pn532',
                                'orientacion': '90', 'ssid': 'COJO',
                                'ip_estatica': '192.168.50.21'})
    assert r.status_code == 400
    assert 'Orientación' in r.get_json()['message']


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


# ── Reintentos de mpremote ────────────────────────────────────────────────
#
# "could not enter raw repl" no es un fallo de cable: la placa esta ocupada
# (boot.py bloquea ~12s con el WiFi, main.py hace un OTA cada minuto) y no
# atiende el Ctrl-C con el que mpremote entra en la consola.

class _Resultado:
    def __init__(self, returncode, stderr=''):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ''


def test_insiste_mientras_la_placa_este_ocupada(monkeypatch):
    from app.routes import sistema

    monkeypatch.setattr(sistema.time, 'sleep', lambda _: None)
    intentos = []

    def mpremote(*args):
        intentos.append(args)
        # Ocupada las tres primeras veces, libre a la cuarta
        if len(intentos) < 4:
            return _Resultado(1, 'mpremote.transport.TransportError: could not enter raw repl')
        return _Resultado(0)

    r = sistema._mpremote_insistiendo(mpremote, 'cp', 'x', ':x')
    assert r.returncode == 0
    assert len(intentos) == 4


def test_no_insiste_con_un_error_de_verdad(monkeypatch):
    """Un fallo que no se arregla esperando no debe multiplicar la espera."""
    from app.routes import sistema

    monkeypatch.setattr(sistema.time, 'sleep', lambda _: None)
    intentos = []

    def mpremote(*args):
        intentos.append(args)
        return _Resultado(1, 'No module named mpremote')

    r = sistema._mpremote_insistiendo(mpremote, 'cp', 'x', ':x')
    assert r.returncode == 1
    assert len(intentos) == 1


def test_se_rinde_y_devuelve_el_ultimo_fallo(monkeypatch):
    from app.routes import sistema

    monkeypatch.setattr(sistema.time, 'sleep', lambda _: None)
    intentos = []

    def mpremote(*args):
        intentos.append(args)
        return _Resultado(1, 'could not enter raw repl')

    r = sistema._mpremote_insistiendo(mpremote, 'cp', 'x', ':x')
    assert r.returncode == 1
    assert len(intentos) == 1 + len(sistema._MPREMOTE_ESPERAS)


def test_el_error_lleva_un_consejo_accionable():
    from app.routes import sistema
    consejo = sistema._consejo_placa_ocupada('TransportError: could not enter raw repl')
    assert 'monitor serie' in consejo
    # Otros errores no llevan ese consejo, que no vendria a cuento
    assert sistema._consejo_placa_ocupada('No such file') == ''


# ── WebREPL apagado por defecto ───────────────────────────────────────────

def test_flash_rfid_ya_no_exige_webrepl(admin_client):
    """Se quito del formulario: sin el, la validacion debe pasar de largo y
    fallar por otra cosa (el puerto), no por la contrasena que ya no se pide."""
    r = admin_client.post('/api/esp32/rfid/flash_usb',
                          json={'puerto': 'COM5', 'ssid': 'COJO', 'password': 'x',
                                'ip_estatica': '192.168.50.21',
                                'host_servidor': '192.168.50.1'})
    assert 'WebREPL' not in (r.get_json().get('message') or '')


def test_el_firmware_no_arranca_webrepl_sin_contrasena():
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, 'esp32', 'boot.py'), encoding='utf-8') as f:
        boot = f.read()
    # El import de webrepl tiene que quedar DENTRO del if de la contrasena
    assert 'if getattr(cfg, "WEBREPL_PASSWORD", "")' in boot
    assert boot.index('WEBREPL_PASSWORD') < boot.index('import webrepl')
    with open(os.path.join(base, 'esp32', 'wifi_config.py'), encoding='utf-8') as f:
        assert 'WEBREPL_PASSWORD = ""' in f.read()


# ── Resetear la placa cuando no atiende ───────────────────────────────────
#
# El lector RFID pasa hasta 15s dentro de una lectura de socket bloqueada
# (comprobacion OTA con el servidor inalcanzable) y ahi no atiende el Ctrl-C
# con el que mpremote entra. Esperar puede no bastar; resetearla, si.

def test_ante_un_fallo_transitorio_se_resetea_la_placa(monkeypatch):
    from app.routes import sistema

    monkeypatch.setattr(sistema.time, 'sleep', lambda _: None)
    reseteos = []
    monkeypatch.setattr(sistema, '_interrumpir_placa',
                        lambda puerto: reseteos.append(puerto) or True)

    intentos = []

    def mpremote(*args):
        intentos.append(args)
        if len(intentos) < 3:
            return _Resultado(1, 'could not enter raw repl')
        return _Resultado(0)

    r = sistema._mpremote_insistiendo(mpremote, 'cp', 'x', ':x', puerto='COM3')
    assert r.returncode == 0
    assert reseteos == ['COM3', 'COM3']      # uno antes de cada reintento


def test_sin_puerto_no_se_intenta_resetear(monkeypatch):
    """Los tests y las llamadas sin puerto no deben tocar ningun serie."""
    from app.routes import sistema

    monkeypatch.setattr(sistema.time, 'sleep', lambda _: None)
    def _explota(puerto):
        raise AssertionError('no deberia resetear sin puerto')
    monkeypatch.setattr(sistema, '_interrumpir_placa', _explota)

    r = sistema._mpremote_insistiendo(lambda *a: _Resultado(1, 'could not enter raw repl'),
                                      'cp', 'x', ':x')
    assert r.returncode == 1


def test_interrumpir_placa_no_revienta_sin_puerto(monkeypatch):
    """Mejor esfuerzo: si el puerto no se deja abrir, se sigue igual."""
    from app.routes import sistema
    assert sistema._interrumpir_placa('/dev/no-existe-este-puerto') is False


def test_interrumpir_placa_manda_ctrl_c_aunque_no_haya_dtr_rts():
    """Un pty no deja tocar DTR/RTS, igual que algunos puentes USB-serie
    reales. El reset por hardware es un extra: el Ctrl-C tiene que salir
    igualmente, que es lo que para una placa que esta en un time.sleep()."""
    import os
    import pty
    import threading
    import time as _t
    import pytest
    from app.routes import sistema

    if not hasattr(pty, 'openpty'):
        pytest.skip('sin pty en esta plataforma')

    maestro, esclavo = pty.openpty()
    recibido = bytearray()
    parar = threading.Event()

    def leer():
        while not parar.is_set():
            try:
                trozo = os.read(maestro, 1024)
            except OSError:
                break
            if trozo:
                recibido.extend(trozo)

    hilo = threading.Thread(target=leer, daemon=True)
    hilo.start()
    try:
        assert sistema._interrumpir_placa(os.ttyname(esclavo)) is True
    finally:
        parar.set()
        os.close(maestro)
        os.close(esclavo)

    assert recibido.count(b'\x03') > 10        # Ctrl-C repetido, no uno suelto
    assert set(recibido) == {3}                # y nada mas en la linea


def test_el_consejo_manda_a_borrar_micropython():
    """Cuando ni reseteando se entra, la salida garantizada es dejar la placa
    sin nada ejecutandose (esptool), no seguir peleando con mpremote."""
    from app.routes import sistema
    consejo = sistema._consejo_placa_ocupada('could not enter raw repl')
    assert 'Borrar y grabar MicroPython' in consejo
