"""
Gestión de proyectos.
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


# ==================== GESTIÓN DE PROYECTOS ====================

@bp.route('/proyectos')
def gestion_proyectos():
    """Vista de gestión de proyectos"""
    return render_template('gestion-proyectos.html')


@bp.route('/api/proyectos', methods=['GET'])
def api_obtener_proyectos():
    """Obtener listado de proyectos"""
    try:
        proyecto_repo = ProyectoRepository(db)
        estado = request.args.get('estado')  # activo, completado, pausado, cancelado
        
        proyectos = proyecto_repo.obtener_todos_proyectos(estado)
        
        return jsonify({
            'success': True,
            'proyectos': proyectos
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/proyectos', methods=['POST'])
def api_crear_proyecto():
    """Crear nuevo proyecto"""
    try:
        data = request.get_json()
        
        proyecto_repo = ProyectoRepository(db)
        proyecto_id = proyecto_repo.crear_proyecto(
            nombre=data['nombre'],
            archivo=data['archivo'],
            carro_asignado=data.get('carro_asignado')
        )
        
        proyecto = proyecto_repo.obtener_proyecto(proyecto_id)
        
        return jsonify({
            'success': True,
            'proyecto': proyecto
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/proyectos/<int:proyecto_id>/carro', methods=['PUT'])
def api_asignar_carro(proyecto_id):
    """Asignar proyecto a un carro"""
    try:
        data = request.get_json()
        carro_numero = data.get('carro_numero')

        proyecto_repo = ProyectoRepository(db)

        if carro_numero:
            success = proyecto_repo.asignar_carro(proyecto_id, carro_numero)
        else:
            success = proyecto_repo.liberar_carro(proyecto_id)

        if success:
            proyecto = proyecto_repo.obtener_proyecto(proyecto_id)
            return jsonify({
                'success': True,
                'proyecto': proyecto
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo asignar el carro'
            }), 400

    except IntegrityError:
        return jsonify({
            'success': False,
            'error': f'El carro {carro_numero} ya está asignado a otro proyecto',
            'code': 'CARRO_DUPLICADO',
        }), 409
    except Exception as e:
        return error_interno(e)


@bp.route('/api/proyectos/<int:proyecto_id>/estado', methods=['PUT'])
def api_cambiar_estado_proyecto(proyecto_id):
    """Cambiar estado de un proyecto"""
    try:
        data = request.get_json()
        estado = data.get('estado')
        
        proyecto_repo = ProyectoRepository(db)
        success = proyecto_repo.cambiar_estado(proyecto_id, estado)
        
        if success:
            proyecto = proyecto_repo.obtener_proyecto(proyecto_id)
            return jsonify({
                'success': True,
                'proyecto': proyecto
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo cambiar el estado'
            }), 400
            
    except Exception as e:
        return error_interno(e)
