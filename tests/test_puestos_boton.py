"""Asignación del botón de la pantalla del carro a cada puesto (1-7)."""


def _un_puesto(client, n=0):
    return client.get('/api/puestos').get_json()['puestos'][n]


def test_puestos_nacen_sin_boton(client):
    assert _un_puesto(client).get('boton') is None


def test_asignar_boton_a_un_puesto(admin_client, client):
    p = _un_puesto(client)
    r = admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': 3})
    assert r.get_json()['success'], r.get_json()

    assert next(x for x in client.get('/api/puestos').get_json()['puestos']
                if x['id'] == p['id'])['boton'] == 3


def test_quitar_el_boton(admin_client, client):
    p = _un_puesto(client)
    admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': 3})
    assert admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': None}).get_json()['success']

    assert next(x for x in client.get('/api/puestos').get_json()['puestos']
                if x['id'] == p['id'])['boton'] is None


def test_un_boton_no_puede_estar_en_dos_puestos(admin_client, client):
    puestos = client.get('/api/puestos').get_json()['puestos']
    a, b = puestos[0], puestos[1]

    assert admin_client.put(f'/api/puestos/{a["id"]}', json={'boton': 5}).get_json()['success']

    r = admin_client.put(f'/api/puestos/{b["id"]}', json={'boton': 5})
    assert r.status_code == 409
    assert a['nombre'] in r.get_json()['message']


def test_reasignar_el_mismo_boton_al_mismo_puesto_no_falla(admin_client, client):
    p = _un_puesto(client)
    admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': 2})
    assert admin_client.put(f'/api/puestos/{p["id"]}',
                            json={'boton': 2, 'nombre': p['nombre']}).get_json()['success']


def test_el_boton_8_esta_reservado_para_ok(admin_client, client):
    p = _un_puesto(client)
    r = admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': 8})
    assert r.status_code == 400
    assert 'OK' in r.get_json()['message']


def test_boton_fuera_de_rango_o_invalido(admin_client, client):
    p = _un_puesto(client)
    assert admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': -1}).status_code == 400
    assert admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': 'x'}).status_code == 400


def test_boton_cero_equivale_a_sin_boton(admin_client, client):
    p = _un_puesto(client)
    admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': 4})
    assert admin_client.put(f'/api/puestos/{p["id"]}', json={'boton': 0}).get_json()['success']
    assert next(x for x in client.get('/api/puestos').get_json()['puestos']
                if x['id'] == p['id'])['boton'] is None


def test_asignar_boton_requiere_admin(client):
    p = _un_puesto(client)
    assert client.put(f'/api/puestos/{p["id"]}', json={'boton': 4}).status_code == 401
