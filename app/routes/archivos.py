"""
Archivos Excel de cortes y códigos de barras asociados.
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
from app.routes.etiquetas import _regenerar_etiquetas_archivo


# ==================== CÓDIGOS DE CORTES ====================

@bp.route('/api/codigos', methods=['GET'])
def api_obtener_codigos():
    """Obtener códigos de cortes"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        return jsonify({
            'success': True,
            'codigos': codigos
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/codigos/<codigo>', methods=['GET'])
def api_obtener_codigo(codigo):
    """Obtener información de un código específico"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigo_info = codigo_repo.obtener_codigo(codigo)
        
        if codigo_info:
            return jsonify({
                'success': True,
                'codigo': codigo_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Código no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e)


# ==================== GESTIÓN DE ARCHIVOS EXCEL ====================

@bp.route('/api/upload', methods=['POST'])
@requiere_pin_admin
def upload_file():
    """Subir archivo Excel"""
    try:
        # Verificar que se envió un archivo
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': 'No se encontró archivo'
            }), 400
        
        file = request.files['file']
        
        # Verificar que se seleccionó un archivo
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'No se seleccionó archivo'
            }), 400
        
        # Verificar extensión permitida
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            # Crear carpeta de uploads si no existe
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            
            # Guardar archivo
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)

            # Leer nombres de hojas y buscar patrón CODIGO_EDICION (ej: H0457486_ED04)
            hoja_codigo = None
            codigo_extraido = None
            edicion_extraida = None
            try:
                xl = pd.ExcelFile(filepath)
                import re as _re
                for sheet in xl.sheet_names:
                    m = _re.match(r'^([A-Za-z0-9]+)_([A-Za-z0-9]+)$', sheet.strip())
                    if m:
                        hoja_codigo = sheet.strip()
                        codigo_extraido = m.group(1).upper()
                        edicion_extraida = m.group(2).upper()
                        break
            except Exception:
                pass

            # Regenerar etiquetas si este archivo ya tenía registros en la BD
            etiquetas_regeneradas = False
            etiquetas_total = 0
            try:
                with db.engine.connect() as conn:
                    count = conn.execute(
                        text("SELECT COUNT(*) FROM etiquetas_elementos WHERE archivo_excel = :a"),
                        {'a': filename}
                    ).scalar()
                if count and count > 0:
                    total = _regenerar_etiquetas_archivo(filename, filepath)
                    etiquetas_regeneradas = True
                    etiquetas_total = total
            except Exception as _e:
                print(f"⚠️ No se pudieron regenerar etiquetas tras subida: {_e}")

            return jsonify({
                'success': True,
                'message': 'Archivo subido correctamente',
                'filename': filename,
                'hoja_codigo': hoja_codigo,
                'codigo': codigo_extraido,
                'edicion': edicion_extraida,
                'etiquetas_regeneradas': etiquetas_regeneradas,
                'etiquetas_total': etiquetas_total
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Tipo de archivo no permitido. Solo .xlsx y .xls'
            }), 400
            
    except Exception as e:
        return error_interno(e, 'Error al subir archivo')


@bp.route('/api/list_files', methods=['GET'])
def list_files():
    """Listar archivos Excel en la carpeta de uploads"""
    try:
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        if not os.path.exists(upload_folder):
            return jsonify({'success': True, 'files': []})
        
        files = []
        for filename in os.listdir(upload_folder):
            if allowed_file(filename):
                filepath = os.path.join(upload_folder, filename)
                file_size = os.path.getsize(filepath)
                
                # Formatear tamaño
                if file_size < 1024:
                    size_str = f"{file_size} B"
                elif file_size < 1024 * 1024:
                    size_str = f"{file_size / 1024:.1f} KB"
                else:
                    size_str = f"{file_size / (1024 * 1024):.1f} MB"
                
                files.append({
                    'nombre': filename,
                    'tamano': size_str
                })
        
        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        return error_interno(e, 'Error al listar archivos')


@bp.route('/api/add_corte', methods=['POST'])
@requiere_pin_admin
def add_corte():
    """Agregar nuevo corte de cable (asociar código de barras con archivo)"""
    try:
        data = request.get_json()
        
        codigo_barras = data.get('codigo_barras', '').strip().upper()
        archivo = data.get('archivo', '').strip()
        descripcion = data.get('descripcion', '').strip()
        proyecto = data.get('proyecto', '').strip()
        forzar = data.get('forzar', False)

        if not codigo_barras or not archivo:
            return jsonify({
                'success': False,
                'message': 'Código de barras y archivo son obligatorios'
            }), 400

        # Verificar que el archivo existe (y que el nombre no se sale de la carpeta)
        filepath = _ruta_upload_segura(archivo)
        if not filepath or not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'message': f'El archivo "{archivo}" no existe'
            }), 400

        # Agregar código a la base de datos
        codigo_repo = CodigoCorteRepository(db)

        # Verificar si ya existe; si no se fuerza, avisar al frontend
        existe = codigo_repo.obtener_codigo(codigo_barras)
        if existe and not forzar:
            return jsonify({
                'success': False,
                'ya_existe': True,
                'message': f'El código {codigo_barras} ya está asociado al archivo "{existe["archivo_excel"]}". ¿Deseas sobreescribirlo?'
            }), 409

        # Agregar/sobreescribir código
        success = codigo_repo.agregar_codigo(
            codigo=codigo_barras,
            archivo_excel=archivo,
            proyecto_nombre=proyecto or descripcion or None
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Corte agregado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al agregar el corte'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al agregar corte')


@bp.route('/api/list_cortes', methods=['GET'])
@requiere_pin_admin
def list_cortes():
    """Listar todos los cortes registrados"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        # Formatear para compatibilidad con el formato antiguo
        cortes = []
        for codigo in codigos:
            cortes.append({
                'codigo': codigo['codigo'],
                'codigo_barras': codigo['codigo'],
                'archivo': codigo['archivo_excel'],
                'descripcion': codigo.get('proyecto_nombre', ''),
                'proyecto': codigo.get('proyecto_nombre', '')
            })
        
        return jsonify({
            'success': True,
            'cortes': cortes
        })
    except Exception as e:
        return error_interno(e, 'Error al listar cortes')


# Alias para compatibilidad con el frontend
@bp.route('/api/codigos_cortes/listar', methods=['GET'])
def api_listar_codigos_alias():
    """Alias para listar códigos de corte (compatibilidad)"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        # Formatear códigos para el select
        codigos_formateados = []
        for codigo in codigos:
            codigos_formateados.append({
                'codigo': codigo['codigo'],
                'descripcion': codigo.get('proyecto_nombre', ''),
                'proyecto': codigo.get('proyecto_nombre', ''),
                'archivo': codigo['archivo_excel']
            })
        
        return jsonify({
            'success': True,
            'codigos': codigos_formateados
        })
    except Exception as e:
        return error_interno(e, 'Error al listar códigos')


@bp.route('/api/delete_corte', methods=['POST'])
@requiere_pin_admin
def delete_corte():
    """Eliminar corte de cable"""
    try:
        data = request.get_json()
        codigo_barras = data.get('codigo_barras', '').strip().upper()
        
        if not codigo_barras:
            return jsonify({
                'success': False,
                'message': 'Código de barras vacío'
            }), 400
        
        codigo_repo = CodigoCorteRepository(db)
        
        if codigo_repo.desactivar_codigo(codigo_barras):
            return jsonify({
                'success': True,
                'message': 'Corte eliminado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Código de barras no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al eliminar corte')


@bp.route('/api/delete_file', methods=['POST'])
@requiere_pin_admin
def delete_file():
    """Eliminar archivo Excel"""
    try:
        data = request.get_json()
        filename = data.get('filename', '').strip()
        
        if not filename:
            return jsonify({
                'success': False,
                'message': 'Nombre de archivo vacío'
            }), 400

        # Eliminar archivo físico
        filepath = _ruta_upload_segura(filename)
        if not filepath:
            return jsonify({
                'success': False,
                'message': 'Nombre de archivo no válido'
            }), 400

        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'message': 'Archivo no encontrado'
            }), 404
        
        os.remove(filepath)
        
        # Desactivar todos los códigos asociados a este archivo
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.buscar_por_archivo(filename)
        for codigo in codigos:
            codigo_repo.desactivar_codigo(codigo['codigo'])
        
        return jsonify({
            'success': True,
            'message': 'Archivo eliminado correctamente'
        })
        
    except Exception as e:
        return error_interno(e, 'Error al eliminar archivo')
