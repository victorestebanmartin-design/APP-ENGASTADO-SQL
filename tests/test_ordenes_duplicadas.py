"""Limpieza al arrancar de las órdenes con el número repetido (app/ordenes_duplicadas.py)."""
import logging
import os
import sqlite3

from app.ordenes_duplicadas import limpiar

LOG = logging.getLogger('test_duplicadas')


def _bd(app):
    return app.config['DB_PATH']


def _orden(app, oid, numero, corte='CC1', estado='pendiente', bono=None, carro=None,
           fecha='2026-01-01 10:00:00'):
    with sqlite3.connect(_bd(app)) as c:
        if bono:
            c.execute("INSERT OR IGNORE INTO bonos (id, nombre) VALUES (?, ?)", (bono, bono))
        c.execute(
            "INSERT INTO ordenes_produccion (id, codigo_corte, numero, estado, bono_id, "
            "carro_numero, fecha_creacion) VALUES (?,?,?,?,?,?,?)",
            (oid, corte, numero, estado, bono, carro, fecha))


def _ids(app):
    with sqlite3.connect(_bd(app)) as c:
        return {f[0] for f in c.execute("SELECT id FROM ordenes_produccion")}


def _copias(app):
    return [n for n in os.listdir(os.path.dirname(_bd(app))) if 'antes_duplicadas' in n]


def test_sin_duplicadas_no_hace_nada_ni_copia(app):
    _orden(app, 'a', '600')
    _orden(app, 'b', '601')
    assert limpiar(_bd(app), LOG) == 0
    assert _ids(app) == {'a', 'b'}
    assert _copias(app) == []


def test_borra_la_copia_vacia_y_se_queda_la_que_tiene_trabajo(app):
    _orden(app, 'vieja_vacia', '600', fecha='2026-01-01 10:00:00')
    _orden(app, 'en_bono', '600', estado='en_bono', bono='B1', fecha='2026-01-02 10:00:00')
    assert limpiar(_bd(app), LOG) == 1
    assert _ids(app) == {'en_bono'}
    # Hay copia previa, con las dos órdenes dentro
    (copia,) = _copias(app)
    assert copia.startswith('engastado') and 'backup' in copia
    with sqlite3.connect(os.path.join(os.path.dirname(_bd(app)), copia)) as c:
        assert c.execute("SELECT COUNT(*) FROM ordenes_produccion").fetchone()[0] == 2


def test_si_todas_estan_vacias_se_queda_la_mas_antigua(app):
    _orden(app, 'segunda', '600', fecha='2026-01-02 10:00:00')
    _orden(app, 'primera', '600', fecha='2026-01-01 10:00:00')
    _orden(app, 'tercera', ' 600 ', fecha='2026-01-03 10:00:00')   # con espacios: es la misma
    assert limpiar(_bd(app), LOG) == 2
    assert _ids(app) == {'primera'}
    assert limpiar(_bd(app), LOG) == 0      # y repetirlo no borra más


def test_no_toca_las_que_tienen_trabajo_ni_las_de_otro_corte(app, caplog):
    _orden(app, 'completada', '600', estado='completado')
    _orden(app, 'en_bono', '600', estado='en_bono', bono='B1')
    _orden(app, 'otro_corte', '700', corte='CC1')
    _orden(app, 'otro_corte_2', '700', corte='CC2')
    with caplog.at_level(logging.WARNING, logger='test_duplicadas'):
        assert limpiar(_bd(app), LOG) == 0
    assert _ids(app) == {'completada', 'en_bono', 'otro_corte', 'otro_corte_2'}
    assert _copias(app) == []
    avisos = ' '.join(r.getMessage() for r in caplog.records)
    assert 'numero 600' in avisos and 'numero 700' in avisos


def test_una_pendiente_con_algo_colgando_no_se_borra(app):
    """Pendiente y sin bono, pero ya con trabajo de mangueras: no es una copia vacía."""
    _orden(app, 'con_mangueras', '600', fecha='2026-01-02 10:00:00')
    _orden(app, 'con_carro', '600', carro=1, fecha='2026-01-03 10:00:00')
    _orden(app, 'vacia', '600', fecha='2026-01-04 10:00:00')
    with sqlite3.connect(_bd(app)) as c:
        c.execute("INSERT OR IGNORE INTO carros (numero) VALUES (1)")
        c.execute("INSERT INTO mangueras_preparaciones (orden_id, inicio) VALUES ('con_mangueras', '2026-01-02')")
    assert limpiar(_bd(app), LOG) == 1
    assert _ids(app) == {'con_mangueras', 'con_carro'}


def test_se_ejecuta_al_arrancar(app):
    """create_app pasa por las migraciones: una BD con duplicadas sale limpia."""
    _orden(app, 'una', '600', fecha='2026-01-01 10:00:00')
    _orden(app, 'otra', '600', fecha='2026-01-02 10:00:00')
    from app import _apply_migrations
    _apply_migrations(_bd(app))
    assert _ids(app) == {'una'}
