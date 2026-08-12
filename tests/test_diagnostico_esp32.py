"""Panel de chequeo (Admin -> Diagnóstico ESP32): historial de eventos
físicos (botones + NFC) usado para verificar hardware sin depender solo
del 'online'."""


def _operario_con_tag(client, nombre, tag):
    op = client.post('/api/operarios', json={'nombre': nombre}).get_json()['operario']
    client.put(f'/api/operarios/{op["id"]}', json={'tag_uid': tag})
    return op


def test_eventos_vacio_al_principio(admin_client):
    d = admin_client.get('/api/esp32/eventos').get_json()
    assert d['success']
    assert d['eventos'] == []


def test_eventos_requiere_pin(client):
    """Sin sesión de admin, el historial de eventos no es accesible."""
    assert client.get('/api/esp32/eventos').status_code == 401


def test_boton_del_carro_aparece_en_el_historial(client, admin_client):
    client.get('/api/esp32/evento?tipo=confirmacion&fase=recoger&id=aabbcc'
               '&carro=3&puesto=puesto_001&operario=PEPE&lote=l1&grupo=1')
    eventos = admin_client.get('/api/esp32/eventos').get_json()['eventos']
    assert len(eventos) == 1
    assert eventos[0]['tipo'] == 'confirmacion'
    assert eventos[0]['operario'] == 'PEPE'


def test_eventos_mas_recientes_primero(client, admin_client):
    client.get('/api/esp32/evento?tipo=tag&uid=AABBCCDD&carro=3')
    client.get('/api/esp32/evento?tipo=liberar&carro=3&puesto=puesto_001')
    eventos = admin_client.get('/api/esp32/eventos').get_json()['eventos']
    assert eventos[0]['tipo'] == 'liberar'
    assert eventos[1]['tipo'] == 'tag'


def test_entrada_rfid_ok_queda_registrada(client, admin_client):
    _operario_con_tag(client, 'ANA', 'AA11BB22')
    r = client.post('/api/puestos/engastado_v3/entrada',
                     json={'tag_uid': 'AA11BB22', 'device_id': 'lector1'})
    assert r.status_code == 200

    eventos = admin_client.get('/api/esp32/eventos').get_json()['eventos']
    assert eventos[0]['tipo'] == 'entrada_rfid'
    assert eventos[0]['operario'] == 'ANA'
    assert eventos[0]['uid'] == 'AA11BB22'


def test_entrada_rfid_tarjeta_no_registrada_tambien_queda_registrada(client, admin_client):
    r = client.post('/api/puestos/engastado_v3/entrada',
                     json={'tag_uid': 'FFEEDDCC', 'device_id': 'lector1'})
    assert r.status_code == 404

    eventos = admin_client.get('/api/esp32/eventos').get_json()['eventos']
    assert eventos[0]['tipo'] == 'entrada_rfid'
    assert eventos[0]['operario'] == ''
    assert 'no registrada' in eventos[0]['detalle'].lower()


def test_dispositivo_nombre_se_resuelve_desde_lectores_rfid(client, admin_client):
    admin_client.post('/api/esp32/rfid/devices/lector1', json={'nombre': 'Entrada Nave'})
    _operario_con_tag(client, 'ANA', 'AA11BB22')
    client.post('/api/puestos/engastado_v3/entrada',
                json={'tag_uid': 'AA11BB22', 'device_id': 'lector1'})

    eventos = admin_client.get('/api/esp32/eventos').get_json()['eventos']
    assert eventos[0]['dispositivo_nombre'] == 'Entrada Nave'


def test_limite_de_eventos(client, admin_client):
    for i in range(5):
        client.get(f'/api/esp32/evento?tipo=tag&uid=AA{i:06d}&carro=3')
    eventos = admin_client.get('/api/esp32/eventos?limite=2').get_json()['eventos']
    assert len(eventos) == 2
