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
            bono = None
            if carro['bono_id']:
                bono = BonoRepository(db).obtener_bono(carro['bono_id'])
            carro['en_bono'] = bool(bono and carro['estado'] != 'disponible')
            carro['bono_nombre'] = bono['nombre'] if bono else None
            
            if proyectos and len(proyectos) > 0:
                # Carro ocupado
                carro['ocupado'] = True
                carro['proyecto_id'] = proyectos[0]['id']
                carro['proyecto_nombre'] = proyectos[0]['nombre']
                carro['proyecto_archivo'] = proyectos[0]['archivo']
            else:
                # Carro libre
                carro['ocupado'] = carro['en_bono'] or carro['estado'] == 'en_proceso'
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
        data = request.get_json(silent=True) or {}
        numero_carro = data.get('numero_carro')
        proyecto_nombre = data.get('proyecto_nombre')
        archivo = data.get('archivo')
        orden_id = data.get('orden_id')  # ID de la orden
        
        if type(numero_carro) is not int or not 1 <= numero_carro <= 6:
            return jsonify(success=False, message='Selecciona un carro del 1 al 6'), 400
        if not orden_id and (not proyecto_nombre or not archivo):
            return jsonify({
                'success': False,
                'message': 'Faltan parámetros requeridos'
            }), 400
        
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE carros SET numero = numero WHERE numero = :numero'), {'numero': numero_carro})
            existe = conn.execute(text('SELECT * FROM carros WHERE numero = :numero'), {'numero': numero_carro}).mappings().first()
            ocupado = conn.execute(text('SELECT id FROM proyectos WHERE carro_asignado = :numero'), {'numero': numero_carro}).first()
            if not existe:
                return jsonify(success=False, message='Carro no encontrado'), 404
            if ocupado or existe['bono_id'] or existe['estado'] == 'en_proceso':
                return jsonify(success=False, message='El carro ya tiene trabajo asignado'), 409
            if orden_id:
                orden = conn.execute(text('SELECT * FROM ordenes_produccion WHERE id = :id'), {'id': orden_id}).mappings().first()
                if not orden:
                    return jsonify(success=False, message='Orden no encontrada'), 404
                if orden['estado'] != 'pendiente' or orden['bono_id']:
                    return jsonify(success=False, message='La orden ya no esta pendiente. Actualiza la pantalla.'), 409
                if not orden['archivo_excel']:
                    return jsonify(success=False, message='Asocia primero un archivo Excel a la orden'), 400
                proyecto_nombre = f"{orden['numero']} - {orden['codigo_corte']}"
                archivo = orden['archivo_excel']
                conn.execute(text("UPDATE ordenes_produccion SET estado = 'en_proceso', carro_numero = :carro WHERE id = :id"), {'carro': numero_carro, 'id': orden_id})
            resultado = conn.execute(text("INSERT INTO proyectos (nombre, archivo, carro_asignado, orden_id) VALUES (:nombre, :archivo, :carro, :orden)"), {'nombre': proyecto_nombre, 'archivo': archivo, 'carro': numero_carro, 'orden': orden_id})
            proyecto_id = resultado.lastrowid
        
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
        ordenes_liberadas = []
        data = request.get_json(silent=True) or {}
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE carros SET numero = numero WHERE numero = :numero'), {'numero': numero_carro})
            carro = conn.execute(text('SELECT * FROM carros WHERE numero = :numero'), {'numero': numero_carro}).mappings().first()
            if not carro:
                return jsonify(success=False, message='Carro no encontrado'), 404
            proyectos = conn.execute(text('SELECT * FROM proyectos WHERE carro_asignado = :numero'), {'numero': numero_carro}).mappings().all()
            if carro['bono_id'] and data.get('confirmar_bono') is not True:
                return jsonify(success=False, message='El carro pertenece a un bono. Confirma que esta vacio antes de liberarlo.'), 409
            for proyecto in proyectos:
                numero_orden = proyecto['nombre'].split(' - ')[0].strip()
                resultado = conn.execute(text("UPDATE ordenes_produccion SET estado = 'pendiente', carro_numero = NULL WHERE (id = :id OR (:id IS NULL AND numero = :numero)) AND estado = 'en_proceso' AND bono_id IS NULL"), {'id': proyecto['orden_id'], 'numero': numero_orden})
                if resultado.rowcount:
                    ordenes_liberadas.append(numero_orden)
                conn.execute(text('UPDATE proyectos SET carro_asignado = NULL WHERE id = :id'), {'id': proyecto['id']})
            conn.execute(text("UPDATE carros SET bono_id = NULL, estado = 'disponible' WHERE numero = :numero"), {'numero': numero_carro})
        
        return jsonify({
            'success': True,
            'message': f'Carro {numero_carro} liberado',
            'ordenes_liberadas': ordenes_liberadas
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/<int:numero_carro>/mover', methods=['POST'])
def api_mover_carro(numero_carro):
    try:
        data = request.get_json(silent=True) or {}
        destino = data.get('destino')
        if type(destino) is not int or not 1 <= destino <= 6 or destino == numero_carro:
            return jsonify(success=False, message='Selecciona otro carro del 1 al 6'), 400
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE carros SET numero = numero WHERE numero IN (:origen, :destino)'), {'origen': numero_carro, 'destino': destino})
            carros = conn.execute(text('SELECT * FROM carros WHERE numero IN (:origen, :destino)'), {'origen': numero_carro, 'destino': destino}).mappings().all()
            if len(carros) != 2:
                return jsonify(success=False, message='Carro no encontrado'), 404
            if any(carro['bono_id'] or carro['estado'] == 'en_proceso' for carro in carros):
                return jsonify(success=False, message='No se puede mover trabajo de un bono ya generado'), 409
            proyectos = conn.execute(text('SELECT * FROM proyectos WHERE carro_asignado IN (:origen, :destino)'), {'origen': numero_carro, 'destino': destino}).mappings().all()
            origen = next((proyecto for proyecto in proyectos if proyecto['carro_asignado'] == numero_carro), None)
            otro = next((proyecto for proyecto in proyectos if proyecto['carro_asignado'] == destino), None)
            if not origen or origen['id'] != data.get('proyecto_id'):
                return jsonify(success=False, message='El contenido del carro ha cambiado. Actualiza la pantalla.'), 409
            if otro and data.get('intercambiar') is not True:
                return jsonify(success=False, message='El destino esta ocupado. Confirma el intercambio.'), 409
            conn.execute(text('UPDATE proyectos SET carro_asignado = NULL WHERE carro_asignado IN (:origen, :destino)'), {'origen': numero_carro, 'destino': destino})
            for proyecto, numero in ((origen, destino), (otro, numero_carro)):
                if proyecto:
                    conn.execute(text('UPDATE proyectos SET carro_asignado = :numero WHERE id = :id'), {'numero': numero, 'id': proyecto['id']})
                    conn.execute(text("UPDATE ordenes_produccion SET carro_numero = :carro WHERE (id = :id OR (:id IS NULL AND numero = :numero)) AND bono_id IS NULL AND estado = 'en_proceso'"), {'carro': numero, 'id': proyecto['orden_id'], 'numero': proyecto['nombre'].split(' - ')[0].strip()})
        return jsonify(success=True, message='Carros actualizados')
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
        
        if type(carro) is not int or not 1 <= carro <= 6:
            return jsonify(success=False, message='Selecciona un carro del 1 al 6'), 400
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE carros SET numero = numero WHERE numero = :numero'), {'numero': carro})
            destino = conn.execute(text('SELECT * FROM carros WHERE numero = :numero'), {'numero': carro}).mappings().first()
            ocupado = conn.execute(text('SELECT id FROM proyectos WHERE carro_asignado = :numero'), {'numero': carro}).first()
            if not destino or destino['bono_id'] or destino['estado'] == 'en_proceso' or ocupado:
                return jsonify(success=False, message='El carro no esta disponible'), 409
            resultado = conn.execute(text("UPDATE proyectos SET carro_asignado = :carro WHERE id = :id AND carro_asignado IS NULL AND estado = 'activo'"), {'carro': carro, 'id': proyecto_id})
            success = resultado.rowcount > 0
        
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
