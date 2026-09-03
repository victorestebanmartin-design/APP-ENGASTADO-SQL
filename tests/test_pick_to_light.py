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


def _registrar_lector(app, device_id='aabbccddeeff', puesto_id='puesto_001', ip='192.168.50.151'):
    """Deja un lector RFID asignado a un puesto, como haría Admin."""
    ruta = os.path.join(app.config['DATA_DIR'], 'esp32_rfid_devices.json')
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({device_id: {'ip': ip, 'puesto_id': puesto_id,
                               'puesto_nombre': 'TERMINALES AMP'}}, f)
    return device_id


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
    assert con_placa == [('192.168.50.151', {'led': 7})]


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
    assert orden == {'success': True, 'apagar': False, 'led': 7}

    client.post('/api/pick-to-light/apagar', json={'puesto_id': 'puesto_001'})
    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden == {'success': True, 'apagar': True, 'led': None}


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
    assert orden == {'success': True, 'apagar': False, 'led': 5}


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
