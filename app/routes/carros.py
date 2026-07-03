"""
Carros: consulta, asignación y liberación.
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


# ==================== CARROS ====================

@bp.route('/api/carros', methods=['GET'])
def api_obtener_carros():
    """Obtener listado de carros con información de proyectos"""
    try:
        carro_repo = CarroRepository(db)
        proyecto_repo = ProyectoRepository(db)
        
        carros = carro_repo.obtener_todos_carros()
        
        # Para cada carro, obtener sus proyectos activos
        for carro in carros:
            proyectos = proyecto_repo.obtener_proyectos_por_carro(carro['numero'])
            
            if proyectos and len(proyectos) > 0:
                # Carro ocupado
                carro['ocupado'] = True
                carro['proyecto_id'] = proyectos[0]['id']
                carro['proyecto_nombre'] = proyectos[0]['nombre']
                carro['proyecto_archivo'] = proyectos[0]['archivo']
            else:
                # Carro libre
                carro['ocupado'] = False
                carro['proyecto_id'] = None
                carro['proyecto_nombre'] = None
                carro['proyecto_archivo'] = None
        
        return jsonify({
            'success': True,
            'carros': carros
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/<int:carro_numero>', methods=['GET'])
def api_obtener_carro(carro_numero):
    """Obtener información de un carro específico"""
    try:
        carro_repo = CarroRepository(db)
        carro = carro_repo.obtener_carro(carro_numero)
        
        if carro:
            # Obtener proyectos y bonos asignados
            proyectos = carro_repo.obtener_proyectos_activos_en_carro(carro_numero)
            bonos = carro_repo.obtener_bonos_en_carro(carro_numero)
            
            carro['proyectos'] = proyectos
            carro['bonos'] = bonos
            
            return jsonify({
                'success': True,
                'carro': carro
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Carro no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/asignar-orden', methods=['POST'])
def api_asignar_orden_a_carro():
    """Asignar orden a un carro creando un proyecto"""
    try:
        data = request.get_json()
        numero_carro = data.get('numero_carro')
        proyecto_nombre = data.get('proyecto_nombre')
        archivo = data.get('archivo')
        orden_id = data.get('orden_id')  # ID de la orden
        
        if not numero_carro or not proyecto_nombre or not archivo:
            return jsonify({
                'success': False,
                'message': 'Faltan parámetros requeridos'
            }), 400
        
        # Crear proyecto
        proyecto_repo = ProyectoRepository(db)
        proyecto_id = proyecto_repo.crear_proyecto(
            nombre=proyecto_nombre,
            archivo=archivo,
            carro_asignado=numero_carro
        )
        
        # Si se proporcionó orden_id, actualizar estado de la orden
        if orden_id:
            orden_repo = OrdenRepository(db)
            orden_repo.cambiar_estado(orden_id, 'en_proceso')
        
        return jsonify({
            'success': True,
            'proyecto_id': proyecto_id,
            'message': f'Proyecto asignado al carro {numero_carro}'
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/<int:numero_carro>/liberar', methods=['POST'])
def api_liberar_carro(numero_carro):
    """Liberar un carro eliminando sus proyectos activos y devolviendo órdenes a pendiente"""
    try:
        proyecto_repo = ProyectoRepository(db)
        orden_repo = OrdenRepository(db)
        
        # Obtener proyectos activos en el carro
        carro_repo = CarroRepository(db)
        proyectos = carro_repo.obtener_proyectos_activos_en_carro(numero_carro)
        
        ordenes_liberadas = []
        
        # Liberar cada proyecto y devolver órdenes a pendiente
        for proyecto in proyectos:
            # Intentar extraer el número de orden del nombre del proyecto
            # Formato esperado: "60245848 - H0068722"
            nombre_proyecto = proyecto.get('nombre', '')
            
            if ' - ' in nombre_proyecto:
                numero_orden = nombre_proyecto.split(' - ')[0].strip()
                
                # Cambiar estado de la orden a pendiente
                query = """
                    UPDATE ordenes_produccion 
                    SET estado = 'pendiente'
                    WHERE numero = :numero AND estado = 'en_proceso'
                """
                rows = orden_repo.execute_update(query, {'numero': numero_orden})
                
                if rows > 0:
                    ordenes_liberadas.append(numero_orden)
            
            # Liberar el proyecto del carro
            proyecto_repo.liberar_carro(proyecto['id'])
        
        return jsonify({
            'success': True,
            'message': f'Carro {numero_carro} liberado',
            'ordenes_liberadas': ordenes_liberadas
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/asignar', methods=['POST'])
def api_asignar_proyecto_carro():
    """Asignar proyecto existente a un carro"""
    try:
        data = request.get_json()
        proyecto_id = data.get('proyecto_id')
        carro = data.get('carro')
        
        if not proyecto_id or not carro:
            return jsonify({
                'success': False,
                'message': 'Faltan parámetros'
            }), 400
        
        proyecto_repo = ProyectoRepository(db)
        success = proyecto_repo.asignar_carro(proyecto_id, carro)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Proyecto asignado al carro'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo asignar el proyecto'
            }), 500
            
    except Exception as e:
        return error_interno(e)
