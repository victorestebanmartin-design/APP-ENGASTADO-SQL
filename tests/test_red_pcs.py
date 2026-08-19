"""PCs detectados en Admin -> Red y placas: olvidarlos a mano y que caduquen.

Al cambiarle la IP a un PC, la vieja se quedaba en la lista para siempre: un
equipo fantasma que ya no existe y que no había forma de quitar.
"""
import json
import os
from datetime import datetime, timedelta


def _anotar_pc(app, ip, hace_dias=0):
    """Mete un PC en pcs_vistos.json con la antigüedad que se quiera."""
    with app.app_context():
        from app.routes.sistema import _pcs_vistos_file, _pcs_vistos_cargar
        pcs = _pcs_vistos_cargar()
        pcs[ip] = {'last_seen': (datetime.now() - timedelta(days=hace_dias)).isoformat()}
        with open(_pcs_vistos_file(), 'w', encoding='utf-8') as f:
            json.dump(pcs, f)


def _pcs_listados(admin_client):
    d = admin_client.get('/api/esp32/ips').get_json()
    return {p['ip_vista'] for p in d['placas'] if p['tipo'] == 'pc'}


def test_un_pc_visto_aparece_en_la_lista(app, admin_client):
    _anotar_pc(app, '192.168.50.3')
    assert '192.168.50.3' in _pcs_listados(admin_client)


def test_se_puede_olvidar_a_mano(app, admin_client):
    _anotar_pc(app, '192.168.50.3')
    r = admin_client.delete('/api/red/pcs/192.168.50.3')
    assert r.get_json()['success']
    assert '192.168.50.3' not in _pcs_listados(admin_client)


def test_olvidar_uno_no_se_lleva_por_delante_a_los_demas(app, admin_client):
    _anotar_pc(app, '192.168.50.3')
    _anotar_pc(app, '192.168.50.10')
    admin_client.delete('/api/red/pcs/192.168.50.3')
    assert _pcs_listados(admin_client) == {'192.168.50.10'}


def test_olvidar_uno_que_no_existe_avisa(admin_client):
    r = admin_client.delete('/api/red/pcs/192.168.50.77')
    assert r.status_code == 404
    assert r.get_json()['success'] is False


def test_olvidar_exige_pin(app, client):
    _anotar_pc(app, '192.168.50.3')
    r = client.delete('/api/red/pcs/192.168.50.3')
    assert r.status_code == 401


def test_un_pc_que_lleva_dias_sin_verse_desaparece_solo(app, admin_client):
    _anotar_pc(app, '192.168.50.3', hace_dias=10)
    _anotar_pc(app, '192.168.50.10', hace_dias=0)
    assert _pcs_listados(admin_client) == {'192.168.50.10'}


def test_un_pc_apagado_el_fin_de_semana_sigue_saliendo(app, admin_client):
    _anotar_pc(app, '192.168.50.10', hace_dias=2)
    assert '192.168.50.10' in _pcs_listados(admin_client)


def test_si_vuelve_a_dar_señales_reaparece(app, admin_client):
    """Olvidarlo no es permanente: el PC vivo se vuelve a anotar solo."""
    _anotar_pc(app, '192.168.50.3')
    admin_client.delete('/api/red/pcs/192.168.50.3')
    assert '192.168.50.3' not in _pcs_listados(admin_client)

    with app.app_context():
        from app.routes.sistema import _pc_registrar
        _pc_registrar('192.168.50.3')
    assert '192.168.50.3' in _pcs_listados(admin_client)


def test_registrar_limpia_de_paso_los_caducados(app, admin_client):
    _anotar_pc(app, '192.168.50.3', hace_dias=10)
    with app.app_context():
        from app.routes.sistema import _pc_registrar, _pcs_vistos_cargar
        _pc_registrar('192.168.50.10')
        quedan = set(_pcs_vistos_cargar())
    assert quedan == {'192.168.50.10'}


def test_la_lista_dice_cuando_se_vio_cada_pc(app, admin_client):
    _anotar_pc(app, '192.168.50.3', hace_dias=2)
    _anotar_pc(app, '192.168.50.10', hace_dias=0)
    placas = admin_client.get('/api/esp32/ips').get_json()['placas']
    por_ip = {p['ip_vista']: p for p in placas if p['tipo'] == 'pc'}

    assert por_ip['192.168.50.10']['visto_hace_min'] < 2
    assert por_ip['192.168.50.3']['visto_hace_min'] >= 2 * 24 * 60
    # y ambos se pueden olvidar desde la propia lista
    assert por_ip['192.168.50.3']['olvidable'] is True
