# Tests de los endpoints de la pantalla ESP32: push/current con canal por carro.


def test_push_y_current_global(client):
    r = client.post('/api/esp32/push', json={
        'carro': 'A2', 'orden': 'ORD-77',
        'paquetes': [{'etiqueta': 1, 'elem': 'E1'}]
    })
    assert r.status_code == 200 and r.get_json()['ok']

    # La pantalla generica (sin carro asignado) ve el ultimo push
    d = client.get('/api/esp32/current').get_json()
    assert d['data']['carro'] == 'A2'


def test_canal_por_carro(client):
    client.post('/api/esp32/push', json={'carro': 'A2', 'paquetes': [{'etiqueta': 1, 'elem': 'E1'}]})
    client.post('/api/esp32/push', json={'carro': 'B9', 'paquetes': [{'etiqueta': 7, 'elem': 'E7'}]})

    # Cada pantalla asignada solo ve su carro
    assert client.get('/api/esp32/current?carro=A2').get_json()['data']['carro'] == 'A2'
    assert client.get('/api/esp32/current?carro=B9').get_json()['data']['carro'] == 'B9'
    # Un carro sin datos devuelve vacio
    assert client.get('/api/esp32/current?carro=ZZ').get_json()['data'] is None
    # La global ve el ultimo (B9)
    assert client.get('/api/esp32/current').get_json()['data']['carro'] == 'B9'


def test_clear_limpia_su_canal_y_el_global(client):
    client.post('/api/esp32/push', json={'carro': 'A2', 'paquetes': [{'etiqueta': 1, 'elem': 'E1'}]})
    client.post('/api/esp32/push', json={'clear': True, 'carro': 'A2'})

    assert client.get('/api/esp32/current?carro=A2').get_json()['data'] == {'clear': True, 'carro': 'A2'}
    assert client.get('/api/esp32/current').get_json()['data'] == {'clear': True, 'carro': 'A2'}


def test_pantalla_se_registra_y_admin_le_asigna_carro(client, admin_client):
    # La pantalla hace poll con su id → queda registrada
    d = client.get('/api/esp32/current?id=aabbccdd1122&esp32_ip=192.168.1.47').get_json()
    assert d['carro_asignado'] == ''

    # El admin la ve en la lista con su IP
    lista = admin_client.get('/api/esp32/devices').get_json()
    dev = next(x for x in lista['devices'] if x['id'] == 'aabbccdd1122')
    assert dev['ip'] == '192.168.1.47' and dev['online']

    # El admin le asigna nombre y carro
    r = admin_client.post('/api/esp32/devices/aabbccdd1122',
                          json={'nombre': 'Pantalla lado A', 'carro': '3'})
    assert r.status_code == 200

    # Se publica trabajo del carro 3 y de otro carro
    client.post('/api/esp32/push', json={'carro': '3', 'paquetes': [{'etiqueta': 5, 'elem': 'E5'}]})
    client.post('/api/esp32/push', json={'carro': '8', 'paquetes': [{'etiqueta': 9, 'elem': 'E9'}]})

    # La pantalla ahora lee SOLO el canal de su carro y sabe su asignacion
    d = client.get('/api/esp32/current?id=aabbccdd1122').get_json()
    assert d['carro_asignado'] == '3'
    assert d['data']['carro'] == '3'

    # DELETE la olvida
    admin_client.delete('/api/esp32/devices/aabbccdd1122')
    lista = admin_client.get('/api/esp32/devices').get_json()
    assert all(x['id'] != 'aabbccdd1122' for x in lista['devices'])


def test_gestion_de_pantallas_requiere_admin(client):
    # Sin sesion de admin: redirige a la pantalla de PIN
    r = client.get('/api/esp32/devices')
    assert r.status_code in (301, 302, 401, 403)
    r = client.post('/api/esp32/devices/aabbccdd1122', json={'carro': '1'})
    assert r.status_code in (301, 302, 401, 403)


def test_carro_con_caracteres_raros_no_escapa_de_data(client, app):
    import os
    r = client.post('/api/esp32/push', json={'carro': '../evil', 'paquetes': []})
    assert r.status_code == 200
    data_dir = app.config['DATA_DIR']
    ficheros = os.listdir(data_dir)
    # El slug sanea la ruta: todo queda dentro de DATA_DIR
    assert any(f.startswith('esp32_current_') for f in ficheros)
    assert not os.path.exists(os.path.join(os.path.dirname(data_dir), 'evil'))
