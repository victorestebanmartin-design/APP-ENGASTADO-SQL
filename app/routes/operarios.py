"""
Operarios (identificación controlada).
"""
from flask import render_template, request, jsonify, current_app, redirect, url_for, send_file, session
import io
import zipfile as _zipfile
from werkzeug.utils import secure_filename
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import os
import json
import re
import subprocess
import sys
import time
import hmac
import hashlib
import traceback
from datetime import datetime, timedelta
import pandas as pd

from repositories.proyecto_repository import ProyectoRepository
from repositories.orden_repository import OrdenRepository
from repositories.codigo_corte_repository import CodigoCorteRepository
from repositories.bono_repository import BonoRepository, CarroRepository
from repositories.puesto_repository import PuestoRepository
from repositories.maquina_repository import MaquinaRepository
from repositories.sesion_trabajo_repository import SesionTrabajoRepository
from app.excel_manager import ExcelManager
from app.auth import (
    requiere_pin_admin,
    proteccion_activa,
    sesion_admin_valida,
    marcar_sesion_admin,
    cerrar_sesion_admin,
)
from app.routes.base import (
    bp, db, error_interno, allowed_file, _ruta_upload_segura,
    _ahora_iso, _detectar_hoja, _es_error_nombre_bono_duplicado,
)


# ==================== OPERARIOS ====================

def _operario_por_tag(conn, tag_uid):
    """Operario activo asociado a esa tarjeta NFC, o None."""
    return conn.execute(text(
        "SELECT id, nombre FROM operarios WHERE tag_uid = :t AND activo = 1"
    ), {'t': tag_uid}).fetchone()


@bp.route('/api/operarios', methods=['GET'])
def api_operarios_get():
    """Listar operarios activos"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, nombre, activo, created_at, tag_uid FROM operarios ORDER BY nombre"
            )).fetchall()
        return jsonify({'success': True, 'operarios': [
            {'id': r[0], 'nombre': r[1], 'activo': r[2], 'created_at': r[3], 'tag_uid': r[4]}
            for r in rows
        ]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios', methods=['POST'])
def api_operarios_create():
    """Crear nuevo operario"""
    try:
        import uuid
        data = request.get_json() or {}
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400
        op_id = str(uuid.uuid4())[:8]
        with db.engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO operarios (id, nombre) VALUES (:id, :nombre)"
            ), {'id': op_id, 'nombre': nombre})
            conn.commit()
        return jsonify({'success': True, 'operario': {'id': op_id, 'nombre': nombre, 'activo': 1}})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>', methods=['PUT'])
def api_operarios_update(op_id):
    """Actualizar operario: nombre y/o su tarjeta NFC."""
    try:
        from app.routes.puestos import normalizar_tag_uid
        data = request.get_json() or {}

        # Tarjeta NFC del operario: UID en hex, o null/'' para quitarla.
        tag_uid, tocar_tag, limpiar_tag = None, False, False
        if 'tag_uid' in data:
            tocar_tag = True
            crudo = data.get('tag_uid')
            if crudo in (None, ''):
                limpiar_tag = True
            else:
                tag_uid = normalizar_tag_uid(crudo)
                if tag_uid is None:
                    return jsonify({'success': False,
                                    'error': 'El UID de la tarjeta no es válido '
                                             '(se espera hexadecimal, de 4 a 10 bytes)'}), 400

        # Si solo se toca la tarjeta, el nombre no es obligatorio.
        nombre = None
        if 'nombre' in data or not tocar_tag:
            nombre = (data.get('nombre') or '').strip()
            if not nombre:
                return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400

        with db.engine.connect() as conn:
            if tocar_tag and not limpiar_tag:
                ocupado = _operario_por_tag(conn, tag_uid)
                if ocupado and ocupado[0] != op_id:
                    return jsonify({'success': False,
                                    'error': f'Esa tarjeta ya está asignada a '
                                             f'"{ocupado[1]}"'}), 409
            if nombre is not None:
                conn.execute(text("UPDATE operarios SET nombre=:nombre WHERE id=:id"),
                             {'nombre': nombre, 'id': op_id})
            if tocar_tag:
                conn.execute(text("UPDATE operarios SET tag_uid=:t WHERE id=:id"),
                             {'t': None if limpiar_tag else tag_uid, 'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except IntegrityError:
        return jsonify({'success': False,
                        'error': 'Esa tarjeta ya está asignada a otro operario'}), 409
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>', methods=['DELETE'])
def api_operarios_delete(op_id):
    """Desactivar operario"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET activo=0 WHERE id=:id"
            ), {'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>/activar', methods=['POST'])
def api_operarios_activar(op_id):
    """Reactivar operario desactivado"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET activo=1 WHERE id=:id"
            ), {'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


# ==================== LOGIN EXCLUSIVO DE OPERARIOS ====================
#
# Al entrar al módulo de engastado el operario se identifica en el modal
# inicial. Ese login queda registrado en operario_logins y es exclusivo:
# mientras esté activo, ningún otro puesto puede entrar con el mismo
# operario. El navegador manda un latido periódico; si deja de llegar
# (cierre brusco del navegador, corte de luz), el login caduca solo.

LOGIN_CADUCIDAD_MINUTOS = 3  # sin latido durante este tiempo => login fantasma


def _expirar_logins_fantasma(conn):
    """Desactiva logins cuyo último latido es demasiado antiguo."""
    limite = (datetime.now() - timedelta(minutes=LOGIN_CADUCIDAD_MINUTOS)).isoformat()
    conn.execute(text(
        "UPDATE operario_logins SET activo=0 WHERE activo=1 AND ultimo_latido < :limite"
    ), {'limite': limite})


@bp.route('/api/operarios/login', methods=['POST'])
def api_operario_login():
    """Logear un operario en el módulo de engastado (login exclusivo).

    Devuelve 409 si el operario ya está dentro desde otro puesto.
    """
    try:
        import uuid
        data = request.get_json(silent=True) or {}
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400

        with db.engine.connect() as conn:
            _expirar_logins_fantasma(conn)

            existente = conn.execute(text(
                "SELECT timestamp_login FROM operario_logins "
                "WHERE activo=1 AND operario_nombre=:n"
            ), {'n': nombre}).fetchone()
            if existente:
                conn.commit()  # persistir la expiración de fantasmas
                hora = (existente[0] or '')[11:16]
                msg = f'{nombre} ya está dentro del módulo en otro puesto'
                if hora:
                    msg += f' (desde las {hora})'
                return jsonify({'success': False, 'error': msg}), 409

            login_id = str(uuid.uuid4())
            ahora = datetime.now().isoformat()
            try:
                conn.execute(text(
                    "INSERT INTO operario_logins "
                    "(id, operario_nombre, timestamp_login, ultimo_latido, activo) "
                    "VALUES (:id, :n, :t, :t, 1)"
                ), {'id': login_id, 'n': nombre, 't': ahora})
                conn.commit()
            except IntegrityError:
                # Carrera: otro puesto se logeó con este nombre en el mismo instante
                return jsonify({
                    'success': False,
                    'error': f'{nombre} ya está dentro del módulo en otro puesto'
                }), 409

        return jsonify({'success': True, 'login_id': login_id})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/logout', methods=['POST'])
def api_operario_logout():
    """Cerrar el login del operario.

    Llamado también vía sendBeacon al cerrar/refrescar la pestaña, por lo
    que se acepta el JSON aunque llegue sin Content-Type application/json.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        login_id = (data.get('login_id') or '').strip()
        if not login_id:
            return jsonify({'success': False, 'error': 'login_id es obligatorio'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operario_logins SET activo=0 WHERE id=:id"
            ), {'id': login_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/login/latido', methods=['POST'])
def api_operario_latido():
    """Mantener vivo el login del operario (latido periódico del navegador).

    Si el login ya no está activo (caducó o un admin lo liberó) responde
    expirado=True; el frontend intentará re-logearse con el mismo nombre.
    """
    try:
        data = request.get_json(silent=True) or {}
        login_id = (data.get('login_id') or '').strip()
        if not login_id:
            return jsonify({'success': False, 'error': 'login_id es obligatorio'}), 400
        with db.engine.connect() as conn:
            res = conn.execute(text(
                "UPDATE operario_logins SET ultimo_latido=:t WHERE id=:id AND activo=1"
            ), {'t': datetime.now().isoformat(), 'id': login_id})
            conn.commit()
        if res.rowcount == 0:
            return jsonify({'success': False, 'expirado': True})
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/logins', methods=['GET'])
def api_operario_logins_get():
    """Listar logins activos (quién está dentro del módulo ahora mismo)."""
    try:
        with db.engine.connect() as conn:
            _expirar_logins_fantasma(conn)
            conn.commit()
            rows = conn.execute(text(
                "SELECT id, operario_nombre, timestamp_login, ultimo_latido "
                "FROM operario_logins WHERE activo=1 ORDER BY timestamp_login"
            )).fetchall()
        return jsonify({'success': True, 'logins': [
            {'id': r[0], 'operario': r[1], 'desde': r[2], 'ultimo_latido': r[3]}
            for r in rows
        ]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/logins/<login_id>/liberar', methods=['POST'])
@requiere_pin_admin
def api_operario_login_liberar(login_id):
    """Liberar a la fuerza un login (admin): expulsa al operario del módulo."""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operario_logins SET activo=0 WHERE id=:id"
            ), {'id': login_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


# ==================== LOGIN POR TARJETA (LECTOR COMPARTIDO) ====================
#
# El lector NFC vive en la pantalla del carro y lo comparten varios PCs. Al
# abrir el módulo, el PC pide un login contra un carro concreto: el servidor
# genera un código corto que la pantalla del carro muestra. El operario pasa su
# tarjeta en ese carro y la lectura (que llega por /api/esp32/evento) resuelve
# la petición. Regla: solo puede haber UNA petición pendiente por carro a la vez
# (así no hay ambigüedad sobre a qué PC va la tarjeta leída).

LOGIN_REQUEST_CADUCIDAD_MINUTOS = 2  # sin sondeo del PC => petición abandonada


def _generar_codigo_login():
    import random
    return '%04d' % random.randint(0, 9999)


def _expirar_login_requests(conn):
    """Marca como expiradas las peticiones pendientes que el PC dejó de sondear."""
    limite = (datetime.now() - timedelta(minutes=LOGIN_REQUEST_CADUCIDAD_MINUTOS)).isoformat()
    conn.execute(text(
        "UPDATE login_requests SET estado='expirado' "
        "WHERE estado='pendiente' AND ultimo_latido < :lim"
    ), {'lim': limite})


def _crear_login_operario(conn, nombre):
    """Crea un login exclusivo para el operario. Devuelve (login_id, error).

    error no None => no se pudo (el operario ya está dentro en otro puesto).
    Reutiliza las mismas reglas de exclusividad que el login manual.
    """
    import uuid
    _expirar_logins_fantasma(conn)
    existente = conn.execute(text(
        "SELECT timestamp_login FROM operario_logins WHERE activo=1 AND operario_nombre=:n"
    ), {'n': nombre}).fetchone()
    if existente:
        hora = (existente[0] or '')[11:16]
        msg = f'{nombre} ya está dentro del módulo en otro puesto'
        if hora:
            msg += f' (desde las {hora})'
        return None, msg
    login_id = str(uuid.uuid4())
    ahora = datetime.now().isoformat()
    try:
        conn.execute(text(
            "INSERT INTO operario_logins "
            "(id, operario_nombre, timestamp_login, ultimo_latido, activo) "
            "VALUES (:id, :n, :t, :t, 1)"
        ), {'id': login_id, 'n': nombre, 't': ahora})
    except IntegrityError:
        return None, f'{nombre} ya está dentro del módulo en otro puesto'
    return login_id, None


def resolver_login_por_tag(conn, carro, tag_uid):
    """Intenta resolver una petición de login pendiente en ese carro con la
    tarjeta leída. Lo llama el handler de eventos del ESP32.

    Devuelve un dict con el resultado, o None si no había petición pendiente en
    ese carro o si la tarjeta no es de ningún operario (se deja la petición
    intacta para que lo vuelva a intentar).
    """
    _expirar_login_requests(conn)
    req = conn.execute(text(
        "SELECT id FROM login_requests WHERE carro=:c AND estado='pendiente'"
    ), {'c': carro}).fetchone()
    if not req:
        return None
    op = _operario_por_tag(conn, tag_uid)
    if not op:
        return None  # tarjeta desconocida: no consumir la petición
    nombre = op[1]
    login_id, error = _crear_login_operario(conn, nombre)
    if error:
        conn.execute(text(
            "UPDATE login_requests SET estado='rechazado', operario_nombre=:n, error=:e "
            "WHERE id=:id"
        ), {'n': nombre, 'e': error, 'id': req[0]})
        return {'estado': 'rechazado', 'operario': nombre, 'error': error}
    conn.execute(text(
        "UPDATE login_requests SET estado='resuelto', operario_nombre=:n, login_id=:lg "
        "WHERE id=:id"
    ), {'n': nombre, 'lg': login_id, 'id': req[0]})
    return {'estado': 'resuelto', 'operario': nombre, 'login_id': login_id}


@bp.route('/api/operarios/login/solicitar', methods=['POST'])
def api_login_solicitar():
    """El PC pide un login por tarjeta contra un carro. Genera el código.

    Devuelve 409 si ese carro ya tiene una petición pendiente (regla: una a la
    vez por carro).
    """
    try:
        import uuid
        data = request.get_json(silent=True) or {}
        carro = (data.get('carro') or '').strip()[:24]
        if not carro:
            return jsonify({'success': False, 'error': 'carro es obligatorio'}), 400
        with db.engine.connect() as conn:
            _expirar_login_requests(conn)
            ocupado = conn.execute(text(
                "SELECT codigo FROM login_requests WHERE carro=:c AND estado='pendiente'"
            ), {'c': carro}).fetchone()
            if ocupado:
                conn.commit()
                return jsonify({
                    'success': False, 'ocupado': True,
                    'error': f'El lector del carro {carro} está ocupado por otro '
                             f'login. Espera un momento.'
                }), 409
            req_id = str(uuid.uuid4())
            codigo = _generar_codigo_login()
            ahora = datetime.now().isoformat()
            try:
                conn.execute(text(
                    "INSERT INTO login_requests "
                    "(id, carro, codigo, estado, created_at, ultimo_latido) "
                    "VALUES (:id, :c, :cod, 'pendiente', :t, :t)"
                ), {'id': req_id, 'c': carro, 'cod': codigo, 't': ahora})
                conn.commit()
            except IntegrityError:
                return jsonify({
                    'success': False, 'ocupado': True,
                    'error': f'El lector del carro {carro} está ocupado. Espera.'
                }), 409
        return jsonify({'success': True, 'request_id': req_id, 'codigo': codigo, 'carro': carro})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/login/solicitar/estado', methods=['POST'])
def api_login_solicitar_estado():
    """El PC sondea el estado de su petición de login (y la mantiene viva).

    Respuestas: estado 'pendiente' (sigue esperando la tarjeta), 'resuelto'
    (con operario y login_id), 'rechazado' (con error, p.ej. ya está dentro en
    otro puesto), o 'expirado'/'cancelado'.
    """
    try:
        data = request.get_json(silent=True) or {}
        req_id = (data.get('request_id') or '').strip()
        if not req_id:
            return jsonify({'success': False, 'error': 'request_id es obligatorio'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE login_requests SET ultimo_latido=:t "
                "WHERE id=:id AND estado='pendiente'"
            ), {'t': datetime.now().isoformat(), 'id': req_id})
            row = conn.execute(text(
                "SELECT estado, codigo, operario_nombre, login_id, error "
                "FROM login_requests WHERE id=:id"
            ), {'id': req_id}).fetchone()
            conn.commit()
        if not row:
            return jsonify({'success': True, 'estado': 'expirado'})
        return jsonify({
            'success': True, 'estado': row[0], 'codigo': row[1],
            'operario': row[2], 'login_id': row[3], 'error': row[4],
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/login/solicitar/cancelar', methods=['POST'])
def api_login_solicitar_cancelar():
    """Cancela la petición de login (PC cierra el modal o la pestaña).

    Acepta el JSON aunque llegue por sendBeacon sin Content-Type.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        req_id = (data.get('request_id') or '').strip()
        if not req_id:
            return jsonify({'success': False, 'error': 'request_id es obligatorio'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE login_requests SET estado='cancelado' "
                "WHERE id=:id AND estado='pendiente'"
            ), {'id': req_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)
