"""Qué terminales cuentan para dar un bono por finalizado."""
from sqlalchemy import text


def _sql(app, sentencia, **p):
    from app.routes.base import db
    with app.app_context():
        db.session.execute(text(sentencia), p)
        db.session.commit()


def test_solo_cuentan_terminales_trabajables(app):
    _sql(app, "INSERT INTO puestos (id, nombre) VALUES ('P1', 'Puesto 1')")
    _sql(app, "INSERT INTO maquinas (id, puesto_id, nombre, activo) VALUES ('M_ON', 'P1', 'On', 1)")
    _sql(app, "INSERT INTO maquinas (id, puesto_id, nombre, activo) VALUES ('M_OFF', 'P1', 'Off', 0)")
    _sql(app, "INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES ('M_ON', 'T_OK')")
    _sql(app, "INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES ('M_ON', 'T_IGN')")
    _sql(app, "INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES ('M_OFF', 'T_MAQ_OFF')")
    _sql(app, "INSERT INTO maquinas_terminales (maquina_id, terminal_codigo) VALUES ('M_ON', 'KN-PELAR-6MM')")
    _sql(app, "INSERT INTO terminales_ignorados (terminal_codigo) VALUES ('T_IGN')")

    from app.routes.progreso import _terminales_trabajables
    with app.app_context():
        todos = {'T_OK', 'T_IGN', 'T_MAQ_OFF', 'T_SIN_MAQUINA', 'KN-PELAR-6MM'}
        assert _terminales_trabajables(todos) == {'T_OK'}
