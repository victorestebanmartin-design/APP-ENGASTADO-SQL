"""
Órdenes de producción (páginas y CRUD).
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


# ==================== GESTIÓN DE ÓRDENES ====================

@bp.route('/registro-ordenes')
def registro_ordenes():
    """Vista de registro de órdenes"""
    return render_template('registro-ordenes.html')


@bp.route('/ordenes')
def lista_ordenes():
    """Tabla completa de órdenes con sidebar dark"""
    return render_template('ordenes.html')


@bp.route('/api/ordenes', methods=['GET'])
def api_obtener_ordenes():
    """Obtener listado de órdenes"""
    try:
        orden_repo = OrdenRepository(db)
        estado = request.args.get('estado')
        
        if estado:
            ordenes = orden_repo.obtener_ordenes_por_estado(estado)
        else:
            ordenes = orden_repo.obtener_ordenes_pendientes()
        
        return jsonify({
            'success': True,
            'ordenes': ordenes
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ordenes', methods=['POST'])
def api_crear_orden():
    """Crear nueva orden de producción"""
    try:
        data = request.get_json()
        
        # Buscar el archivo Excel asociado al código de corte
        codigo_repo = CodigoCorteRepository(db)
        codigo_info = codigo_repo.obtener_codigo(data['codigo_corte'])
        
        archivo_excel = None
        proyecto_nombre = None
        
        if codigo_info:
            archivo_excel = codigo_info.get('archivo_excel')
            proyecto_nombre = codigo_info.get('proyecto_nombre')
        
        # Si no se especificó proyecto, usar el del código de corte
        proyecto = data.get('proyecto', '') or proyecto_nombre or ''
        
        orden_repo = OrdenRepository(db)
        orden_id = orden_repo.crear_orden(
            codigo_corte=data['codigo_corte'],
            numero=data['numero'],
            descripcion=data.get('descripcion', ''),
            cantidad=data.get('cantidad', 1),
            fecha_entrega=data.get('fecha_entrega'),
            prioridad=data.get('prioridad', 'normal'),
            archivo_excel=archivo_excel,
            proyecto=proyecto
        )
        
        orden = orden_repo.obtener_orden(orden_id)
        
        return jsonify({
            'success': True,
            'orden': orden,
            'archivo_encontrado': archivo_excel is not None
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ordenes/eliminar/<orden_id>', methods=['DELETE'])
def api_eliminar_orden(orden_id):
    """Eliminar una orden de producción"""
    try:
        orden_repo = OrdenRepository(db)
        
        # Verificar que la orden existe
        orden = orden_repo.obtener_orden(orden_id)
        if not orden:
            return jsonify({
                'success': False,
                'message': 'Orden no encontrada'
            }), 404
        
        # Eliminar la orden
        if orden_repo.eliminar_orden(orden_id):
            return jsonify({
                'success': True,
                'message': 'Orden eliminada correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo eliminar la orden'
            }), 500
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ordenes/actualizar/<orden_id>', methods=['PUT'])
def api_actualizar_orden(orden_id):
    """Actualizar una orden de producción"""
    try:
        data = request.get_json()
        orden_repo = OrdenRepository(db)
        
        # Verificar que la orden existe
        orden_actual = orden_repo.obtener_orden(orden_id)
        if not orden_actual:
            return jsonify({
                'success': False,
                'message': 'Orden no encontrada'
            }), 404
        
        # Actualizar la orden
        if orden_repo.actualizar_orden(
            orden_id=orden_id,
            codigo_corte=data.get('codigo_corte'),
            numero=data.get('numero'),
            descripcion=data.get('descripcion'),
            cantidad=data.get('cantidad'),
            fecha_entrega=data.get('fecha_entrega'),
            prioridad=data.get('prioridad'),
            proyecto=data.get('proyecto')
        ):
            orden_actualizada = orden_repo.obtener_orden(orden_id)
            return jsonify({
                'success': True,
                'orden': orden_actualizada,
                'message': 'Orden actualizada correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo actualizar la orden'
            }), 500
    except Exception as e:
        return error_interno(e)


# Alias para compatibilidad con el frontend
@bp.route('/api/ordenes/crear', methods=['POST'])
def api_crear_orden_alias():
    """Alias para crear orden (compatibilidad)"""
    return api_crear_orden()


@bp.route('/api/ordenes/listar', methods=['GET'])
def api_listar_ordenes_alias():
    """Alias para listar órdenes (compatibilidad)"""
    try:
        orden_repo = OrdenRepository(db)
        ordenes = orden_repo.obtener_todas_ordenes()
        
        return jsonify({
            'success': True,
            'ordenes': ordenes
        })
    except Exception as e:
        return error_interno(e)
