"""
Paleta de colores por código de cable.
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


# ==================== PALETA DE COLORES DE CABLES ====================

def _text_color_for_bg(hex_color):
    """Devuelve #000000 o #ffffff según la luminancia relativa (WCAG 2.1)."""
    try:
        h = str(hex_color).lstrip('#')
        if len(h) != 6:
            return '#ffffff'
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        def _lin(c):
            c /= 255.0
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        L = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
        return '#000000' if L > 0.179 else '#ffffff'
    except Exception:
        return '#ffffff'


@bp.route('/api/cable-colores', methods=['GET'])
def api_cable_colores_get():
    """Devuelve todos los colores de cables definidos en BD"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT cod_cable, color_hex, color_texto FROM cable_colores ORDER BY cod_cable"
            )).fetchall()
        return jsonify({'success': True, 'colores': [
            {'cod_cable': r[0], 'color_hex': r[1],
             'color_texto': r[2] if r[2] else None}
            for r in rows
        ]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/cable-colores', methods=['POST'])
def api_cable_colores_upsert():
    """Crea o actualiza el color de un cable (cod_cable, color_hex, color_texto opcional)"""
    try:
        data = request.get_json() or {}
        cod = (data.get('cod_cable') or '').strip().upper()
        hex_col = (data.get('color_hex') or '').strip().lower()
        # color_texto: None/'' = auto (calcular por luminancia), o un hex válido
        color_texto_raw = (data.get('color_texto') or '').strip().lower()
        color_texto = color_texto_raw if re.match(r'^#[0-9a-f]{6}$', color_texto_raw) else None
        if not cod or not hex_col:
            return jsonify({'success': False, 'error': 'cod_cable y color_hex son obligatorios'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO cable_colores (cod_cable, color_hex, color_texto) VALUES (:c, :h, :t) "
                "ON CONFLICT(cod_cable) DO UPDATE SET color_hex=excluded.color_hex, color_texto=excluded.color_texto"
            ), {'c': cod, 'h': hex_col, 't': color_texto})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/cable-colores/<path:cod_cable>', methods=['DELETE'])
def api_cable_colores_delete(cod_cable):
    """Elimina la asignación de color de un cable (vuelve al hash fallback)"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text("DELETE FROM cable_colores WHERE cod_cable = :c"), {'c': cod_cable.upper()})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/cable-colores/sin-asignar', methods=['GET'])
def api_cable_colores_sin_asignar():
    """Cables presentes en etiquetas_elementos que no tienen color definido en BD"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT cod_cable FROM etiquetas_elementos
                WHERE cod_cable IS NOT NULL AND cod_cable != '' AND LOWER(cod_cable) != 'nan'
                  AND UPPER(cod_cable) NOT IN (SELECT cod_cable FROM cable_colores)
                ORDER BY cod_cable
            """)).fetchall()
        return jsonify({'success': True, 'cables': [r[0] for r in rows]})
    except Exception as e:
        return error_interno(e)
