"""Impresión de la plancha desde el servidor: solo red local y fallos legibles."""
import pytest

from app import impresion_planchas as ip


@pytest.mark.parametrize('valor', ['8.8.8.8', 'impresora.local', '127.0.0.1', '0.0.0.0', '', '224.0.0.1'])
def test_rechaza_lo_que_no_sea_ip_de_red_local(valor):
    with pytest.raises(ip.ErrorImpresion):
        ip.validar_ip_privada(valor)


@pytest.mark.parametrize('valor', ['192.168.1.50', '10.0.0.7', '172.16.5.9'])
def test_acepta_ips_privadas(valor):
    assert ip.validar_ip_privada(valor) == valor


def test_guardar_y_leer_config(tmp_path):
    assert ip.leer_config(str(tmp_path))['ip'] == ''
    ip.guardar_config(str(tmp_path), '192.168.1.50')
    assert ip.leer_config(str(tmp_path)) == {'ip': '192.168.1.50', 'puerto': 9100}
    with pytest.raises(ip.ErrorImpresion):
        ip.guardar_config(str(tmp_path), '1.1.1.1')


def test_endpoint_sin_impresora_responde_200_con_motivo(client, monkeypatch):
    monkeypatch.setattr(ip, 'html_a_pdf', lambda html: b'%PDF-')
    r = client.post('/api/etiquetas/imprimir_plancha', json={
        'archivo': 'x.xlsx', 'grupos': [{'numero_etiqueta': 1, 'cod_cable': 'A', 'elemento': 'EL-1', 'descripcion': 'd', 'seccion': '1.5', 'sub_numero': 0}]})
    assert r.status_code == 200
    d = r.get_json()
    assert d['success'] is False and d['sin_impresora'] is True and d['message']


def test_endpoint_envia_pdf_a_la_ip_configurada(client, app, monkeypatch):
    ip.guardar_config(app.config['DATA_DIR'], '192.168.1.50')
    enviado = {}
    monkeypatch.setattr(ip, 'html_a_pdf', lambda html: b'%PDF-x')
    monkeypatch.setattr(ip, 'enviar_a_impresora', lambda pdf, i, p: enviado.update(pdf=pdf, ip=i, puerto=p))
    r = client.post('/api/etiquetas/imprimir_plancha', json={
        'archivo': 'x.xlsx', 'grupos': [{'numero_etiqueta': 1, 'cod_cable': 'A', 'elemento': 'EL-1', 'descripcion': 'd', 'seccion': '1.5', 'sub_numero': 0}]})
    assert r.get_json()['success'] is True
    assert enviado == {'pdf': b'%PDF-x', 'ip': '192.168.1.50', 'puerto': 9100}


def _etiqueta_en_bd(app, archivo):
    from sqlalchemy import text
    from app.routes.base import db
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO etiquetas_elementos (numero_etiqueta, cod_cable, elemento, descripcion, seccion, "
                "archivo_excel, codigo_corte, sub_numero) VALUES (1, 'A', 'EL-1', 'd', '1.5', :a, 'H01', 0)"),
                {'a': archivo})


def test_imprimir_archivo_sin_etiquetas_explica_el_motivo(client):
    r = client.post('/api/etiquetas/imprimir_archivo', json={'archivo': 'vacio.xlsx'})
    assert r.status_code == 200
    d = r.get_json()
    assert d['success'] is False and 'etiquetas' in d['message']


def test_imprimir_archivo_envia_las_etiquetas_guardadas(client, app, monkeypatch):
    ip.guardar_config(app.config['DATA_DIR'], '192.168.1.50')
    _etiqueta_en_bd(app, 'corte.xlsx')
    enviado = {}
    monkeypatch.setattr(ip, 'html_a_pdf', lambda html: b'%PDF-y')
    monkeypatch.setattr(ip, 'enviar_a_impresora', lambda pdf, i, p: enviado.update(pdf=pdf, ip=i))
    d = client.post('/api/etiquetas/imprimir_archivo', json={'archivo': 'corte.xlsx'}).get_json()
    assert d['success'] is True
    assert enviado == {'pdf': b'%PDF-y', 'ip': '192.168.1.50'}
