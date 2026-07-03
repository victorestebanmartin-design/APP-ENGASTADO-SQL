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
from datetime import datetime
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
