"""Pick-to-light de gavetas.

Lo que se prueba aquí, sobre todo, es que el sistema DEGRADA bien: sin tira de
LEDs, sin lector asignado o con la placa desenchufada, engastado tiene que
seguir llegando a los paquetes. Un fallo de la bombilla no puede parar a nadie.

El hardware real no está en CI, así que el envío a la placa se sustituye por
un doble que registra lo que se le manda (ver _sin_placa / _con_placa).
"""
import json
import os

import pytest

from app.routes import pick_to_light


@pytest.fixture
def sin_placa(monkeypatch):
    """La placa no contesta: es el caso de 'engastado sigue igual'."""
    enviados = []

    def _falso(ip, payload, timeout=None):
        enviados.append((ip, payload))
        return False, 'La placa de las gavetas no responde'

    monkeypatch.setattr(pick_to_light, '_enviar_a_placa', _falso)
    return enviados


@pytest.fixture
def con_placa(monkeypatch):
    """La placa contesta que sí a todo."""
    enviados = []

    def _falso(ip, payload, timeout=None):
        enviados.append((ip, payload))
        return True, ''

    monkeypatch.setattr(pick_to_light, '_enviar_a_placa', _falso)
    return enviados


def _registrar_lector(app, device_id='aabbccddeeff', puesto_id='puesto_001', ip='192.168.50.151',
                      gavetas=0):
    """Deja un lector RFID asignado a un puesto, como haría Admin."""
    ruta = os.path.join(app.config['DATA_DIR'], 'esp32_rfid_devices.json')
    dispositivo = {'ip': ip, 'puesto_id': puesto_id, 'puesto_nombre': 'TERMINALES AMP'}
    if gavetas:
        dispositivo['gavetas'] = gavetas
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({device_id: dispositivo}, f)
    return device_id


def _asignar_terminal_a_maquina(app, terminal, puesto_id='puesto_001', maquina_id='maquina_001'):
    """Deja un terminal colgado de una máquina de un puesto, como en producción.

    Hace falta para que _gavetas_validas_del_puesto lo encuentre: sin esta
    asignación, terminales_gavetas por sí sola no dice a qué puesto pertenece
    el terminal.
    """
    from repositories.puesto_repository import PuestoRepository
    from repositories.maquina_repository import MaquinaRepository
    from app.routes.base import db
    with app.app_context():
        pr = PuestoRepository(db)
        if not pr.obtener_puesto(puesto_id):
            pr.crear_puesto(puesto_id, puesto_id)
        mr = MaquinaRepository(db)
        if not mr.obtener_maquina(maquina_id):
            mr.crear_maquina(maquina_id, puesto_id, maquina_id)
        mr.asignar_terminal(maquina_id, terminal)


# ── La columna 'led' ─────────────────────────────────────────────────────────

def test_gaveta_guarda_y_devuelve_el_numero_de_led(admin_client):
    r = admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    assert r.status_code == 200 and r.get_json()['led'] == 7

    r = admin_client.get('/api/terminal-gaveta/640204')
    datos = r.get_json()
    assert datos['gaveta'] == 'A-12' and datos['led'] == 7


def test_gaveta_sin_led_sigue_siendo_valida(admin_client):
    """Una instalación sin tira de LEDs guarda la gaveta como toda la vida."""
    r = admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'Estante 3-B'})
    assert r.status_code == 200
    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['led'] is None


def test_led_vacio_quita_la_luz_sin_borrar_la_gaveta(admin_client):
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': ''})
    datos = admin_client.get('/api/terminal-gaveta/640204').get_json()
    assert datos['gaveta'] == 'A-12' and datos['led'] is None


def test_led_fuera_de_rango_se_rechaza_con_motivo(admin_client):
    r = admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 999})
    assert r.status_code == 400
    assert 'entre 1 y' in r.get_json()['message']


def test_editar_solo_la_etiqueta_no_borra_el_led(admin_client):
    """Guardar sin mandar 'led' es cambiar el texto, no apagar la gaveta."""
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-13'})
    datos = admin_client.get('/api/terminal-gaveta/640204').get_json()
    assert datos['gaveta'] == 'A-13' and datos['led'] == 7


# ── Encender ─────────────────────────────────────────────────────────────────

def test_encender_manda_el_led_a_la_placa(app, client, admin_client, con_placa):
    _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200
    assert datos['activo'] is True and datos['led'] == 7 and datos['gaveta'] == 'A-12'
    # 640204 ya viene de fábrica asignado a una máquina de puesto_001 (semilla
    # de schema_sqlite.sql), así que 'validas' ya trae su propio led: ver
    # test_encender_manda_las_gavetas_validas_del_puesto para un puesto limpio.
    assert con_placa == [('192.168.50.151', {'led': 7, 'terminal': '640204', 'validas': [7]})]


def test_encender_manda_las_gavetas_validas_del_puesto(app, client, admin_client, con_placa):
    """La placa necesita saber qué canales tienen gaveta de verdad detrás.

    Un expansor MCP23017 trae 16 canales aunque solo se haya cableado un
    microinterruptor: sin esta lista, los canales sin cablear se leen como
    'fuera' permanentemente y se confunden con gavetas robadas. Usa un puesto
    y terminales propios (no los de la semilla de schema_sqlite.sql) para no
    depender de esos datos.
    """
    _registrar_lector(app, puesto_id='puesto_ptl_test')
    admin_client.put('/api/terminal-gaveta/ZZTEST1', json={'gaveta': 'A-1', 'led': 7})
    admin_client.put('/api/terminal-gaveta/ZZTEST2', json={'gaveta': 'A-2', 'led': 3})
    _asignar_terminal_a_maquina(app, 'ZZTEST1', puesto_id='puesto_ptl_test',
                                maquina_id='maquina_ptl_test')
    _asignar_terminal_a_maquina(app, 'ZZTEST2', puesto_id='puesto_ptl_test',
                                maquina_id='maquina_ptl_test')
    # Un terminal con gaveta pero de OTRO puesto no puede colarse en la lista.
    admin_client.put('/api/terminal-gaveta/ZZTEST3', json={'gaveta': 'B-1', 'led': 12})
    _asignar_terminal_a_maquina(app, 'ZZTEST3', puesto_id='puesto_ptl_otro',
                                maquina_id='maquina_ptl_otro')

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_ptl_test', 'terminal': 'ZZTEST1'})
    assert con_placa == [('192.168.50.151',
                          {'led': 7, 'terminal': 'ZZTEST1', 'validas': [3, 7]})]


def test_encender_un_terminal_sin_led_no_es_un_error(app, client, admin_client, con_placa):
    """Sin luz configurada la app tiene que seguir, avisando del motivo."""
    _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12'})

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200 and datos['success'] is True
    assert datos['activo'] is False and 'no tiene gaveta con luz' in datos['motivo']
    assert con_placa == []


def test_encender_sin_lector_asignado_no_es_un_error(client, admin_client, con_placa):
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200 and datos['activo'] is False
    assert 'lector asignado' in datos['motivo']


def test_encender_con_la_placa_caida_no_es_un_error(app, client, admin_client, sin_placa):
    _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200 and datos['success'] is True
    assert datos['activo'] is False and 'no responde' in datos['motivo']


def test_lector_tras_nat_puede_sondear_su_orden(app, client, admin_client, con_placa):
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden == {'success': True, 'apagar': False, 'led': 7, 'terminal': '640204', 'validas': [7]}

    client.post('/api/pick-to-light/apagar', json={'puesto_id': 'puesto_001'})
    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden == {'success': True, 'apagar': True, 'led': None, 'terminal': '', 'validas': []}


def test_pythonanywhere_espera_la_gaveta_por_sondeo(app, client, admin_client, sin_placa):
    _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    respuesta = client.post('/api/pick-to-light/encender',
                            json={'puesto_id': 'puesto_001', 'terminal': '640204'},
                            headers={'Host': 'viktor85.pythonanywhere.com'})
    datos = respuesta.get_json()
    assert datos['activo'] is True
    assert datos['motivo'] == 'La placa recibirá la orden por sondeo.'


def test_pythonanywhere_puede_probar_un_led_por_sondeo(app, client, admin_client, sin_placa, monkeypatch):
    device_id = _registrar_lector(app)
    monkeypatch.setattr(pick_to_light, '_backend_pythonanywhere', lambda: True)

    respuesta = admin_client.post('/api/pick-to-light/probar', json={'puesto_id': 'puesto_001', 'led': 5})
    assert respuesta.get_json() == {'success': True, 'message': 'La placa recibirá la orden por sondeo.'}

    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden == {'success': True, 'apagar': False, 'led': 5, 'terminal': '', 'validas': []}


def test_sondeo_reconfirma_recogida_si_se_pierde_el_aviso_post(app, client, admin_client, con_placa):
    """El GET periodico tiene que poder confirmar solo, sin depender del POST.

    El aviso normal (api_esp32_rfid_gaveta) es un POST suelto en el momento de
    sacar la gaveta: si se pierde por un handshake TLS lento o un corte breve
    de wifi, nadie lo reintenta. El sondeo de /orden si se repite cada 750 ms
    (ver lector_puesto.py), asi que reportar led/recogida tambien ahi tiene
    que bastar para que el operario no se quede esperando delante del cajon.
    """
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['recogida'] is False

    client.get('/api/esp32/rfid/gaveta/orden?device_id=%s&led=7&recogida=1' % device_id)

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['recogida'] is True


def test_sondeo_no_confirma_recogida_de_otro_led(app, client, admin_client, con_placa):
    """Un led distinto al objetivo actual no puede confirmar por error de sondeo."""
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    client.get('/api/esp32/rfid/gaveta/orden?device_id=%s&led=3&recogida=1' % device_id)

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['recogida'] is False


def test_encender_otro_terminal_borra_la_recogida_anterior(app, client, admin_client, con_placa):
    """Sin esto, el segundo terminal saltaría la puerta con la confirmación del primero."""
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    admin_client.put('/api/terminal-gaveta/640205', json={'gaveta': 'A-13', 'led': 8})

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})
    assert client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()['recogida'] is True

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640205'})
    assert client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()['recogida'] is False


# ── Lo que manda la placa ────────────────────────────────────────────────────

def test_la_gaveta_correcta_confirma_la_recogida(app, client, admin_client, con_placa):
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    r = client.post('/api/esp32/rfid/gaveta',
                    json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})
    assert r.status_code == 200

    datos = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert datos['recogida'] is True and datos['error_led'] is None


def test_la_gaveta_equivocada_se_marca_y_se_corrige(app, client, admin_client, con_placa):
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 3, 'fuera': True, 'resultado': 'equivocada'})
    datos = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert datos['error_led'] == 3 and datos['recogida'] is False

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 3, 'fuera': False, 'resultado': 'corregida'})
    assert client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()['error_led'] is None


def test_devolver_la_gaveta_correcta_se_marca_como_devuelta(app, client, admin_client, con_placa):
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})
    assert client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()['devuelta'] is False

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': False, 'resultado': 'devuelta'})
    assert client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()['devuelta'] is True


def test_sondeo_reconfirma_devolucion_si_se_pierde_el_aviso_post(app, client, admin_client, con_placa):
    """Igual que con la recogida: el GET periodico tiene que poder confirmar
    la devolucion por si solo, sin depender del POST suelto de 'devuelta'."""
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    client.get('/api/esp32/rfid/gaveta/orden?device_id=%s&led=7&recogida=1&puesta=0' % device_id)
    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['recogida'] is True and estado['devuelta'] is False

    client.get('/api/esp32/rfid/gaveta/orden?device_id=%s&led=7&recogida=1&puesta=1' % device_id)
    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['devuelta'] is True


def test_varias_gavetas_robadas_se_listan_todas(app, client, admin_client, con_placa):
    """Con dos cajones abiertos que no tocan hay que nombrar los dos."""
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    for robada in (3, 5):
        client.post('/api/esp32/rfid/gaveta',
                    json={'device_id': device_id, 'led': robada, 'fuera': True,
                          'resultado': 'equivocada'})
    assert client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()['intrusas'] == [3, 5]

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 3, 'fuera': False, 'resultado': 'corregida'})
    datos = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert datos['intrusas'] == [5] and datos['error_led'] == 5


def test_el_sondeo_manda_la_lista_entera_de_intrusas(app, client, admin_client, con_placa):
    """La placa es la que sabe la verdad: su lista sustituye a la guardada.

    Si solo se aplicaran los cambios sueltos, un aviso de 'corregida' perdido
    dejaria una gaveta intrusa fantasma avisando para siempre.
    """
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 3, 'fuera': True, 'resultado': 'equivocada'})

    client.get('/api/esp32/rfid/gaveta/orden?device_id=%s&led=7&recogida=1&intrusas=' % device_id)
    datos = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert datos['intrusas'] == [] and datos['error_led'] is None


def test_encender_manda_el_terminal_a_la_placa_para_el_display(app, client, admin_client, con_placa):
    _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    assert con_placa == [('192.168.50.151', {'led': 7, 'terminal': '640204', 'validas': [7]})]


def test_el_sondeo_devuelve_el_terminal_en_curso(app, client, admin_client, con_placa):
    """La placa tras NAT tambien tiene que poder escribirlo en su pantalla."""
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden['led'] == 7 and orden['terminal'] == '640204'


def test_el_aviso_deja_escrito_cuantas_gavetas_tiene_la_placa(app, client):
    """Para verlo en Admin sin ir al puesto a contar cajones."""
    device_id = _registrar_lector(app)
    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 0, 'fuera': False,
                      'resultado': 'arranque', 'gavetas': 32, 'expansores': 2})

    ruta = os.path.join(app.config['DATA_DIR'], 'esp32_rfid_devices.json')
    with open(ruta, encoding='utf-8') as f:
        devs = json.load(f)
    assert devs[device_id]['gavetas'] == 32
    assert devs[device_id]['last_seen']


def test_aviso_de_un_lector_desconocido_no_revienta(client):
    r = client.post('/api/esp32/rfid/gaveta',
                    json={'device_id': 'ffffffffffff', 'led': 1, 'fuera': True,
                          'resultado': 'sin_objetivo'})
    assert r.status_code == 200 and r.get_json()['success'] is True


def test_aviso_sin_device_id_se_rechaza(client):
    r = client.post('/api/esp32/rfid/gaveta', json={'led': 1})
    assert r.status_code == 400


# ── Apagar y probar ──────────────────────────────────────────────────────────

def test_apagar_limpia_el_estado_del_puesto(app, client, admin_client, con_placa):
    device_id = _registrar_lector(app)
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})

    client.post('/api/pick-to-light/apagar', json={'puesto_id': 'puesto_001'})

    datos = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert datos['recogida'] is False and datos['led'] is None
    assert con_placa[-1] == ('192.168.50.151', {'apagar': True})


def test_apagar_sin_placa_no_es_un_error(client, sin_placa):
    r = client.post('/api/pick-to-light/apagar', json={'puesto_id': 'puesto_001'})
    assert r.status_code == 200 and r.get_json()['success'] is True


def test_probar_deduce_el_puesto_a_partir_del_terminal(app, admin_client, con_placa):
    """En gestión de puestos se prueba un terminal, no un puesto."""
    _registrar_lector(app)
    r = admin_client.post('/api/pick-to-light/probar', json={'terminal': '640204', 'led': 5})
    assert r.status_code == 200, r.get_json()
    assert con_placa == [('192.168.50.151', {'led': 5})]


def test_probar_un_terminal_sin_maquina_lo_dice_claro(admin_client, con_placa):
    r = admin_client.post('/api/pick-to-light/probar', json={'terminal': 'NOEXISTE', 'led': 5})
    assert r.status_code == 404
    assert 'no esta asignado a ninguna maquina' in r.get_json()['message']


def test_probar_un_led_fuera_de_rango_no_llega_a_la_placa(app, admin_client, con_placa):
    """Un numero que no se podria guardar tampoco se manda a la placa."""
    _registrar_lector(app)
    for valor in (0, 129, 'x'):
        r = admin_client.post('/api/pick-to-light/probar',
                              json={'terminal': '640204', 'led': valor})
        assert r.status_code == 400, (valor, r.get_json())
    assert con_placa == []


def test_probar_espera_mas_que_encender(app, admin_client, monkeypatch):
    """Encender es delante del operario; probar es de montaje y puede esperar.

    Sondear los expansores por I2C a veces pasa del timeout corto, y ahi un
    corte no ahorra nada: no hay nadie esperando la pantalla.
    """
    _registrar_lector(app)
    vistos = []
    monkeypatch.setattr(pick_to_light, '_enviar_a_placa',
                        lambda ip, payload, timeout=None: (vistos.append(timeout), (True, ''))[1])

    admin_client.post('/api/pick-to-light/probar', json={'terminal': '640204', 'led': 5})
    assert vistos == [pick_to_light.TIMEOUT_PLACA_PROBAR]
    assert pick_to_light.TIMEOUT_PLACA_PROBAR > pick_to_light.TIMEOUT_PLACA


def test_probar_necesita_pin_de_admin(client, con_placa):
    r = client.post('/api/pick-to-light/probar', json={'terminal': '640204', 'led': 5})
    assert r.status_code in (401, 403)
    assert con_placa == []


# ── Export/import del kanban ─────────────────────────────────────────────────

def test_el_export_lleva_el_led_y_la_ida_y_vuelta_lo_conserva(admin_client):
    import io as _io
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    exportado = json.loads(
        admin_client.get('/api/kanban-terminales/export-datos').data.decode('utf-8'))
    assert exportado['gavetas'] == [{'terminal_codigo': '640204', 'gaveta': 'A-12', 'led': 7}]

    admin_client.delete('/api/terminal-gaveta/640204')
    contenido = json.dumps(exportado, ensure_ascii=False).encode('utf-8')
    admin_client.post('/api/kanban-terminales/import-datos',
                      data={'fichero': (_io.BytesIO(contenido), 'kanban.json')},
                      content_type='multipart/form-data')

    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['led'] == 7


def test_importar_un_fichero_viejo_no_borra_los_leds(admin_client):
    """Los ficheros v1 no traen 'led'; importarlos no puede apagar el puesto."""
    import io as _io
    admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'A-12', 'led': 7})

    viejo = {'version': 1,
             'gavetas': [{'terminal_codigo': '640204', 'gaveta': 'A-12'}],
             'stock': []}
    contenido = json.dumps(viejo, ensure_ascii=False).encode('utf-8')
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data={'fichero': (_io.BytesIO(contenido), 'kanban.json')},
                          content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()
    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['led'] == 7


# ── Pruebas de cableado con la placa fuera de alcance ────────────────────────
#
# Desde PythonAnywhere el servidor NO puede abrir una conexion hacia la placa:
# vive en una IP privada y el intento muere con ConnectionRefusedError. Los
# endpoints de prueba daban 502 y el panel quedaba inservible justo en el
# entorno donde se estaba montando el hardware. Ahora el comando se aparca y lo
# recoge el sondeo de la placa, que devuelve el resultado por otra peticion.

@pytest.fixture
def placa_inalcanzable(monkeypatch):
    """El empuje directo al puerto 80 falla, como desde PythonAnywhere."""
    intentos = []

    def _falso(ip, payload, timeout=None):
        intentos.append((ip, payload))
        return False, 'La placa no responde (ConnectionRefusedError)', {}

    monkeypatch.setattr(pick_to_light, '_enviar_a_placa_con_datos', _falso)
    return intentos


def test_prueba_de_led_con_la_placa_fuera_de_alcance_no_da_502(
        app, admin_client, placa_inalcanzable):
    """El 502 no se podia arreglar tocando la placa: no era cosa suya."""
    dev = _registrar_lector(app)
    r = admin_client.post('/api/pick-to-light/test/led',
                          json={'device_id': dev, 'led': 5, 'color': [0, 0, 100]})
    assert r.status_code == 200
    datos = r.get_json()
    assert datos['success'] is True
    assert datos['pendiente'] is True
    assert datos['seq'] >= 1


def test_la_placa_recoge_la_prueba_en_su_sondeo(app, client, admin_client,
                                                placa_inalcanzable):
    """El comando aparcado tiene que salir por la ruta que sondea la placa."""
    dev = _registrar_lector(app)
    admin_client.post('/api/pick-to-light/test/led',
                      json={'device_id': dev, 'led': 5, 'color': [0, 0, 100]})

    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + dev).get_json()
    assert orden['test'] == {'test_led': 5, 'color': [0, 0, 100]}
    assert orden['test_seq'] >= 1


def test_el_resultado_de_la_placa_llega_al_panel(app, client, admin_client,
                                                 placa_inalcanzable):
    """Ida y vuelta completa: sin esto 'test_micros' no serviria de nada."""
    dev = _registrar_lector(app)
    pedido = admin_client.post('/api/pick-to-light/test/micros',
                               json={'device_id': dev}).get_json()
    seq = pedido['seq']

    # Antes de que conteste la placa, el panel sigue esperando.
    espera = admin_client.get(
        '/api/pick-to-light/test/resultado?device_id=%s&seq=%d' % (dev, seq)).get_json()
    assert espera['listo'] is False

    client.post('/api/esp32/rfid/gaveta/test-resultado',
                json={'device_id': dev, 'seq': seq,
                      'resultado': {'ok': True, 'fuera': [3], 'puestas': [1, 2],
                                    'total': 16}})

    listo = admin_client.get(
        '/api/pick-to-light/test/resultado?device_id=%s&seq=%d' % (dev, seq)).get_json()
    assert listo['listo'] is True
    assert listo['resultado']['fuera'] == [3]
    assert listo['resultado']['total'] == 16


def test_la_orden_no_se_repite_una_vez_ejecutada(app, client, admin_client,
                                                 placa_inalcanzable):
    """Sin esto la placa repetiria la prueba en cada sondeo, cada 750 ms."""
    dev = _registrar_lector(app)
    seq = admin_client.post('/api/pick-to-light/test/led',
                            json={'device_id': dev, 'led': 5}).get_json()['seq']
    client.post('/api/esp32/rfid/gaveta/test-resultado',
                json={'device_id': dev, 'seq': seq, 'resultado': {'ok': True}})

    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + dev).get_json()
    assert not orden.get('test')


def test_un_resultado_atrasado_no_pisa_a_la_prueba_en_curso(
        app, client, admin_client, placa_inalcanzable):
    """Una respuesta tardia de la prueba anterior no puede darse por buena."""
    dev = _registrar_lector(app)
    primera = admin_client.post('/api/pick-to-light/test/led',
                                json={'device_id': dev, 'led': 1}).get_json()['seq']
    segunda = admin_client.post('/api/pick-to-light/test/led',
                                json={'device_id': dev, 'led': 2}).get_json()['seq']
    assert segunda != primera

    # Llega, tarde, el resultado de la PRIMERA.
    client.post('/api/esp32/rfid/gaveta/test-resultado',
                json={'device_id': dev, 'seq': primera,
                      'resultado': {'ok': True, 'test_led': 1}})

    r = admin_client.get('/api/pick-to-light/test/resultado?device_id=%s&seq=%d'
                         % (dev, segunda)).get_json()
    assert r['listo'] is False, 'el panel se ha creido el resultado del anterior'


def test_con_la_placa_a_mano_no_se_usa_el_sondeo(app, admin_client, monkeypatch):
    """En la red de planta el empuje directo sigue siendo el camino: instantaneo."""
    monkeypatch.setattr(pick_to_light, '_enviar_a_placa_con_datos',
                        lambda ip, payload, timeout=None:
                        (True, '', {'ok': True, 'estado': {'gavetas': 16}}))
    dev = _registrar_lector(app)
    datos = admin_client.post('/api/pick-to-light/test/led',
                              json={'device_id': dev, 'led': 5}).get_json()
    assert datos['pendiente'] is False
    assert datos['estado']['gavetas'] == 16


# ── Mapa de cobertura del puesto ─────────────────────────────────────────────

def test_mapa_requiere_pin_admin(app, client):
    dev = _registrar_lector(app, gavetas=8)
    assert client.get('/api/pick-to-light/mapa?device_id=' + dev).status_code == 401


def test_mapa_lector_no_encontrado(admin_client):
    r = admin_client.get('/api/pick-to-light/mapa?device_id=noexiste')
    assert r.status_code == 404


def test_mapa_sin_gavetas_reportadas_aun(app, admin_client):
    """La placa todavía no ha dicho cuántos canales tiene: lista vacía, no error."""
    dev = _registrar_lector(app)   # gavetas=0 por defecto
    r = admin_client.get('/api/pick-to-light/mapa?device_id=' + dev)
    datos = r.get_json()
    assert r.status_code == 200
    assert datos['total_gavetas'] == 0 and datos['canales'] == []


def test_mapa_marca_asignados_y_libres_sin_mezclar_puestos(app, admin_client):
    """El mismo número de LED en dos puestos son dos cajones físicos distintos."""
    dev = _registrar_lector(app, gavetas=5)
    admin_client.put('/api/terminal-gaveta/ZZMAPA1', json={'gaveta': 'A-1', 'led': 2})
    admin_client.put('/api/terminal-gaveta/ZZMAPA2', json={'gaveta': 'B-9', 'led': 4})
    _asignar_terminal_a_maquina(app, 'ZZMAPA1', puesto_id='puesto_001', maquina_id='maquina_mapa')
    # ZZMAPA2 tiene led=4 pero está en OTRO puesto: no puede aparecer en el mapa de puesto_001.
    _asignar_terminal_a_maquina(app, 'ZZMAPA2', puesto_id='puesto_mapa_otro',
                                maquina_id='maquina_mapa_otro')

    r = admin_client.get('/api/pick-to-light/mapa?device_id=' + dev)
    datos = r.get_json()

    assert r.status_code == 200
    assert datos['puesto_id'] == 'puesto_001'
    assert datos['total_gavetas'] == 5
    assert len(datos['canales']) == 5
    por_canal = {c['canal']: c for c in datos['canales']}
    assert por_canal[2] == {'canal': 2, 'terminal': 'ZZMAPA1', 'gaveta': 'A-1'}
    assert por_canal[4] == {'canal': 4, 'terminal': None, 'gaveta': None}
    assert por_canal[1] == {'canal': 1, 'terminal': None, 'gaveta': None}


# ── Informe de correspondencia LED-micro ─────────────────────────────────────

def test_informe_requiere_pin_admin(app, client):
    dev = _registrar_lector(app)
    assert client.post('/api/pick-to-light/correspondencia/informe',
                       json={'device_id': dev}).status_code == 401
    assert client.get('/api/pick-to-light/correspondencia/informe?device_id=' + dev).status_code == 401


def test_informe_sin_device_id_se_rechaza(admin_client):
    r = admin_client.post('/api/pick-to-light/correspondencia/informe', json={})
    assert r.status_code == 400


def test_informe_sin_prueba_previa_devuelve_none(admin_client):
    r = admin_client.get('/api/pick-to-light/correspondencia/informe?device_id=nunca-probado')
    assert r.status_code == 200 and r.get_json()['informe'] is None


def test_informe_se_guarda_y_se_recupera(app, admin_client):
    dev = _registrar_lector(app)
    resumen = {'comprobados': 3, 'correctos': 2, 'cruzados': 1, 'sin_respuesta': 0, 'omitidos': 0}
    detalle = [
        {'canal': 1, 'terminal': '640204', 'gaveta': 'A-12', 'resultado': 'correcto'},
        {'canal': 2, 'terminal': '640205', 'gaveta': 'A-13', 'resultado': 'cruzado', 'abrio_canal': 3},
    ]
    r = admin_client.post('/api/pick-to-light/correspondencia/informe',
                          json={'device_id': dev, 'resumen': resumen, 'detalle': detalle})
    assert r.status_code == 200 and r.get_json()['success'] is True

    informe = admin_client.get(
        '/api/pick-to-light/correspondencia/informe?device_id=' + dev).get_json()['informe']
    assert informe['device_id'] == dev
    assert informe['puesto_id'] == 'puesto_001'
    assert informe['cancelado'] is False
    assert informe['resumen'] == resumen
    assert informe['detalle'] == detalle
    assert informe['fecha']   # se sella en el servidor


def test_informe_cancelado_se_guarda_como_tal(app, admin_client):
    dev = _registrar_lector(app)
    admin_client.post('/api/pick-to-light/correspondencia/informe',
                      json={'device_id': dev, 'cancelado': True,
                            'resumen': {'comprobados': 1}, 'detalle': []})
    informe = admin_client.get(
        '/api/pick-to-light/correspondencia/informe?device_id=' + dev).get_json()['informe']
    assert informe['cancelado'] is True


def test_un_segundo_informe_sustituye_al_anterior(app, admin_client):
    """Solo se guarda 'el último', como se pidió: nada de historial todavía."""
    dev = _registrar_lector(app)
    admin_client.post('/api/pick-to-light/correspondencia/informe',
                      json={'device_id': dev, 'resumen': {'comprobados': 1}, 'detalle': []})
    admin_client.post('/api/pick-to-light/correspondencia/informe',
                      json={'device_id': dev, 'resumen': {'comprobados': 2}, 'detalle': []})
    informe = admin_client.get(
        '/api/pick-to-light/correspondencia/informe?device_id=' + dev).get_json()['informe']
    assert informe['resumen']['comprobados'] == 2
