"""
Reports y trazabilidad de progreso.
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
from app.routes.progreso import _crimps_por_terminal_archivo


# ==================== REPORTS / TRAZABILIDAD ====================

def _terminales_validos_bono(nombre_bono):
    """Set de terminales que REALMENTE se engastan en un bono (crimps > 0).

    Devuelve None si no se puede determinar (bono desconocido o sin archivos),
    en cuyo caso el llamante no debe filtrar. Si devuelve un set no vacío,
    los terminales que no estén en él solo aparecen con '*' y no se ponen.
    """
    try:
        bono_repo = BonoRepository(db)
        orden_repo = OrdenRepository(db)
        bono = bono_repo.obtener_bono_por_nombre(nombre_bono)
        if not bono:
            return None
        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])
        validos = set()
        cache = {}
        for orden in ordenes:
            archivo = orden.get('archivo_excel')
            if not archivo:
                continue
            if archivo not in cache:
                cache[archivo] = _crimps_por_terminal_archivo(archivo)
            for terminal, n in cache[archivo].items():
                if terminal and n and n > 0:
                    validos.add(str(terminal).upper())
        return validos or None
    except Exception:
        return None


@bp.route('/api/report/progreso', methods=['GET'])
def api_report_progreso():
    """
    Agrega todos los JSON de progreso y devuelve trazabilidad completa.
    Parámetros opcionales:
      ?bono=<nombre>        → filtrar por bono
      ?terminal=<codigo>    → filtrar por terminal
      ?operario=<nombre>    → filtrar por operario
    """
    try:
        filtro_bono = request.args.get('bono', '').strip() or None
        filtro_terminal = request.args.get('terminal', '').strip().upper() or None
        filtro_operario = request.args.get('operario', '').strip() or None

        data_dir = current_app.config['DATA_DIR']
        registros = []

        # Cache de terminales que REALMENTE se engastan por bono (crimps > 0),
        # para no mostrar terminales que solo aparecen con '*' (no se ponen).
        _validos_cache = {}

        for fname in sorted(os.listdir(data_dir)):
            if not (fname.startswith('progreso_bono_') and fname.endswith('.json')):
                continue
            nombre_bono = fname[len('progreso_bono_'):-len('.json')]
            if filtro_bono and nombre_bono != filtro_bono:
                continue
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    progreso = json.load(f)
            except Exception:
                continue

            if nombre_bono not in _validos_cache:
                _validos_cache[nombre_bono] = _terminales_validos_bono(nombre_bono)
            validos = _validos_cache[nombre_bono]

            for terminal, datos in progreso.items():
                if filtro_terminal and terminal.upper() != filtro_terminal:
                    continue
                # Ocultar terminales que no se engastan (solo aparecen con '*')
                if validos and terminal.upper() not in validos:
                    continue
                operario = datos.get('operario', '')
                if filtro_operario and operario.lower() != filtro_operario.lower():
                    continue
                registros.append({
                    'bono': nombre_bono,
                    'terminal': terminal,
                    'operario': operario,
                    'estado': datos.get('estado', ''),
                    'carros_completados': datos.get('carros_completados', []),
                    'fecha_inicio': datos.get('fecha_inicio', ''),
                    'fecha_ultima_actualizacion': datos.get('fecha_ultima_actualizacion', ''),
                })

        # Estadísticas
        bonos_unicos = len(set(r['bono'] for r in registros))
        terminales_unicos = len(set(r['terminal'] for r in registros))
        operarios_unicos = len(set(r['operario'] for r in registros if r['operario']))

        return jsonify({
            'success': True,
            'registros': registros,
            'total': len(registros),
            'bonos': bonos_unicos,
            'terminales': terminales_unicos,
            'operarios': operarios_unicos,
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return error_interno(e)
