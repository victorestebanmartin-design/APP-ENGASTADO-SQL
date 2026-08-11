"""Confirmación física en el carro con los 8 pulsadores de la pantalla.

Los botones 1-7 identifican un PUESTO y el 8 es OK. El operario que llega al
carro pulsa el botón de su puesto, ve sus paquetes y confirma con OK: primero
la RECOGIDA (fase=recoger) y, al terminar el grupo, la DEVOLUCIÓN
(fase=devolver). Hasta cada confirmación el PC no deja avanzar.
"""
import os


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


# ── Liberar un puesto colgado ─────────────────────────────────────────────

def _push(client, carro='3', puesto='puesto_001', fase='recoger'):
    return client.post('/api/esp32/push', json={
        'carro': carro, 'puesto_id': puesto, 'puesto_nombre': 'AMP-01',
        'operario': 'PEPE', 'boton': 1, 'fase': fase, 'lote': 'l1',
        'paquetes': [{'etiqueta': 1, 'elem': 'E1'}]
    })


def _puestos_en_pantalla(client, carro='3'):
    ops = client.get(f'/api/esp32/current?carro={carro}').get_json()['ops']
    return [o['data'].get('puesto_id') for o in ops]


def test_el_puesto_aparece_en_el_canal_del_carro(client):
    _push(client)
    assert _puestos_en_pantalla(client) == ['puesto_001']


def test_liberar_saca_al_puesto_de_la_pantalla(client):
    """Salida de emergencia: mantener pulsado el botón del puesto en el carro."""
    _push(client)
    r = client.get('/api/esp32/evento?tipo=liberar&carro=3&puesto=puesto_001&operario=PEPE')
    assert r.get_json()['success']
    assert _puestos_en_pantalla(client) == []


def test_liberar_solo_afecta_a_ese_puesto(client):
    _push(client, puesto='puesto_001')
    _push(client, puesto='puesto_002')
    client.get('/api/esp32/evento?tipo=liberar&carro=3&puesto=puesto_001')
    assert _puestos_en_pantalla(client) == ['puesto_002']


def test_clear_con_puesto_id_libera(client):
    """Al cancelar el modal el navegador manda clear CON puesto_id."""
    _push(client)
    client.post('/api/esp32/push', json={'clear': True, 'carro': '3',
                                         'puesto_id': 'puesto_001', 'operario': 'PEPE'})
    assert _puestos_en_pantalla(client) == []


def test_entrada_sin_latido_caduca(client, app):
    """Sin latido del PC, la entrada desaparece pasado el TTL."""
    import json as _json
    from datetime import datetime, timedelta
    from app.routes import sistema

    _push(client)
    ruta = os.path.join(app.config['DATA_DIR'], 'esp32_current_3.json')
    with open(ruta) as f:
        payload = _json.load(f)
    viejo = (datetime.now() - timedelta(seconds=sistema.ESP32_TTL_S + 60)).isoformat()
    for v in payload['ops'].values():
        v['ts'] = viejo
    with open(ruta, 'w') as f:
        _json.dump(payload, f)

    assert _puestos_en_pantalla(client) == []


# ── Estado del lector NFC de cada pantalla ────────────────────────────────

def test_pantalla_reporta_estado_del_lector(client, admin_client):
    """La pantalla manda &nfc=ok|ko|off en cada poll y Admin lo muestra."""
    client.get('/api/esp32/current?id=aabbcc&nfc=ok')
    dev = next(d for d in admin_client.get('/api/esp32/devices').get_json()['devices']
               if d['id'] == 'aabbcc')
    assert dev['nfc'] == 'ok'

    # Si el lector se cuelga, la pantalla pasa a reportar 'ko'
    client.get('/api/esp32/current?id=aabbcc&nfc=ko')
    dev = next(d for d in admin_client.get('/api/esp32/devices').get_json()['devices']
               if d['id'] == 'aabbcc')
    assert dev['nfc'] == 'ko'


def test_estado_nfc_invalido_se_ignora(client, admin_client):
    client.get('/api/esp32/current?id=aabbcc&nfc=ok')
    client.get('/api/esp32/current?id=aabbcc&nfc=basura')
    dev = next(d for d in admin_client.get('/api/esp32/devices').get_json()['devices']
               if d['id'] == 'aabbcc')
    assert dev['nfc'] == 'ok'      # se queda el último válido


def test_pantalla_sin_lector_no_reporta_nfc(client, admin_client):
    client.get('/api/esp32/current?id=ddeeff')
    dev = next(d for d in admin_client.get('/api/esp32/devices').get_json()['devices']
               if d['id'] == 'ddeeff')
    assert dev['nfc'] == ''
