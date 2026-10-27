"""Tiempo de colocacion de manguitos por orden.

Es el hermano de mangueras_trabajo.py: mismo reloj fichado por operario (tramos
con latido), misma tarjeta y mismo codigo bidi corte-orden-cantidad. La
diferencia es que aqui la orden NO se da de alta: la crea la preparacion de
mangueras, y los manguitos solo se pueden empezar cuando esa preparacion ya se
ha iniciado. Asi el tiempo de cada orden cuelga de la misma fila.
"""
import re
from datetime import datetime, timedelta, timezone

from flask import jsonify, request, session
from sqlalchemy import text

from app.auth import sesion_admin_valida
from app.routes.base import bp, db, operario_puede
from app.routes.mangueras_propuestas import _identidad, _json_peticion
from app.routes.mangueras_trabajo import fin_de_pausa


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _cerrar_abandonados(conn):
    limite = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    conn.execute(text(
        'UPDATE manguitos_tramos SET fin=ultimo_latido WHERE fin IS NULL AND '
        '(ultimo_latido<:limite OR NOT EXISTS '
        '(SELECT 1 FROM operario_logins l WHERE l.id=login_id AND l.activo=1))'
    ), {'limite': limite})


def _resumen(conn, orden_id):
    colocacion = conn.execute(text('SELECT * FROM manguitos_colocaciones WHERE orden_id=:id'),
                              {'id': orden_id}).mappings().first()
    tramos = [dict(fila) for fila in conn.execute(text(
        'SELECT * FROM manguitos_tramos WHERE orden_id=:id ORDER BY inicio, id'
    ), {'id': orden_id}).mappings()]
    ahora = datetime.now(timezone.utc)
    for tramo in tramos:
        final = datetime.fromisoformat(tramo['fin']) if tramo['fin'] else ahora
        tramo['segundos'] = max(0, int((final - datetime.fromisoformat(tramo['inicio'])).total_seconds()))
    return {
        'inicio': colocacion['inicio'] if colocacion else None,
        'fin': colocacion['fin'] if colocacion else None,
        'estado': 'terminada' if colocacion and colocacion['fin'] else
                  'en_preparacion' if any(not tramo['fin'] for tramo in tramos) else 'pausada',
        'segundos': sum(tramo['segundos'] for tramo in tramos),
        'operarios': list(dict.fromkeys(tramo['operario_nombre'] for tramo in tramos)),
        'tramos': tramos,
    }


@bp.route('/api/manguitos/trabajo/escanear', methods=['POST'])
def escanear_manguitos():
    identidad = _identidad()
    if not identidad:
        return jsonify(success=False, error='Entra con tu sesion de operario para registrar el trabajo.'), 401
    if not operario_puede(identidad['nombre'], 'manguitos'):
        return jsonify(success=False, error='No tienes permiso de manguitos.'), 403
    try:
        datos = _json_peticion()
        codigo = datos.get('codigo')
        coincidencia = re.fullmatch(r'([A-Za-z0-9_]+)-(\d+)-([1-9]\d*)', codigo.strip() if isinstance(codigo, str) else '')
        if not coincidencia:
            raise ValueError('Codigo no valido. Se requiere corte-orden-cantidad, por ejemplo H0174891-60238442-1.')
        corte, numero, cantidad_texto = coincidencia.groups()
        cantidad = int(cantidad_texto)
        with db.engine.begin() as conn:
            conn.exec_driver_sql('BEGIN IMMEDIATE')
            codigo_info = conn.execute(text(
                'SELECT * FROM codigos_cortes WHERE codigo=:codigo COLLATE NOCASE AND activo=1'
            ), {'codigo': corte}).mappings().first()
            if not codigo_info or not codigo_info['archivo_excel']:
                raise ValueError('El corte no esta registrado o no tiene Excel asociado.')
            orden = conn.execute(text('SELECT * FROM ordenes_produccion WHERE numero=:numero'),
                                 {'numero': numero}).mappings().first()
            preparada = orden and conn.execute(text('SELECT 1 FROM mangueras_preparaciones WHERE orden_id=:id'),
                                               {'id': orden['id']}).first()
            if not preparada:
                return jsonify(success=False, error='Primero hay que preparar las mangueras de esta orden. '
                                                    'Escanea el codigo en Preparacion de mangueras y vuelve aqui.'), 409
            if orden['codigo_corte'].upper() != codigo_info['codigo'].upper() or orden['cantidad'] != cantidad:
                return jsonify(success=False, error='La orden ya existe con otro corte o cantidad. Revisa el codigo antes de continuar.'), 409
            if orden['estado'] in ('cancelado', 'completado', 'finalizado'):
                return jsonify(success=False, error='La orden esta cancelada o finalizada.'), 409
            ahora = _ahora()
            _cerrar_abandonados(conn)
            colocacion = conn.execute(text('SELECT fin FROM manguitos_colocaciones WHERE orden_id=:id'),
                                      {'id': orden['id']}).first()
            if colocacion and colocacion[0]:
                return jsonify(success=False, error='La colocacion de manguitos de esta orden ya esta terminada.'), 409
            conn.execute(text('INSERT OR IGNORE INTO manguitos_colocaciones (orden_id, inicio) VALUES (:id, :ahora)'),
                         {'id': orden['id'], 'ahora': ahora})
            login_id = session['operario_login_id']
            conn.execute(text('UPDATE manguitos_tramos SET fin=:ahora WHERE login_id=:login AND orden_id!=:orden AND fin IS NULL'),
                         {'ahora': ahora, 'login': login_id, 'orden': orden['id']})
            conn.execute(text(
                'INSERT INTO manguitos_tramos (orden_id, login_id, operario_id, operario_nombre, inicio, ultimo_latido) '
                'SELECT :orden, :login, :operario, :nombre, :ahora, :ahora WHERE NOT EXISTS '
                '(SELECT 1 FROM manguitos_tramos WHERE login_id=:login AND fin IS NULL)'
            ), {'orden': orden['id'], 'login': login_id, 'operario': identidad['id'], 'nombre': identidad['nombre'], 'ahora': ahora})
            resumen = _resumen(conn, orden['id'])
            return jsonify(success=True, orden=dict(orden), corte={'codigo': codigo_info['codigo'],
                           'archivo': codigo_info['archivo_excel'], 'proyecto': codigo_info['proyecto_nombre']}, colocacion=resumen)
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400


@bp.route('/api/manguitos/trabajo/<orden_id>', methods=['GET', 'POST'])
def trabajo_manguitos(orden_id):
    identidad = _identidad()
    if not identidad and not (request.method == 'GET' and sesion_admin_valida()):
        return jsonify(success=False, error='Sesion de operario requerida.'), 401
    if identidad and not any(operario_puede(identidad['nombre'], modulo) for modulo in
                             (('manguitos', 'produccion') if request.method == 'GET' else ('manguitos',))):
        return jsonify(success=False, error='No tienes permiso para consultar o registrar manguitos.'), 403
    try:
        datos = _json_peticion() if request.method == 'POST' else {}
        accion = datos.get('accion')
        if request.method == 'POST' and accion not in ('latido', 'pausar', 'terminar'):
            raise ValueError('Accion no valida.')
        with db.engine.begin() as conn:
            conn.exec_driver_sql('BEGIN IMMEDIATE')
            _cerrar_abandonados(conn)
            if request.method == 'POST':
                ahora = _ahora()
                activo = conn.execute(text(
                    'SELECT id, inicio FROM manguitos_tramos WHERE orden_id=:orden AND login_id=:login AND fin IS NULL'
                ), {'orden': orden_id, 'login': session['operario_login_id']}).first()
                if not activo:
                    return jsonify(success=False, error='Colocacion pausada. Vuelve a escanear la orden para retomarla.'), 409
                fin = None if accion == 'latido' else ahora
                if accion == 'pausar':
                    fin = fin_de_pausa(activo.inicio, ahora, datos.get('inactivo_segundos'))
                conn.execute(text('UPDATE manguitos_tramos SET ultimo_latido=:ahora, fin=:fin WHERE id=:id'),
                             {'id': activo.id, 'ahora': ahora, 'fin': fin})
                if accion == 'terminar':
                    conn.execute(text('UPDATE manguitos_tramos SET fin=:ahora WHERE orden_id=:id AND fin IS NULL'),
                                 {'ahora': ahora, 'id': orden_id})
                    conn.execute(text('UPDATE manguitos_colocaciones SET fin=:ahora WHERE orden_id=:id'),
                                 {'ahora': ahora, 'id': orden_id})
            return jsonify(success=True, colocacion=_resumen(conn, orden_id))
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
