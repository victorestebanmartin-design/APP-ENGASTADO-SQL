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

@bp.route('/api/operarios', methods=['GET'])
def api_operarios_get():
    """Listar operarios activos"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, nombre, activo, created_at FROM operarios ORDER BY nombre"
            )).fetchall()
        return jsonify({'success': True, 'operarios': [
            {'id': r[0], 'nombre': r[1], 'activo': r[2], 'created_at': r[3]}
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
    """Actualizar nombre de operario"""
    try:
        data = request.get_json() or {}
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET nombre=:nombre WHERE id=:id"
            ), {'nombre': nombre, 'id': op_id})
            conn.commit()
        return jsonify({'success': True})
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
