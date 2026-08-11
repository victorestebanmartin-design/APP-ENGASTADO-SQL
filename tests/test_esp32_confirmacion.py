"""Confirmación física en el carro con los 8 pulsadores de la pantalla.

Los botones 1-7 identifican un PUESTO y el 8 es OK. El operario que llega al
carro pulsa el botón de su puesto, ve sus paquetes y confirma con OK: primero
la RECOGIDA (fase=recoger) y, al terminar el grupo, la DEVOLUCIÓN
(fase=devolver). Hasta cada confirmación el PC no deja avanzar.
"""


def _registrar_pantalla(client, dev_id='aabbcc'):
    """Simula una pantalla que hace poll y queda registrada."""
    client.get(f'/api/esp32/current?id={dev_id}')
    return dev_id


def _asignar_carro(admin_client, dev_id, carro):
    return admin_client.post(f'/api/esp32/devices/{dev_id}', json={'carro': carro})


def _confirmar(client, fase='recoger', carro='3', puesto='puesto_001',
               lote='lote1', grupo='1', tipo='confirmacion'):
    return client.get(f'/api/esp32/evento?tipo={tipo}&fase={fase}&id=aabbcc'
                      f'&carro={carro}&puesto={puesto}&operario=PEPE'
                      f'&lote={lote}&grupo={grupo}')


def _estado(client, carro='3', puesto='puesto_001'):
    return client.get(f'/api/esp32/estado-carro?carro={carro}&puesto={puesto}').get_json()


# ── Estado de la pantalla ─────────────────────────────────────────────────

def test_estado_carro_sin_pantalla_no_bloquea(client):
    """Sin pantalla asignada al carro, display=False: el PC no debe bloquear."""
    d = _estado(client, carro='9')
    assert d['success']
    assert not d['display']
    assert d['confirmacion'] is None


def test_estado_carro_requiere_carro(client):
    assert client.get('/api/esp32/estado-carro').status_code == 400


def test_pantalla_asignada_se_ve_viva(client, admin_client):
    dev_id = _registrar_pantalla(client)
    _asignar_carro(admin_client, dev_id, '3')
    d = _estado(client)
    assert d['display']
    assert d['viva']          # acaba de hacer poll


# ── Recogida y devolución ─────────────────────────────────────────────────

def test_recogida_queda_registrada(client):
    assert _confirmar(client, fase='recoger', grupo='2').get_json()['success']
    c = _estado(client)['confirmacion']
    assert c['lote'] == 'lote1'
    assert c['fase'] == 'recoger'
    assert c['grupo'] == '2'
    assert c['operario'] == 'PEPE'


def test_devolucion_sustituye_a_la_recogida(client):
    """El ciclo del grupo: primero se recoge, al acabar se devuelve."""
    _confirmar(client, fase='recoger', lote='lote1')
    assert _estado(client)['confirmacion']['fase'] == 'recoger'

    _confirmar(client, fase='devolver', lote='dev1')
    c = _estado(client)['confirmacion']
    assert c['fase'] == 'devolver'
    assert c['lote'] == 'dev1'


def test_la_recogida_de_un_lote_no_vale_para_el_siguiente(client):
    """Al pasar de grupo cambia el lote: hay que volver al carro."""
    _confirmar(client, fase='recoger', lote='lote1')
    c = _estado(client)['confirmacion']
    assert c['lote'] == 'lote1'      # el PC compara contra el lote que muestra
    assert c['lote'] != 'lote2'


# ── Aislamiento por puesto ────────────────────────────────────────────────

def test_confirmacion_es_por_puesto_y_carro(client):
    _confirmar(client, puesto='puesto_001', carro='3')

    # Otro puesto del mismo carro no hereda la confirmación
    assert _estado(client, carro='3', puesto='puesto_002')['confirmacion'] is None
    # Ni el mismo puesto en otro carro
    assert _estado(client, carro='4', puesto='puesto_001')['confirmacion'] is None


def test_dos_puestos_confirman_de_forma_independiente(client):
    _confirmar(client, puesto='puesto_001', lote='l1')
    _confirmar(client, puesto='puesto_002', lote='l2', fase='devolver')

    a = _estado(client, puesto='puesto_001')['confirmacion']
    b = _estado(client, puesto='puesto_002')['confirmacion']
    assert a['lote'] == 'l1' and a['fase'] == 'recoger'
    assert b['lote'] == 'l2' and b['fase'] == 'devolver'


# ── Salida de emergencia y validación ─────────────────────────────────────

def test_confirmacion_manual_se_distingue(client):
    """La salida de emergencia desde el PC queda marcada como manual."""
    _confirmar(client, tipo='confirmacion_manual', lote='lote9')
    assert _estado(client)['confirmacion']['tipo'] == 'confirmacion_manual'


def test_evento_requiere_tipo(client):
    assert client.get('/api/esp32/evento?carro=3').status_code == 400


def test_evento_sin_fase_asume_recogida(client):
    client.get('/api/esp32/evento?tipo=confirmacion&carro=3&puesto=puesto_001&lote=x')
    assert _estado(client)['confirmacion']['fase'] == 'recoger'
