"""
Protección del módulo de administración mediante PIN.

La protección solo se activa si hay un hash de PIN configurado
(Config.ADMIN_PIN_HASH, cargado del .env). Si no lo hay, el decorador
deja pasar todo y la app funciona como siempre.
"""
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
