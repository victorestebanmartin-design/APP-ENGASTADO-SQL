"""
Puestos, máquinas y asignación de terminales.
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


# ==================== PUESTOS Y MÁQUINAS ====================

@bp.route('/api/puestos', methods=['GET'])
def api_obtener_puestos():
    """Obtener lista de puestos con sus máquinas"""
    try:
        puesto_repo = PuestoRepository(db)
        maquina_repo = MaquinaRepository(db)
        
        puestos = puesto_repo.obtener_todos_puestos()
        
        # Agregar máquinas a cada puesto
        for puesto in puestos:
            maquinas = maquina_repo.obtener_maquinas_por_puesto(puesto['id'])
            # Agregar terminales a cada máquina
            for maquina in maquinas:
                maquina['terminales_asignados'] = maquina_repo.obtener_terminales_asignados(maquina['id'])
            puesto['maquinas'] = maquinas
        
        return jsonify({
            'success': True,
            'puestos': puestos
        })
    except Exception as e:
        return error_interno(e, 'Error al obtener puestos')


@bp.route('/api/puestos', methods=['POST'])
@requiere_pin_admin
def api_crear_puesto():
    """Crear nuevo puesto"""
    try:
        data = request.get_json()
        
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({
                'success': False,
                'message': 'El nombre del puesto es obligatorio'
            }), 400
        
        # Generar ID único
        puesto_repo = PuestoRepository(db)
        puestos_existentes = puesto_repo.obtener_todos_puestos(solo_activos=False)
        
        import random
        new_id = f"puesto_{len(puestos_existentes) + 1:03d}"
        while any(p['id'] == new_id for p in puestos_existentes):
            new_id = f"puesto_{len(puestos_existentes) + 1:03d}_{random.randint(100, 999)}"
        
        # Crear puesto
        if puesto_repo.crear_puesto(new_id, nombre, descripcion):
            nuevo_puesto = puesto_repo.obtener_puesto(new_id)
            return jsonify({
                'success': True,
                'puesto': nuevo_puesto
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al crear el puesto'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al crear puesto')


@bp.route('/api/puestos/<puesto_id>', methods=['PUT'])
@requiere_pin_admin
def api_actualizar_puesto(puesto_id):
    """Actualizar puesto existente"""
    try:
        data = request.get_json()
        
        puesto_repo = PuestoRepository(db)
        
        # Verificar que existe
        puesto = puesto_repo.obtener_puesto(puesto_id)
        if not puesto:
            return jsonify({
                'success': False,
                'message': 'Puesto no encontrado'
            }), 404
        
        # Actualizar
        nombre = data.get('nombre')
        descripcion = data.get('descripcion')
        
        if puesto_repo.actualizar_puesto(puesto_id, nombre, descripcion):
            puesto_actualizado = puesto_repo.obtener_puesto(puesto_id)
            return jsonify({
                'success': True,
                'puesto': puesto_actualizado
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se realizaron cambios'
            }), 400
            
    except Exception as e:
        return error_interno(e, 'Error al actualizar puesto')


@bp.route('/api/puestos/<puesto_id>', methods=['DELETE'])
@requiere_pin_admin
def api_eliminar_puesto(puesto_id):
    """Eliminar puesto"""
    try:
        puesto_repo = PuestoRepository(db)
        
        if puesto_repo.desactivar_puesto(puesto_id):
            return jsonify({
                'success': True,
                'message': 'Puesto eliminado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Puesto no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al eliminar puesto')


@bp.route('/api/maquinas', methods=['GET'])
def api_obtener_maquinas():
    """Obtener lista de máquinas con información del puesto"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquinas = maquina_repo.obtener_todas_maquinas()
        
        # Agregar terminales asignados a cada máquina
        for maquina in maquinas:
            maquina['terminales_asignados'] = maquina_repo.obtener_terminales_asignados(maquina['id'])
        
        return jsonify({
            'success': True,
            'maquinas': maquinas
        })
    except Exception as e:
        return error_interno(e, 'Error al obtener máquinas')


@bp.route('/api/maquinas', methods=['POST'])
def api_crear_maquina():
    """Crear nueva máquina"""
    try:
        data = request.get_json()
        
        puesto_id = data.get('puesto_id', '').strip()
        nombre = data.get('nombre', '').strip()
        modelo = data.get('modelo', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not puesto_id or not nombre:
            return jsonify({
                'success': False,
                'message': 'Puesto y nombre son obligatorios'
            }), 400
        
        # Verificar que el puesto existe
        puesto_repo = PuestoRepository(db)
        puesto = puesto_repo.obtener_puesto(puesto_id)
        if not puesto:
            return jsonify({
                'success': False,
                'message': 'Puesto no encontrado'
            }), 404
        
        # Generar ID único
        maquina_repo = MaquinaRepository(db)
        maquinas_existentes = maquina_repo.obtener_todas_maquinas(solo_activas=False)
        
        import random
        new_id = f"maq_{len(maquinas_existentes) + 1:03d}"
        while any(m['id'] == new_id for m in maquinas_existentes):
            new_id = f"maq_{len(maquinas_existentes) + 1:03d}_{random.randint(100, 999)}"
        
        # Crear máquina
        if maquina_repo.crear_maquina(new_id, puesto_id, nombre, modelo, descripcion):
            nueva_maquina = maquina_repo.obtener_maquina(new_id)
            nueva_maquina['terminales_asignados'] = []
            return jsonify({
                'success': True,
                'maquina': nueva_maquina
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al crear la máquina'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al crear máquina')


@bp.route('/api/maquinas/<maquina_id>', methods=['PUT'])
def api_actualizar_maquina(maquina_id):
    """Actualizar máquina existente"""
    try:
        data = request.get_json()
        
        maquina_repo = MaquinaRepository(db)
        
        # Verificar que existe
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({
                'success': False,
                'message': 'Máquina no encontrada'
            }), 404
        
        # Actualizar
        nombre = data.get('nombre')
        modelo = data.get('modelo')
        descripcion = data.get('descripcion')
        
        if maquina_repo.actualizar_maquina(maquina_id, nombre, modelo, descripcion):
            maquina_actualizada = maquina_repo.obtener_maquina(maquina_id)
            maquina_actualizada['terminales_asignados'] = maquina_repo.obtener_terminales_asignados(maquina_id)
            return jsonify({
                'success': True,
                'maquina': maquina_actualizada
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se realizaron cambios'
            }), 400
            
    except Exception as e:
        return error_interno(e, 'Error al actualizar máquina')


@bp.route('/api/maquinas/<maquina_id>', methods=['DELETE'])
def api_eliminar_maquina(maquina_id):
    """Eliminar máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        
        if maquina_repo.desactivar_maquina(maquina_id):
            return jsonify({
                'success': True,
                'message': 'Máquina eliminada correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Máquina no encontrada'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al eliminar máquina')


@bp.route('/api/terminales-disponibles', methods=['GET'])
def api_terminales_disponibles():
    """Obtener todos los terminales disponibles con su estado de asignación"""
    try:
        # Obtener códigos de archivos activos
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        # Leer todos los archivos Excel y extraer terminales
        upload_folder = current_app.config['UPLOAD_FOLDER']
        terminales_sistema = set()
        archivos_procesados = 0
        errores_lectura = []
        
        for codigo in codigos:
            archivo = codigo['archivo_excel']
            filepath = os.path.join(upload_folder, archivo)
            
            if os.path.exists(filepath):
                try:
                    df = pd.read_excel(filepath, sheet_name=_detectar_hoja(filepath))
                    
                    # Buscar columnas de terminales (pueden ser 'Terminal', 'De Terminal', 'Para Terminal')
                    columnas_terminales = []
                    for col in df.columns:
                        col_lower = str(col).lower()
                        if 'terminal' in col_lower:
                            columnas_terminales.append(col)
                    
                    # Extraer terminales únicos de todas las columnas encontradas
                    # Excluir terminales con * (son manuales, no se engastan)
                    if columnas_terminales:
                        for col in columnas_terminales:
                            terminales_unicos = df[col].dropna().unique()
                            nuevos_terminales = [
                                str(t).strip() for t in terminales_unicos
                                if str(t).strip() and not str(t).strip().endswith('*')
                            ]
                            terminales_sistema.update(nuevos_terminales)
                        archivos_procesados += 1
                    
                except Exception as e:
                    errores_lectura.append({
                        'archivo': archivo,
                        'error': str(e)
                    })
        
        # Obtener asignaciones actuales
        maquina_repo = MaquinaRepository(db)
        maquinas = maquina_repo.obtener_todas_maquinas()
        
        # Crear diccionario de asignaciones
        terminales_asignados = {}
        for maquina in maquinas:
            terminales_maq = maquina_repo.obtener_terminales_asignados(maquina['id'])
            for terminal in terminales_maq:
                terminales_asignados[terminal] = {
                    'maquina_id': maquina['id'],
                    'maquina_nombre': maquina['nombre'],
                    'puesto_nombre': maquina.get('puesto_nombre', '')
                }

        # Cargar imágenes de terminales
        rows = db.session.execute(
            text("SELECT terminal_codigo, imagen_data FROM terminales_imagenes")
        ).fetchall()
        imagenes_map = {r[0]: r[1] for r in rows}

        # Cargar gavetas de terminales
        rows_gav = db.session.execute(
            text("SELECT terminal_codigo, gaveta FROM terminales_gavetas")
        ).fetchall()
        gavetas_map = {r[0]: r[1] for r in rows_gav}

        # Preparar respuesta con estado de cada terminal
        terminales_con_estado = []
        for terminal in sorted(list(terminales_sistema)):
            estado = {
                'terminal': terminal,
                'asignado': terminal in terminales_asignados,
                'asignacion': terminales_asignados.get(terminal, None),
                'imagen_data': imagenes_map.get(terminal),
                'gaveta': gavetas_map.get(terminal)
            }
            terminales_con_estado.append(estado)
        
        # Contar terminales sin asignar
        sin_asignar = len([t for t in terminales_con_estado if not t['asignado']])
        
        respuesta = {
            'success': True,
            'terminales': terminales_con_estado,
            'total': len(terminales_sistema),
            'sin_asignar': sin_asignar,
            'asignados': len(terminales_asignados),
            'archivos_procesados': archivos_procesados,
            'total_archivos': len(codigos)
        }
        
        # Incluir errores si los hay (para debugging)
        if errores_lectura:
            respuesta['errores_lectura'] = errores_lectura
        
        return jsonify(respuesta)
        
    except Exception as e:
        return error_interno(e, 'Error al obtener terminales')


@bp.route('/api/excel/<path:archivo>/terminales', methods=['GET'])
def api_excel_terminales(archivo):
    """Obtener terminales que REALMENTE se engastan en un archivo Excel.

    Usa la misma lógica que la vista de engastado (_crimps_por_terminal_archivo):
    un terminal solo cuenta si tiene al menos un crimp real (lado sin '*'). Así el
    detalle de la visualización coincide con la lista seleccionable y el peso
    ponderado, sin incluir terminales que solo aparecen con asterisco (no se engastan).
    """
    try:
        archivo = os.path.basename((archivo or '').strip())
        if not archivo:
            return jsonify({
                'success': False,
                'error': 'Archivo no especificado'
            }), 400

        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'data/cortes')
        filepath = os.path.join(upload_folder, archivo)

        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'error': f'Archivo no encontrado: {archivo}'
            }), 404

        crimps = _crimps_por_terminal_archivo(archivo)
        terminales = sorted(t for t, n in crimps.items() if n > 0)

        return jsonify({
            'success': True,
            'terminales': terminales,
            'total': len(terminales)
        })

    except Exception as e:
        return error_interno(e)


@bp.route('/api/asignar-terminal', methods=['POST'])
def api_asignar_terminal():
    """Asignar un terminal a una máquina"""
    try:
        data = request.get_json()
        
        terminal = data.get('terminal', '').strip()
        maquina_id = data.get('maquina_id', '').strip()
        
        if not terminal or not maquina_id:
            return jsonify({
                'success': False,
                'message': 'Terminal y máquina son obligatorios'
            }), 400
        
        maquina_repo = MaquinaRepository(db)
        
        # Verificar que no esté ya asignado
        asignacion_actual = maquina_repo.verificar_terminal_asignado(terminal)
        if asignacion_actual:
            return jsonify({
                'success': False,
                'message': f'El terminal ya está asignado a {asignacion_actual["maquina_nombre"]}'
            }), 400
        
        # Asignar terminal
        if maquina_repo.asignar_terminal(maquina_id, terminal):
            return jsonify({
                'success': True,
                'message': f'Terminal {terminal} asignado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al asignar el terminal'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al asignar terminal')


@bp.route('/api/desasignar-terminal', methods=['POST'])
def api_desasignar_terminal():
    """Desasignar un terminal de su máquina actual"""
    try:
        data = request.get_json()
        
        terminal = data.get('terminal', '').strip()
        
        if not terminal:
            return jsonify({
                'success': False,
                'message': 'Terminal es obligatorio'
            }), 400
        
        maquina_repo = MaquinaRepository(db)
        
        if maquina_repo.desasignar_terminal(terminal):
            return jsonify({
                'success': True,
                'message': f'Terminal {terminal} desasignado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Terminal no encontrado o no asignado'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al desasignar terminal')


# ==================== IMÁGENES DE TERMINALES ====================

MAX_IMAGEN_BYTES = 420_000  # ~300 KB binario ≈ 420 KB en base64

@bp.route('/api/terminal-imagen/<codigo>', methods=['PUT'])
def api_subir_imagen_terminal(codigo):
    """Guardar o actualizar la imagen (base64) de un terminal."""
    try:
        data = request.get_json(silent=True) or {}
        imagen_data = (data.get('imagen_data') or '').strip()

        if not imagen_data:
            return jsonify({'success': False, 'message': 'No se recibió imagen'}), 400

        if not imagen_data.startswith('data:image/'):
            return jsonify({'success': False, 'message': 'Formato inválido (se espera data URL)'}), 400

        if len(imagen_data.encode('utf-8')) > MAX_IMAGEN_BYTES:
            return jsonify({'success': False, 'message': 'Imagen demasiado grande (máx ~300 KB)'}), 400

        db.session.execute(text("""
            INSERT INTO terminales_imagenes (terminal_codigo, imagen_data, updated_at)
            VALUES (:codigo, :img, datetime('now'))
            ON CONFLICT(terminal_codigo) DO UPDATE
                SET imagen_data = excluded.imagen_data,
                    updated_at  = excluded.updated_at
        """), {'codigo': codigo, 'img': imagen_data})
        db.session.commit()

        return jsonify({'success': True, 'message': 'Imagen guardada'})

    except Exception as e:
        return error_interno(e, 'Error al guardar imagen de terminal')


@bp.route('/api/terminal-imagen/<codigo>', methods=['DELETE'])
def api_eliminar_imagen_terminal(codigo):
    """Eliminar la imagen de un terminal."""
    try:
        db.session.execute(
            text("DELETE FROM terminales_imagenes WHERE terminal_codigo = :codigo"),
            {'codigo': codigo}
        )
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al eliminar imagen de terminal')


# ==================== GAVETAS DE TERMINALES ====================

@bp.route('/api/terminal-gaveta/<codigo>', methods=['PUT'])
def api_guardar_gaveta_terminal(codigo):
    """Guardar o actualizar la gaveta de un terminal."""
    try:
        data  = request.get_json(silent=True) or {}
        gaveta = (data.get('gaveta') or '').strip()[:80]   # máx 80 caracteres

        if not gaveta:
            return jsonify({'success': False, 'message': 'La gaveta no puede estar vacía'}), 400

        db.session.execute(text("""
            INSERT INTO terminales_gavetas (terminal_codigo, gaveta, updated_at)
            VALUES (:codigo, :gaveta, datetime('now'))
            ON CONFLICT(terminal_codigo) DO UPDATE
                SET gaveta     = excluded.gaveta,
                    updated_at = excluded.updated_at
        """), {'codigo': codigo, 'gaveta': gaveta})
        db.session.commit()

        return jsonify({'success': True, 'gaveta': gaveta})

    except Exception as e:
        return error_interno(e, 'Error al guardar gaveta de terminal')


@bp.route('/api/terminal-gaveta/<codigo>', methods=['DELETE'])
def api_eliminar_gaveta_terminal(codigo):
    """Eliminar la gaveta de un terminal."""
    try:
        db.session.execute(
            text("DELETE FROM terminales_gavetas WHERE terminal_codigo = :codigo"),
            {'codigo': codigo}
        )
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al eliminar gaveta de terminal')
