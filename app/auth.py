"""
Protección del módulo de administración mediante PIN.

La protección solo se activa si hay un hash de PIN configurado
(Config.ADMIN_PIN_HASH, cargado del .env). Si no lo hay, el decorador
deja pasar todo y la app funciona como siempre.
"""
import os
from datetime import datetime, timedelta
from functools import wraps

from flask import session, redirect, url_for, request, jsonify, current_app

# Claves usadas dentro de la sesión de Flask
SESSION_KEY = 'admin_verificado'
SESSION_TS = 'admin_verificado_ts'


def proteccion_activa():
    """True solo si hay un hash de PIN configurado."""
    return bool(current_app.config.get('ADMIN_PIN_HASH'))


def sesion_admin_valida():
    """True si la sesión de admin está verificada y no ha expirado (8h por defecto)."""
    if not session.get(SESSION_KEY):
        return False
    ts = session.get(SESSION_TS)
    if not ts:
        return False
    try:
        inicio = datetime.fromtimestamp(float(ts))
    except (TypeError, ValueError):
        return False
    horas = current_app.config.get('ADMIN_SESSION_HOURS', 8)
    if datetime.now() - inicio > timedelta(hours=horas):
        return False
    return True


def marcar_sesion_admin():
    """Marca la sesión actual como administración verificada."""
    session[SESSION_KEY] = True
    session[SESSION_TS] = datetime.now().timestamp()


def cerrar_sesion_admin():
    """Cierra la sesión de administración."""
    session.pop(SESSION_KEY, None)
    session.pop(SESSION_TS, None)


def _es_peticion_api():
    """Las rutas de API (que devuelven JSON) empiezan por /api/."""
    return request.path.startswith('/api/')


def requiere_pin_admin(f):
    """Decorador: exige sesión de admin verificada.

    - Si la protección no está activa (sin ADMIN_PIN_HASH), deja pasar.
    - Si la sesión es válida, deja pasar.
    - Si no: rutas de API -> 401 JSON; rutas de página -> redirige al PIN.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not proteccion_activa():
            return f(*args, **kwargs)
        if sesion_admin_valida():
            return f(*args, **kwargs)
        if _es_peticion_api():
            return jsonify({
                'success': False,
                'message': 'Sesión de administración requerida'
            }), 401
        return redirect(url_for('main.admin_pin'))
    return wrapper


# ==================== GATE DE LOGIN GLOBAL (tarjeta + puesto + permisos) ====================
#
# Interruptor maestro de '/' y '/modules': con esto desactivado, la app
# funciona exactamente igual que siempre (sin pedir tarjeta a nadie). Se
# guarda en un JSON (no solo en Config.OPERARIO_GATE_ENABLED, que viene del
# .env) para poder activarlo/desactivarlo en caliente desde Admin -> Sistema
# sin reiniciar el servidor -- imprescindible mientras se configuran los
# permisos reales de cada operario antes de exigirlos de verdad.

def _gate_operario_file():
    return os.path.join(current_app.config['DATA_DIR'], 'operario_gate.json')


def gate_operario_activo():
    """True si el gate de login global esta activo ahora mismo."""
    try:
        import json
        with open(_gate_operario_file()) as f:
            return bool(json.load(f).get('enabled'))
    except Exception:
        return bool(current_app.config.get('OPERARIO_GATE_ENABLED'))


def fijar_gate_operario(activo):
    """Activa/desactiva el gate en caliente (llamado desde Admin -> Sistema)."""
    import json
    with open(_gate_operario_file(), 'w') as f:
        json.dump({'enabled': bool(activo)}, f)


def requiere_operario(f):
    """Decorador: exige que este PC tenga puesto asignado y que su navegador
    tenga adoptada la sesión de un operario (ver /puesto/seleccionar,
    /login y app/routes/operarios.py:api_sesion_operario_adoptar).

    - Si el gate no está activo (ver gate_operario_activo), deja pasar.
    - Sin puesto asignado a este PC -> /puesto/seleccionar.
    - Con puesto pero sin operario en sesión (o con un login ya caducado en
      el servidor) -> /login.
    - Con ambos -> deja pasar.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not gate_operario_activo():
            return f(*args, **kwargs)

        from app.routes.puestos import _puesto_pc_actual
        puesto_id, _ = _puesto_pc_actual()
        if not puesto_id:
            return redirect(url_for('main.puesto_seleccionar'))

        from app.routes.base import db
        from sqlalchemy import text as _text
        nombre = session.get('operario_actual')
        login_id = session.get('operario_login_id')
        operario_valido = False
        if nombre and login_id:
            with db.engine.connect() as conn:
                vivo = conn.execute(_text(
                    "SELECT 1 FROM operario_logins WHERE id=:id AND activo=1"
                ), {'id': login_id}).fetchone()
                operario_valido = bool(vivo)
        if not operario_valido:
            session.pop('operario_actual', None)
            session.pop('operario_login_id', None)
            return redirect(url_for('main.login_operario'))

        return f(*args, **kwargs)
    return wrapper
