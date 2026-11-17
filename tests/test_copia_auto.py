"""Copia automática: verificada, con todo lo que no vive en la BD, y además en
un disco externo cuando lo hay, sin que su ausencia deje a la planta sin copia."""
import os
import shutil
import sqlite3
from datetime import datetime, timedelta

import pytest

from app import backup_auto


@pytest.fixture
def datos(app):
    """data/ con una BD de verdad, un PDF de máquina, un manguito y un Excel."""
    data = app.config['DATA_DIR']
    shutil.copyfile(app.config['DB_PATH'], os.path.join(data, 'engastado.db'))
    for carpeta, nombre, contenido in (('maquinas_pdf', 'maq.pdf', b'%PDF'),
                                       ('manguitos', 'lista 1.txt', b'manguito'),
                                       ('cortes', 'corte.xlsx', b'excel')):
        os.makedirs(os.path.join(data, carpeta), exist_ok=True)
        with open(os.path.join(data, carpeta, nombre), 'wb') as f:
            f.write(contenido)
    return data


@pytest.fixture
def disco_externo(tmp_path, monkeypatch):
    """Una carpeta que hace de disco externo. En los tests está en el mismo
    disco que data/, así que se desactiva esa comprobación."""
    ruta = tmp_path / 'disco_E' / 'CopiasCOJOsw'
    ruta.mkdir(parents=True)
    monkeypatch.setattr(backup_auto, '_mismo_disco', lambda a, b: False)
    return str(ruta)


def _carpetas(base):
    return sorted(d for d in os.listdir(base) if d.startswith('backup_'))


# ── Qué lleva una copia ─────────────────────────────────────────────────────

def test_la_copia_lleva_bd_documentos_de_maquinas_y_manguitos(app, datos):
    _, carpeta, problemas = backup_auto._una_copia(datos, app.logger)
    assert problemas == []
    for relativo in ('engastado.db', 'maquinas_pdf/maq.pdf', 'manguitos/lista 1.txt',
                     'cortes/corte.xlsx'):
        assert os.path.isfile(os.path.join(carpeta, relativo)), relativo


def test_una_bd_danada_no_pasa_la_verificacion(tmp_path, app):
    ruta = str(tmp_path / 'rota.db')
    shutil.copyfile(app.config['DB_PATH'], ruta)
    with open(ruta, 'r+b') as f:
        f.seek(100)
        f.write(b'\xff' * 4000)
    assert backup_auto._verificar_db(ruta) is not None
    assert backup_auto._verificar_db(app.config['DB_PATH']) is None


# ── Una ronda: servidor y disco externo ─────────────────────────────────────

def test_sin_disco_externo_copia_en_el_servidor_y_lo_avisa(app, datos):
    estado = backup_auto.hacer_ronda(app)
    assert estado['local']['ok'], estado
    assert 'externo' not in estado
    assert len(_carpetas(os.path.join(datos, 'backups_auto'))) == 1

    resumen = backup_auto.resumen_estado(app)
    assert any('solo están en el disco del servidor' in a for a in resumen['avisos'])


def test_con_disco_externo_copia_en_los_dos_sitios(app, datos, disco_externo):
    backup_auto.guardar_destino(app, disco_externo)
    estado = backup_auto.hacer_ronda(app)

    assert estado['local']['ok'] and estado['externo']['ok'], estado
    [copia] = _carpetas(disco_externo)
    assert os.path.isfile(os.path.join(disco_externo, copia, 'engastado.db'))
    assert os.path.isfile(os.path.join(disco_externo, copia, 'maquinas_pdf', 'maq.pdf'))
    assert backup_auto.resumen_estado(app)['avisos'] == []


def test_disco_desenchufado_avisa_y_no_deja_sin_copia(app, datos, disco_externo):
    backup_auto.guardar_destino(app, disco_externo)
    assert backup_auto.hacer_ronda(app)['externo']['ok']
    primera_ok = backup_auto.resumen_estado(app)['externo']['ultima_ok']

    shutil.rmtree(os.path.dirname(disco_externo))          # se llevan el disco
    estado = backup_auto.hacer_ronda(app)

    assert estado['local']['ok']                           # el servidor sigue copiando
    assert not estado['externo']['ok']
    assert 'enchufado' in estado['externo']['detalle']
    assert estado['externo']['ultima_ok'] == primera_ok    # se recuerda la última buena
    assert not os.path.exists(disco_externo)               # y no se crea en otro sitio
    assert any('enchufado' in a for a in backup_auto.resumen_estado(app)['avisos'])


def test_un_fallo_a_mitad_en_el_disco_externo_no_tumba_la_ronda(app, datos, disco_externo, monkeypatch):
    backup_auto.guardar_destino(app, disco_externo)
    real = backup_auto._una_copia

    def falla_en_el_externo(data_dir, logger, destino_base=None):
        if destino_base == disco_externo:
            raise OSError('el disco se ha desconectado')
        return real(data_dir, logger, destino_base)

    monkeypatch.setattr(backup_auto, '_una_copia', falla_en_el_externo)
    estado = backup_auto.hacer_ronda(app)
    assert estado['local']['ok']
    assert not estado['externo']['ok']
    assert 'desconectado' in estado['externo']['detalle']


def test_cada_sitio_guarda_solo_las_ultimas(app, datos, disco_externo, monkeypatch):
    app.config['AUTO_BACKUP_RETENER'] = 2
    backup_auto.guardar_destino(app, disco_externo)
    for segundo in range(4):
        sello = datetime(2026, 11, 17, 10, 0, segundo)
        monkeypatch.setattr(backup_auto, 'datetime',
                            type('Reloj', (datetime,), {'now': classmethod(lambda cls, s=sello: s)}))
        backup_auto.hacer_ronda(app)
    assert len(_carpetas(os.path.join(datos, 'backups_auto'))) == 2
    assert len(_carpetas(disco_externo)) == 2


def test_dos_rondas_a_la_vez_no_se_pisan(app, datos):
    with backup_auto._RONDA:
        assert backup_auto.hacer_ronda(app) is None


def test_avisa_si_hace_mucho_que_no_hay_copia_buena(app, datos):
    backup_auto.hacer_ronda(app)
    assert backup_auto.resumen_estado(app)['avisos'] != []        # sin disco externo
    dentro_de_dos_dias = datetime.now() + timedelta(days=2)
    avisos = backup_auto.resumen_estado(app, ahora=dentro_de_dos_dias)['avisos']
    assert any('No hay una copia buena en el servidor' in a for a in avisos)


# ── La carpeta del disco externo ────────────────────────────────────────────

def test_la_carpeta_tiene_que_existir_y_ser_de_otro_disco(app, tmp_path):
    data = app.config['DATA_DIR']
    assert 'ruta completa' in backup_auto.error_destino('CopiasCOJOsw', data)
    assert 'no existe' in backup_auto.error_destino(str(tmp_path / 'no_esta'), data)
    if os.name == 'nt':
        assert 'mismo disco' in backup_auto.error_destino(str(tmp_path), data)


def test_una_carpeta_valida_se_acepta(app, disco_externo):
    assert backup_auto.error_destino(disco_externo, app.config['DATA_DIR']) is None
    assert os.listdir(disco_externo) == []        # la prueba de escritura no deja rastro


def test_el_env_manda_sobre_lo_de_admin(app, disco_externo):
    backup_auto.guardar_destino(app, disco_externo)
    app.config['AUTO_BACKUP_DESTINO'] = r'F:\OtraCarpeta'
    assert backup_auto.destino_externo(app) == r'F:\OtraCarpeta'
    assert backup_auto.destino_fijado_por_env(app)


# ── Admin → Sistema ─────────────────────────────────────────────────────────

def test_las_rutas_de_la_copia_piden_admin(client):
    assert client.get('/api/sistema/copia_auto').status_code == 401
    assert client.post('/api/sistema/copia_auto/destino', json={'ruta': 'E:\\x'}).status_code == 401
    assert client.post('/api/sistema/copia_auto/ahora').status_code == 401


def test_admin_fija_el_disco_y_hace_una_copia(admin_client, datos, disco_externo):
    r = admin_client.post('/api/sistema/copia_auto/destino', json={'ruta': 'relativa'})
    assert r.status_code == 400 and 'ruta completa' in r.get_json()['message']

    r = admin_client.post('/api/sistema/copia_auto/destino', json={'ruta': disco_externo})
    assert r.get_json()['success'], r.get_json()
    assert r.get_json()['destino_externo'] == disco_externo

    d = admin_client.post('/api/sistema/copia_auto/ahora').get_json()
    assert d['success'] and d['local']['ok'] and d['externo']['ok'], d
    assert d['avisos'] == []

    d = admin_client.post('/api/sistema/copia_auto/destino', json={'ruta': ''}).get_json()
    assert d['success'] and d['destino_externo'] == ''


def test_con_el_env_no_se_cambia_desde_admin(app, admin_client):
    app.config['AUTO_BACKUP_DESTINO'] = r'F:\Copias'
    r = admin_client.post('/api/sistema/copia_auto/destino', json={'ruta': ''})
    assert r.status_code == 400 and '.env' in r.get_json()['message']
    assert admin_client.get('/api/sistema/copia_auto').get_json()['destino_por_env']


def test_la_copia_ocupada_responde_409(admin_client, datos):
    with backup_auto._RONDA:
        assert admin_client.post('/api/sistema/copia_auto/ahora').status_code == 409
