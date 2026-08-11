"""Confirmación física del lote en el carro (pulsador de la pantalla ESP32).

El PC no deja empezar un grupo de paquetes hasta que el operario confirma en
la pantalla del carro; estos tests cubren el circuito servidor de ese gesto.
"""


def _registrar_pantalla(client, dev_id='aabbcc', carro='3'):
    """Simula una pantalla que hace poll y queda asignada a un carro."""
    client.get(f'/api/esp32/current?id={dev_id}')
    return dev_id


def _asignar_carro(admin_client, dev_id, carro):
    return admin_client.post(f'/api/esp32/devices/{dev_id}', json={'carro': carro})


def test_estado_carro_sin_pantalla_no_bloquea(client):
    """Sin pantalla asignada al carro, display=False: el PC no debe bloquear."""
    d = client.get('/api/esp32/estado-carro?carro=9&operario=PEPE').get_json()
    assert d['success']
    assert not d['display']
    assert d['confirmacion'] is None


def test_estado_carro_requiere_carro(client):
    assert client.get('/api/esp32/estado-carro').status_code == 400


def test_pantalla_asignada_se_ve_viva(client, admin_client):
    dev_id = _registrar_pantalla(client)
    _asignar_carro(admin_client, dev_id, '3')
    d = client.get('/api/esp32/estado-carro?carro=3&operario=PEPE').get_json()
    assert d['display']
    assert d['viva']          # acaba de hacer poll


def test_confirmacion_del_lote_queda_registrada(client):
    r = client.get('/api/esp32/evento?tipo=confirmacion&id=aabbcc'
                   '&carro=3&operario=PEPE&lote=lote1&grupo=2')
    assert r.get_json()['success']

    d = client.get('/api/esp32/estado-carro?carro=3&operario=PEPE').get_json()
    assert d['confirmacion']['lote'] == 'lote1'
    assert d['confirmacion']['grupo'] == '2'
    assert d['confirmacion']['tipo'] == 'confirmacion'


def test_confirmacion_es_por_operario_y_carro(client):
    client.get('/api/esp32/evento?tipo=confirmacion&carro=3&operario=PEPE&lote=lote1')

    # Otro operario del mismo carro no hereda la confirmación
    d = client.get('/api/esp32/estado-carro?carro=3&operario=MARIA').get_json()
    assert d['confirmacion'] is None

    # Ni el mismo operario en otro carro
    d = client.get('/api/esp32/estado-carro?carro=4&operario=PEPE').get_json()
    assert d['confirmacion'] is None


def test_lote_nuevo_invalida_la_confirmacion_anterior(client):
    """Al pasar al siguiente grupo el lote cambia: hay que volver al carro."""
    client.get('/api/esp32/evento?tipo=confirmacion&carro=3&operario=PEPE&lote=lote1&grupo=1')
    client.get('/api/esp32/evento?tipo=confirmacion&carro=3&operario=PEPE&lote=lote2&grupo=2')

    d = client.get('/api/esp32/estado-carro?carro=3&operario=PEPE').get_json()
    assert d['confirmacion']['lote'] == 'lote2'   # el PC compara contra su lote


def test_confirmacion_manual_se_distingue(client):
    """La salida de emergencia desde el PC queda marcada como manual."""
    client.get('/api/esp32/evento?tipo=confirmacion_manual&carro=3&operario=PEPE&lote=lote9')
    d = client.get('/api/esp32/estado-carro?carro=3&operario=PEPE').get_json()
    assert d['confirmacion']['tipo'] == 'confirmacion_manual'


def test_evento_requiere_tipo(client):
    assert client.get('/api/esp32/evento?carro=3').status_code == 400
