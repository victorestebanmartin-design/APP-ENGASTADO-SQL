"""Pick-to-light de gavetas.

Lo que se prueba aquí, sobre todo, es que el sistema DEGRADA bien: sin tira de
LEDs, sin lector asignado o con la placa desenchufada, engastado tiene que
seguir llegando a los paquetes. Un fallo de la bombilla no puede parar a nadie.

El hardware real no está en CI, así que el envío a la placa se sustituye por
un doble que registra lo que se le manda (ver _sin_placa / _con_placa).

La configuración física (terminal -> gaveta -> LED) vive en
pick_to_light_canales, una fila por (puesto, canal): el LED 1 del puesto A y
el LED 1 del puesto B son cajones físicos distintos. Se escribe SOLO desde
PUT/DELETE /api/pick-to-light/canal; la vieja ruta /api/terminal-gaveta/<cod>
sigue existiendo en solo lectura (la usa v3-seleccion.js) más un GET, pero su
PUT/DELETE están deprecados (410) a propósito: un único sitio de escritura.
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

    Hace falta para que la asignación de canal la acepte: un terminal solo
    puede tener LED en el puesto de la máquina a la que está enganchado.
    640204 y 640205 ya vienen así de fábrica (semilla de seed_inicial.json en
    puesto_001), así que la mayoría de tests no necesita llamar a esto.
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


def _asignar_canal(admin_client, puesto_id, canal, terminal, etiqueta='A-12'):
    """PUT /api/pick-to-light/canal: único sitio desde el que se escribe."""
    return admin_client.put('/api/pick-to-light/canal',
                            json={'puesto_id': puesto_id, 'canal': canal,
                                  'terminal': terminal, 'etiqueta_gaveta': etiqueta})


def _seed_terminales_gavetas(app, terminal, gaveta, led=None):
    """Inserta directamente en la vieja terminales_gavetas (sin pasar por la
    API, que ya no escribe ahí): solo para probar el puente de exportación
    /kanban-terminales, que sigue leyendo de la tabla vieja a propósito."""
    from sqlalchemy import text
    with app.app_context():
        from app.routes.base import db
        db.session.execute(text("""
            INSERT INTO terminales_gavetas (terminal_codigo, gaveta, led, updated_at)
            VALUES (:t, :g, :l, datetime('now'))
        """), {'t': terminal, 'g': gaveta, 'l': led})
        db.session.commit()


# ── Canal Pick-to-Light: asignar / cambiar / desasignar ──────────────────────

def test_asignar_canal_guarda_y_se_puede_leer_despues(admin_client):
    r = _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    assert r.status_code == 200 and r.get_json()['canal'] == 7

    datos = admin_client.get('/api/terminal-gaveta/640204').get_json()
    assert datos['gaveta'] == 'A-12' and datos['led'] == 7 and datos['puesto_id'] == 'puesto_001'


def test_terminal_sin_maquina_en_el_puesto_se_rechaza(admin_client):
    r = _asignar_canal(admin_client, 'puesto_001', 7, 'SIN-MAQUINA', 'A-12')
    assert r.status_code == 400
    assert 'no pertenece a ninguna máquina' in r.get_json()['message']


def test_terminal_de_otro_puesto_no_se_puede_asignar_aqui(app, admin_client):
    """El terminal existe, pero su máquina está en OTRO puesto."""
    _asignar_terminal_a_maquina(app, 'ZZOTRO', puesto_id='puesto_ajeno', maquina_id='maquina_ajena')
    r = _asignar_canal(admin_client, 'puesto_001', 7, 'ZZOTRO', 'A-12')
    assert r.status_code == 400
    assert 'no pertenece a ninguna máquina de este puesto' in r.get_json()['message']


def test_canal_fuera_de_rango_se_rechaza(admin_client):
    r = _asignar_canal(admin_client, 'puesto_001', 999, '640204', 'A-12')
    assert r.status_code == 400
    assert 'entre 1 y' in r.get_json()['message']


def test_canal_por_encima_de_las_gavetas_detectadas_se_rechaza(app, admin_client):
    """La placa de este puesto solo tiene 5 canales de verdad."""
    _registrar_lector(app, gavetas=5)
    r = _asignar_canal(admin_client, 'puesto_001', 6, '640204', 'A-12')
    assert r.status_code == 400
    assert 'no existe' in r.get_json()['message']


def test_canal_dentro_de_las_gavetas_detectadas_se_acepta(app, admin_client):
    _registrar_lector(app, gavetas=5)
    r = _asignar_canal(admin_client, 'puesto_001', 5, '640204', 'A-12')
    assert r.status_code == 200


def test_no_se_puede_repetir_canal_dentro_del_mismo_puesto(admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    r = _asignar_canal(admin_client, 'puesto_001', 7, '640205', 'A-13')
    assert r.status_code == 400
    assert '640204' in r.get_json()['message']


def test_led_1_puede_existir_en_dos_puestos_distintos(app, admin_client):
    """El canal 1 del puesto A y el canal 1 del puesto B son cajones físicos
    distintos: cada placa tiene su propia numeración."""
    _asignar_terminal_a_maquina(app, 'ZZOTRO', puesto_id='puesto_002', maquina_id='maquina_otra')
    r1 = _asignar_canal(admin_client, 'puesto_001', 1, '640204', 'A-1')
    r2 = _asignar_canal(admin_client, 'puesto_002', 1, 'ZZOTRO', 'B-1')
    assert r1.status_code == 200 and r2.status_code == 200


def test_un_terminal_no_puede_tener_dos_canales_en_el_mismo_puesto(admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    r = _asignar_canal(admin_client, 'puesto_001', 8, '640204', 'A-13')
    assert r.status_code == 400
    assert 'canal 7' in r.get_json()['message']


def test_reasignar_el_mismo_canal_y_terminal_actualiza_la_etiqueta(admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    r = _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-99')
    assert r.status_code == 200
    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['gaveta'] == 'A-99'


def test_desasignar_canal_libera_el_terminal_y_el_canal(admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    r = admin_client.delete('/api/pick-to-light/canal?puesto_id=puesto_001&canal=7')
    assert r.status_code == 200

    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['led'] is None
    # El canal y el terminal quedan libres para una asignación nueva.
    assert _asignar_canal(admin_client, 'puesto_001', 7, '640205', 'A-13').status_code == 200


def test_asignar_canal_requiere_pin_admin(client):
    r = client.put('/api/pick-to-light/canal',
                   json={'puesto_id': 'puesto_001', 'canal': 7, 'terminal': '640204',
                         'etiqueta_gaveta': 'A-12'})
    assert r.status_code in (401, 403)


def test_desasignar_canal_requiere_pin_admin(client):
    r = client.delete('/api/pick-to-light/canal?puesto_id=puesto_001&canal=7')
    assert r.status_code in (401, 403)


def test_terminal_gaveta_put_delete_estan_deprecados(client, admin_client):
    """La ficha de Terminales ya no puede escribir: solo Pick-to-Light."""
    r = admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'X', 'led': 1})
    assert r.status_code == 410
    r = admin_client.delete('/api/terminal-gaveta/640204')
    assert r.status_code == 410


# ── Encender ─────────────────────────────────────────────────────────────────

def test_encender_manda_el_led_a_la_placa(app, client, admin_client, con_placa):
    _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200
    assert datos['activo'] is True and datos['led'] == 7 and datos['gaveta'] == 'A-12'
    assert con_placa == [('192.168.50.151', {'led': 7, 'terminal': '640204', 'validas': [7]})]


def test_encender_manda_las_gavetas_validas_del_puesto(app, client, admin_client, con_placa):
    """La placa necesita saber qué canales tienen gaveta de verdad detrás.

    Un expansor MCP23017 trae 16 canales aunque solo se haya cableado un
    microinterruptor: sin esta lista, los canales sin cablear se leen como
    'fuera' permanentemente y se confunden con gavetas robadas. Usa un puesto
    y terminales propios (no los de la semilla) para no depender de esos datos.
    """
    _registrar_lector(app, puesto_id='puesto_ptl_test')
    _asignar_terminal_a_maquina(app, 'ZZTEST1', puesto_id='puesto_ptl_test',
                                maquina_id='maquina_ptl_test')
    _asignar_terminal_a_maquina(app, 'ZZTEST2', puesto_id='puesto_ptl_test',
                                maquina_id='maquina_ptl_test')
    _asignar_canal(admin_client, 'puesto_ptl_test', 7, 'ZZTEST1', 'A-1')
    _asignar_canal(admin_client, 'puesto_ptl_test', 3, 'ZZTEST2', 'A-2')
    # Un terminal con gaveta pero de OTRO puesto no puede colarse en la lista.
    _asignar_terminal_a_maquina(app, 'ZZTEST3', puesto_id='puesto_ptl_otro',
                                maquina_id='maquina_ptl_otro')
    _asignar_canal(admin_client, 'puesto_ptl_otro', 12, 'ZZTEST3', 'B-1')

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_ptl_test', 'terminal': 'ZZTEST1'})
    assert con_placa == [('192.168.50.151',
                          {'led': 7, 'terminal': 'ZZTEST1', 'validas': [3, 7]})]


def test_encender_un_terminal_sin_led_no_es_un_error(app, client, admin_client, con_placa):
    """Sin luz configurada la app tiene que seguir, avisando del motivo."""
    _registrar_lector(app)

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200 and datos['success'] is True
    assert datos['activo'] is False and 'no tiene gaveta con luz' in datos['motivo']
    assert con_placa == []


def test_encender_sin_lector_asignado_no_es_un_error(client, admin_client, con_placa):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200 and datos['activo'] is False
    assert 'lector asignado' in datos['motivo']


def test_encender_con_la_placa_caida_no_es_un_error(app, client, admin_client, sin_placa):
    _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')

    r = client.post('/api/pick-to-light/encender',
                    json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    datos = r.get_json()
    assert r.status_code == 200 and datos['success'] is True
    assert datos['activo'] is False and 'no responde' in datos['motivo']


def test_lector_tras_nat_puede_sondear_su_orden(app, client, admin_client, con_placa):
    device_id = _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden == {'success': True, 'apagar': False, 'led': 7, 'terminal': '640204', 'validas': [7], 'rfid_modo': None}

    client.post('/api/pick-to-light/apagar', json={'puesto_id': 'puesto_001'})
    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden == {'success': True, 'apagar': True, 'led': None, 'terminal': '', 'validas': [], 'rfid_modo': None}


def test_pythonanywhere_espera_la_gaveta_por_sondeo(app, client, admin_client, sin_placa):
    _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')

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
    assert orden == {'success': True, 'apagar': False, 'led': 5, 'terminal': '', 'validas': [], 'rfid_modo': None}


def test_sondeo_reconfirma_recogida_si_se_pierde_el_aviso_post(app, client, admin_client, con_placa):
    """El GET periodico tiene que poder confirmar solo, sin depender del POST.

    El aviso normal (api_esp32_rfid_gaveta) es un POST suelto en el momento de
    sacar la gaveta: si se pierde por un handshake TLS lento o un corte breve
    de wifi, nadie lo reintenta. El sondeo de /orden si se repite cada 750 ms
    (ver lector_puesto.py), asi que reportar led/recogida tambien ahi tiene
    que bastar para que el operario no se quede esperando delante del cajon.
    """
    device_id = _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
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
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    client.get('/api/esp32/rfid/gaveta/orden?device_id=%s&led=3&recogida=1' % device_id)

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['recogida'] is False


def test_encender_otro_terminal_borra_la_recogida_anterior(app, client, admin_client, con_placa):
    """Sin esto, el segundo terminal saltaría la puerta con la confirmación del primero."""
    device_id = _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    _asignar_canal(admin_client, 'puesto_001', 8, '640205', 'A-13')

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
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    r = client.post('/api/esp32/rfid/gaveta',
                    json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})
    assert r.status_code == 200

    datos = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert datos['recogida'] is True and datos['error_led'] is None


def test_la_gaveta_equivocada_se_marca_y_se_corrige(app, client, admin_client, con_placa):
    device_id = _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
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
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
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
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
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
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
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
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 3, 'fuera': True, 'resultado': 'equivocada'})

    client.get('/api/esp32/rfid/gaveta/orden?device_id=%s&led=7&recogida=1&intrusas=' % device_id)
    datos = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert datos['intrusas'] == [] and datos['error_led'] is None


def test_encender_manda_el_terminal_a_la_placa_para_el_display(app, client, admin_client, con_placa):
    _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')

    client.post('/api/pick-to-light/encender',
                json={'puesto_id': 'puesto_001', 'terminal': '640204'})
    assert con_placa == [('192.168.50.151', {'led': 7, 'terminal': '640204', 'validas': [7]})]


def test_el_sondeo_devuelve_el_terminal_en_curso(app, client, admin_client, con_placa):
    """La placa tras NAT tambien tiene que poder escribirlo en su pantalla."""
    device_id = _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
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
    assert devs[device_id]['expansores'] == 2
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
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
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


# ── Export/import del kanban (puente entre servidores) ───────────────────────
#
# Este puente sigue leyendo/escribiendo la vieja terminales_gavetas a
# proposito (ver nota junto a KANBAN_DATOS_VERSION en puestos.py): ya no
# gobierna ninguna luz, asi que se siembra con SQL directo en vez de con la
# API (que ya no escribe ahi).

def test_el_export_lleva_el_led_y_la_ida_y_vuelta_lo_conserva(app, admin_client):
    import io as _io
    _seed_terminales_gavetas(app, '640204', 'A-12', 7)

    exportado = json.loads(
        admin_client.get('/api/kanban-terminales/export-datos').data.decode('utf-8'))
    assert exportado['gavetas'] == [{'terminal_codigo': '640204', 'gaveta': 'A-12', 'led': 7}]

    contenido = json.dumps(exportado, ensure_ascii=False).encode('utf-8')
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data={'fichero': (_io.BytesIO(contenido), 'kanban.json')},
                          content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()


def test_importar_un_fichero_viejo_no_revienta(admin_client):
    """Los ficheros v1 no traen 'led'; se siguen aceptando sin dar error."""
    import io as _io
    viejo = {'version': 1,
             'gavetas': [{'terminal_codigo': '640204', 'gaveta': 'A-12'}],
             'stock': []}
    contenido = json.dumps(viejo, ensure_ascii=False).encode('utf-8')
    r = admin_client.post('/api/kanban-terminales/import-datos',
                          data={'fichero': (_io.BytesIO(contenido), 'kanban.json')},
                          content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()


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
    _asignar_terminal_a_maquina(app, 'ZZMAPA1', puesto_id='puesto_001', maquina_id='maquina_mapa')
    _asignar_canal(admin_client, 'puesto_001', 2, 'ZZMAPA1', 'A-1')
    # ZZMAPA2 tiene canal 4 pero está en OTRO puesto: no puede aparecer en el mapa de puesto_001.
    _asignar_terminal_a_maquina(app, 'ZZMAPA2', puesto_id='puesto_mapa_otro',
                                maquina_id='maquina_mapa_otro')
    _asignar_canal(admin_client, 'puesto_mapa_otro', 4, 'ZZMAPA2', 'B-9')

    r = admin_client.get('/api/pick-to-light/mapa?device_id=' + dev)
    datos = r.get_json()

    assert r.status_code == 200
    assert datos['puesto_id'] == 'puesto_001'
    assert datos['total_gavetas'] == 5
    assert len(datos['canales']) == 5
    por_canal = {c['canal']: c for c in datos['canales']}
    assert por_canal[2] == {'canal': 2, 'terminal': 'ZZMAPA1', 'gaveta': 'A-1', 'rfid': False}
    assert por_canal[4] == {'canal': 4, 'terminal': None, 'gaveta': None, 'rfid': False}
    assert por_canal[1] == {'canal': 1, 'terminal': None, 'gaveta': None, 'rfid': False}


def test_mapa_puede_pedirse_por_puesto_id(app, admin_client):
    """El flujo normal es elegir puesto primero; el lector se resuelve solo."""
    _registrar_lector(app, gavetas=5)
    r = admin_client.get('/api/pick-to-light/mapa?puesto_id=puesto_001')
    assert r.status_code == 200 and r.get_json()['total_gavetas'] == 5


def test_mapa_lista_terminales_disponibles_sin_los_ya_asignados(app, admin_client):
    dev = _registrar_lector(app, gavetas=5)
    r = _asignar_canal(admin_client, 'puesto_001', 3, '640204', 'A-12')
    assert r.status_code == 200, r.get_json()

    datos = admin_client.get('/api/pick-to-light/mapa?device_id=' + dev).get_json()
    codigos = {t['terminal'] for t in datos['terminales_disponibles']}
    assert '640204' not in codigos            # ya asignado
    assert '640205' in codigos                # de una máquina del puesto, aún libre


def test_mapa_incluye_el_estado_del_dispositivo(app, admin_client):
    device_id = _registrar_lector(app, gavetas=5)
    # Simula un latido real de la placa (expansores + en_prueba).
    ruta = os.path.join(app.config['DATA_DIR'], 'esp32_rfid_devices.json')
    with open(ruta, encoding='utf-8') as f:
        devs = json.load(f)
    devs[device_id]['expansores'] = 1
    devs[device_id]['en_prueba'] = True
    devs[device_id]['nombre'] = 'Lector puesto 1'
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(devs, f)

    datos = admin_client.get('/api/pick-to-light/mapa?device_id=' + device_id).get_json()
    assert datos['dispositivo']['expansores'] == 1
    assert datos['dispositivo']['en_prueba'] is True
    assert datos['dispositivo']['nombre'] == 'Lector puesto 1'
    assert datos['dispositivo']['online'] is False   # sin last_seen todavía


def test_mapa_dispositivo_online_con_latido_reciente(app, admin_client):
    from datetime import datetime
    device_id = _registrar_lector(app, gavetas=5)
    ruta = os.path.join(app.config['DATA_DIR'], 'esp32_rfid_devices.json')
    with open(ruta, encoding='utf-8') as f:
        devs = json.load(f)
    devs[device_id]['last_seen'] = datetime.now().isoformat()
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(devs, f)

    datos = admin_client.get('/api/pick-to-light/mapa?device_id=' + device_id).get_json()
    assert datos['dispositivo']['online'] is True


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


# ── Alta de RFID por canal ────────────────────────────────────────────────────
#
# El RC522 es el MISMO que el login de operarios: aquí solo se prueba la
# parte servidor (armar/sondear/confirmar/desvincular + unicidad). El "modo"
# del firmware que evita mezclar una lectura de gaveta con un login normal
# se prueba en tests/test_gavetas_firmware.py-style, en el propio fichero de
# firmware si aplica, o queda para verificación manual (no hay runner JS/RC522
# en CI para el bucle principal completo de lector_puesto.py).

def test_normalizar_uid(app):
    from app.routes.pick_to_light import _normalizar_uid
    with app.app_context():
        assert _normalizar_uid(' a1:b2-c3 d4 ') == 'A1B2C3D4'
        assert _normalizar_uid('') == ''
        assert _normalizar_uid(None) == ''


def test_rfid_armar_requiere_pin_admin(client):
    r = client.post('/api/pick-to-light/canal/rfid/armar',
                    json={'puesto_id': 'puesto_001', 'canal': 7})
    assert r.status_code in (401, 403)


def test_rfid_armar_sin_lector_asignado_da_404(admin_client):
    r = admin_client.post('/api/pick-to-light/canal/rfid/armar',
                          json={'puesto_id': 'puesto_sin_lector', 'canal': 7})
    assert r.status_code == 404


def test_rfid_armar_encola_el_comando_para_la_placa(app, admin_client):
    device_id = _registrar_lector(app)
    r = admin_client.post('/api/pick-to-light/canal/rfid/armar',
                          json={'puesto_id': 'puesto_001', 'canal': 7})
    datos = r.get_json()
    assert r.status_code == 200 and datos['device_id'] == device_id and datos['seq'] >= 1

    orden = admin_client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden['test'] == {'ptl_rfid_modo': 'alta', 'canal': 7,
                             'duracion_ms': pick_to_light.RFID_ARMADO_DURACION_MS}


def test_rfid_sondeo_antes_de_leer_nada_no_esta_listo(app, admin_client):
    device_id = _registrar_lector(app)
    seq = admin_client.post('/api/pick-to-light/canal/rfid/armar',
                            json={'puesto_id': 'puesto_001', 'canal': 7}).get_json()['seq']
    r = admin_client.get('/api/pick-to-light/canal/rfid/armar?device_id=%s&seq=%d'
                         % (device_id, seq))
    assert r.status_code == 200 and r.get_json()['listo'] is False


def test_rfid_lectura_de_alta_marca_listo_con_el_uid_normalizado(app, admin_client, client):
    device_id = _registrar_lector(app)
    seq = admin_client.post('/api/pick-to-light/canal/rfid/armar',
                            json={'puesto_id': 'puesto_001', 'canal': 7}).get_json()['seq']

    r = client.post('/api/esp32/rfid/gaveta/lectura',
                    json={'device_id': device_id, 'uid': 'a1:b2:c3:d4', 'tipo': 'alta'})
    assert r.status_code == 200 and r.get_json()['ok'] is True

    sondeo = admin_client.get('/api/pick-to-light/canal/rfid/armar?device_id=%s&seq=%d'
                              % (device_id, seq)).get_json()
    assert sondeo['listo'] is True and sondeo['uid'] == 'A1B2C3D4'


def test_rfid_lectura_sin_armado_previo_no_revienta(app, client):
    """Una lectura tardía (armado caducado o ya consumido) no puede tumbar nada."""
    device_id = _registrar_lector(app)
    r = client.post('/api/esp32/rfid/gaveta/lectura',
                    json={'device_id': device_id, 'uid': 'AABBCC', 'tipo': 'alta'})
    assert r.status_code == 200
    assert r.get_json()['ok'] is False


def test_rfid_lectura_sin_device_id_se_rechaza(client):
    r = client.post('/api/esp32/rfid/gaveta/lectura', json={'uid': 'AABBCC', 'tipo': 'alta'})
    assert r.status_code == 400


def test_rfid_confirmar_requiere_terminal_ya_asignado(admin_client):
    r = admin_client.put('/api/pick-to-light/canal/rfid',
                         json={'puesto_id': 'puesto_001', 'canal': 7, 'uid': 'AABBCC'})
    assert r.status_code == 400
    assert 'Asigna primero un terminal' in r.get_json()['message']


def test_rfid_confirmar_guarda_uid_y_se_ve_desde_terminal_gaveta(admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    r = admin_client.put('/api/pick-to-light/canal/rfid',
                         json={'puesto_id': 'puesto_001', 'canal': 7, 'uid': 'aa bb cc'})
    assert r.status_code == 200 and r.get_json()['uid'] == 'AABBCC'

    datos = admin_client.get('/api/terminal-gaveta/640204').get_json()
    assert datos['rfid'] is True


def test_rfid_confirmar_rechaza_uid_duplicado_activo(admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    _asignar_canal(admin_client, 'puesto_001', 8, '640205', 'A-13')
    admin_client.put('/api/pick-to-light/canal/rfid',
                     json={'puesto_id': 'puesto_001', 'canal': 7, 'uid': 'AABBCC'})

    r = admin_client.put('/api/pick-to-light/canal/rfid',
                         json={'puesto_id': 'puesto_001', 'canal': 8, 'uid': 'aabbcc'})
    assert r.status_code == 409
    assert 'canal 7' in r.get_json()['message']


def test_rfid_confirmar_rechaza_uid_duplicado_de_otro_puesto(app, admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    admin_client.put('/api/pick-to-light/canal/rfid',
                     json={'puesto_id': 'puesto_001', 'canal': 7, 'uid': 'AABBCC'})

    _asignar_terminal_a_maquina(app, 'ZZOTRO', puesto_id='puesto_002', maquina_id='maquina_otra')
    _asignar_canal(admin_client, 'puesto_002', 1, 'ZZOTRO', 'B-1')
    r = admin_client.put('/api/pick-to-light/canal/rfid',
                         json={'puesto_id': 'puesto_002', 'canal': 1, 'uid': 'AABBCC'})
    assert r.status_code == 409


def test_rfid_reasignar_el_mismo_canal_no_choca_consigo_mismo(admin_client):
    """Guardar de nuevo el mismo UID en la misma gaveta no es un duplicado."""
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    admin_client.put('/api/pick-to-light/canal/rfid',
                     json={'puesto_id': 'puesto_001', 'canal': 7, 'uid': 'AABBCC'})
    r = admin_client.put('/api/pick-to-light/canal/rfid',
                         json={'puesto_id': 'puesto_001', 'canal': 7, 'uid': 'AABBCC'})
    assert r.status_code == 200


def test_rfid_desvincular_libera_el_uid(admin_client):
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    _asignar_canal(admin_client, 'puesto_001', 8, '640205', 'A-13')
    admin_client.put('/api/pick-to-light/canal/rfid',
                     json={'puesto_id': 'puesto_001', 'canal': 7, 'uid': 'AABBCC'})

    r = admin_client.delete('/api/pick-to-light/canal/rfid?puesto_id=puesto_001&canal=7')
    assert r.status_code == 200
    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['rfid'] is False

    # El UID queda libre para otra gaveta.
    r2 = admin_client.put('/api/pick-to-light/canal/rfid',
                          json={'puesto_id': 'puesto_001', 'canal': 8, 'uid': 'AABBCC'})
    assert r2.status_code == 200


def test_mapa_marca_rfid_true_cuando_esta_configurado(app, admin_client):
    dev = _registrar_lector(app, gavetas=5)
    _asignar_canal(admin_client, 'puesto_001', 3, '640204', 'A-12')
    admin_client.put('/api/pick-to-light/canal/rfid',
                     json={'puesto_id': 'puesto_001', 'canal': 3, 'uid': 'AABBCC'})

    datos = admin_client.get('/api/pick-to-light/mapa?device_id=' + dev).get_json()
    por_canal = {c['canal']: c for c in datos['canales']}
    assert por_canal[3]['rfid'] is True


# ── Verificación RFID de la orden productiva ─────────────────────────────────
#
# El micro confirma que se ha sacado la posición correcta; el RFID confirma
# que la gaveta física es la esperada. Doble check de integridad operativa,
# no antifraude: por eso una gaveta sin RFID configurado sigue funcionando
# exactamente igual que siempre (implantación gradual).

def _encender_con_rfid(app, client, admin_client, con_placa, puesto_id='puesto_001',
                       device_id=None, terminal='640204', canal=7, uid='AABBCC'):
    """Deja una orden en curso con RFID esperado. Devuelve el device_id."""
    if device_id is None:
        device_id = _registrar_lector(app, puesto_id=puesto_id)
    _asignar_canal(admin_client, puesto_id, canal, terminal, 'A-12')
    admin_client.put('/api/pick-to-light/canal/rfid',
                     json={'puesto_id': puesto_id, 'canal': canal, 'uid': uid})
    client.post('/api/pick-to-light/encender', json={'puesto_id': puesto_id, 'terminal': terminal})
    return device_id


def test_orden_con_rfid_manda_el_modo_de_verificacion_en_el_sondeo(app, client, admin_client, con_placa):
    device_id = _encender_con_rfid(app, client, admin_client, con_placa)
    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden['rfid_modo']['canal'] == 7
    assert orden['rfid_modo']['orden_id']


def test_rfid_correcto_con_micro_correcto_confirma(app, client, admin_client, con_placa):
    device_id = _encender_con_rfid(app, client, admin_client, con_placa)
    orden_id = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id
                          ).get_json()['rfid_modo']['orden_id']

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})
    r = client.post('/api/esp32/rfid/gaveta/lectura',
                    json={'device_id': device_id, 'uid': 'aa:bb:cc', 'tipo': 'verificar',
                          'orden_id': orden_id})
    assert r.status_code == 200 and r.get_json()['ok'] is True

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['estado'] == 'confirmada'
    assert estado['rfid_confirmado'] is True

    # Ya no hace falta seguir verificando: el sondeo deja de pedirlo.
    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden['rfid_modo'] is None


def test_rfid_correcto_antes_de_abrir_el_micro_no_confirma_todavia(app, client, admin_client, con_placa):
    """Se guarda como validado, pero la orden no está 'confirmada' hasta el micro."""
    device_id = _encender_con_rfid(app, client, admin_client, con_placa)
    orden_id = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id
                          ).get_json()['rfid_modo']['orden_id']

    r = client.post('/api/esp32/rfid/gaveta/lectura',
                    json={'device_id': device_id, 'uid': 'AABBCC', 'tipo': 'verificar',
                          'orden_id': orden_id})
    assert r.get_json()['ok'] is True

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['rfid_confirmado'] is True
    assert estado['estado'] == 'esperando_micro'   # el RFID ya vale, falta abrir el cajon

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})
    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['estado'] == 'confirmada'


def test_rfid_incorrecto_no_confirma_y_registra_incidencia(app, client, admin_client, con_placa):
    device_id = _encender_con_rfid(app, client, admin_client, con_placa)
    orden_id = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id
                          ).get_json()['rfid_modo']['orden_id']
    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})

    r = client.post('/api/esp32/rfid/gaveta/lectura',
                    json={'device_id': device_id, 'uid': 'FFFFFF', 'tipo': 'verificar',
                          'orden_id': orden_id})
    datos = r.get_json()
    assert datos['ok'] is False
    assert 'no corresponde' in datos['mensaje']

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['estado'] == 'rfid_incorrecto'
    assert estado['uid_incorrecto'] is True

    incidencias = admin_client.get('/api/pick-to-light/incidencias?puesto_id=puesto_001').get_json()
    tipos = [i['tipo'] for i in incidencias['incidencias']]
    assert 'rfid_incorrecto' in tipos


def test_rfid_de_otro_puesto_no_afecta_a_esta_orden(app, client, admin_client, con_placa):
    """Un lector de OTRO puesto no puede tocar el estado de este."""
    device_id = _encender_con_rfid(app, client, admin_client, con_placa, puesto_id='puesto_001')
    _asignar_terminal_a_maquina(app, 'ZZOTRO', puesto_id='puesto_002', maquina_id='maquina_otra')
    otro_device = _encender_con_rfid(app, client, admin_client, con_placa, puesto_id='puesto_002',
                                     terminal='ZZOTRO', canal=1, uid='112233')

    # Una lectura que llega por el lector del OTRO puesto, aunque adivinara el
    # orden_id de este, no puede tocar el estado de puesto_001: el servidor
    # resuelve el puesto por el device_id, no por lo que diga el cuerpo.
    orden_id_001 = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id
                              ).get_json()['rfid_modo']['orden_id']
    client.post('/api/esp32/rfid/gaveta/lectura',
                json={'device_id': otro_device, 'uid': 'AABBCC', 'tipo': 'verificar',
                      'orden_id': orden_id_001})

    estado_001 = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado_001['rfid_confirmado'] is False


def test_lectura_tardia_de_una_orden_anterior_no_confirma_la_nueva(app, client, admin_client, con_placa):
    device_id = _encender_con_rfid(app, client, admin_client, con_placa)
    orden_vieja = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id
                             ).get_json()['rfid_modo']['orden_id']

    # El operario cambia de terminal: nueva orden, nuevo orden_id.
    _asignar_canal(admin_client, 'puesto_001', 8, '640205', 'A-13')
    admin_client.put('/api/pick-to-light/canal/rfid',
                     json={'puesto_id': 'puesto_001', 'canal': 8, 'uid': 'DDEEFF'})
    client.post('/api/pick-to-light/encender', json={'puesto_id': 'puesto_001', 'terminal': '640205'})

    # Llega, tarde, la lectura de la orden VIEJA (terminal 640204, canal 7).
    r = client.post('/api/esp32/rfid/gaveta/lectura',
                    json={'device_id': device_id, 'uid': 'AABBCC', 'tipo': 'verificar',
                          'orden_id': orden_vieja})
    assert r.get_json()['ok'] is False

    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['led'] == 8 and estado['rfid_confirmado'] is False


def test_gaveta_sin_rfid_configurado_mantiene_el_flujo_de_solo_micro(app, client, admin_client, con_placa):
    """Implantación gradual: sin UID en el canal, todo sigue como siempre."""
    device_id = _registrar_lector(app)
    _asignar_canal(admin_client, 'puesto_001', 7, '640204', 'A-12')
    client.post('/api/pick-to-light/encender', json={'puesto_id': 'puesto_001', 'terminal': '640204'})

    orden = client.get('/api/esp32/rfid/gaveta/orden?device_id=' + device_id).get_json()
    assert orden['rfid_modo'] is None

    client.post('/api/esp32/rfid/gaveta',
                json={'device_id': device_id, 'led': 7, 'fuera': True, 'resultado': 'ok'})
    estado = client.get('/api/pick-to-light/estado?puesto_id=puesto_001').get_json()
    assert estado['estado'] == 'confirmada'
    assert estado['uid_esperado'] is False


def test_rfid_timeout_o_bypass_se_registra_como_incidencia(app, client, admin_client, con_placa):
    _encender_con_rfid(app, client, admin_client, con_placa)
    r = client.post('/api/pick-to-light/incidencia',
                    json={'puesto_id': 'puesto_001', 'tipo': 'rfid_bypass',
                          'detalle': 'operario siguió sin confirmar'})
    assert r.status_code == 200

    incidencias = admin_client.get('/api/pick-to-light/incidencias?puesto_id=puesto_001').get_json()
    assert incidencias['incidencias'][0]['tipo'] == 'rfid_bypass'


def test_incidencia_de_tipo_no_reconocido_se_rechaza(client):
    r = client.post('/api/pick-to-light/incidencia',
                    json={'puesto_id': 'puesto_001', 'tipo': 'lo-que-sea'})
    assert r.status_code == 400


def test_incidencias_requiere_pin_admin(client):
    r = client.get('/api/pick-to-light/incidencias?puesto_id=puesto_001')
    assert r.status_code in (401, 403)


def test_prueba_guiada_registra_cruces_y_sin_respuesta_como_incidencias(app, admin_client):
    dev = _registrar_lector(app)
    detalle = [
        {'canal': 1, 'terminal': '640204', 'gaveta': 'A-12', 'resultado': 'correcto'},
        {'canal': 2, 'terminal': '640205', 'gaveta': 'A-13', 'resultado': 'cruzado', 'abrio_canal': 9},
        {'canal': 3, 'terminal': '640206', 'gaveta': 'A-14', 'resultado': 'sin_respuesta'},
    ]
    admin_client.post('/api/pick-to-light/correspondencia/informe',
                      json={'device_id': dev, 'resumen': {'comprobados': 3}, 'detalle': detalle})

    incidencias = admin_client.get('/api/pick-to-light/incidencias?puesto_id=puesto_001').get_json()
    tipos = sorted(i['tipo'] for i in incidencias['incidencias'])
    assert tipos == ['canal_cruzado', 'micro_sin_respuesta']
