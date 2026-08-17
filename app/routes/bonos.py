"""
Bonos: CRUD, generación desde carros y nombre sugerido.
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
    _ruta_progreso_bono,
    bp, db, error_interno, allowed_file, _ruta_upload_segura,
    _ahora_iso, _detectar_hoja, _es_error_nombre_bono_duplicado,
)


# ==================== GESTIÓN DE BONOS ====================

@bp.route('/api/bonos', methods=['GET'])
def api_obtener_bonos():
    """Obtener listado de bonos"""
    try:
        from app.routes.progreso import _bono_finalizado

        bono_repo = BonoRepository(db)
        estado = request.args.get('estado')
        
        bonos = bono_repo.obtener_todos_bonos(estado)

        # Marcar cada bono como finalizado si todos sus terminales están completados
        for bono in bonos:
            bono['finalizado'] = _bono_finalizado(bono.get('nombre'))
        
        return jsonify({
            'success': True,
            'bonos': bonos
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<nombre>', methods=['GET'])
def api_obtener_bono_por_nombre(nombre):
    """Obtener bono por nombre con sus órdenes"""
    try:
        bono_repo = BonoRepository(db)
        orden_repo = OrdenRepository(db)
        
        # Buscar bono por nombre
        bonos = bono_repo.obtener_todos_bonos()
        bono = next((b for b in bonos if b['nombre'] == nombre), None)
        
        if not bono:
            return jsonify({
                'success': False,
                'message': f'No se encontró el bono {nombre}'
            }), 404
        
        # Obtener órdenes del bono
        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])
        
        # Construir respuesta con información completa
        # Si carro_numero es NULL (bonos migrados), usar índice+1 como fallback
        carros_list = [
            {
                'carro': o.get('carro_numero') if o.get('carro_numero') is not None else (idx + 1),
                'archivo_excel': o.get('archivo_excel'),
                'proyecto_nombre': o.get('numero', '')
            }
            for idx, o in enumerate(ordenes)
            if o.get('archivo_excel')
        ]
        bono_completo = {
            'id': bono['id'],
            'nombre': bono['nombre'],
            'descripcion': bono.get('descripcion'),
            'estado': bono['estado'],
            'fecha_creacion': bono['fecha_creacion'],
            'total_ordenes': len(ordenes),
            'ordenes': ordenes,
            'carros': carros_list,
            'num_cortes': len(carros_list)
        }
        
        return jsonify({
            'success': True,
            'bono': bono_completo
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<nombre>', methods=['DELETE'])
def api_eliminar_bono(nombre):
    """Eliminar bono por nombre"""
    try:
        bono_repo = BonoRepository(db)
        bono = bono_repo.obtener_bono_por_nombre(nombre)
        if not bono:
            return jsonify({'success': False, 'error': 'Bono no encontrado'}), 404

        ok = bono_repo.eliminar_bono(bono['id'])
        if not ok:
            return jsonify({'success': False, 'error': 'No se pudo eliminar el bono'}), 500

        # Borrar fichero de progreso si existe
        import os
        progreso_path = _ruta_progreso_bono(nombre)
        if os.path.exists(progreso_path):
            os.remove(progreso_path)

        return jsonify({'success': True, 'message': f'Bono {nombre} eliminado correctamente'})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos', methods=['POST'])
def api_crear_bono():
    """Crear nuevo bono"""
    try:
        data = request.get_json()
        
        bono_repo = BonoRepository(db)
        with db.engine.begin() as conn:
            bono_id = bono_repo.crear_bono(
                nombre=data['nombre'],
                ordenes_ids=data['ordenes_ids'],
                descripcion=data.get('descripcion'),
                conn=conn
            )
        
        bono = bono_repo.obtener_bono_con_ordenes(bono_id)
        
        return jsonify({
            'success': True,
            'bono': bono
        })
    except IntegrityError as e:
        if _es_error_nombre_bono_duplicado(e):
            return jsonify({
                'success': False,
                'message': 'Ya existe un bono con ese nombre. Refresca el nombre sugerido e inténtalo de nuevo.'
            }), 409
        return error_interno(e)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<bono_id>/carro', methods=['PUT'])
def api_asignar_bono_carro(bono_id):
    """Asignar bono a un carro"""
    try:
        data = request.get_json()
        carro_numero = data.get('carro_numero')
        
        bono_repo = BonoRepository(db)
        success = bono_repo.asignar_a_carro(bono_id, carro_numero)
        
        if success:
            bono = bono_repo.obtener_bono_con_ordenes(bono_id)
            return jsonify({
                'success': True,
                'bono': bono
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo asignar el carro'
            }), 400
            
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/nombre-sugerido', methods=['GET'])
def api_obtener_nombre_sugerido_bono():
    """Obtener nombre sugerido para el siguiente bono en formato DDMMYYYY_N"""
    try:
        from datetime import datetime
        
        bono_repo = BonoRepository(db)
        
        # Formato: DDMMYYYY
        fecha_hoy = datetime.now().strftime('%d%m%Y')
        
        # Obtener todos los bonos
        bonos = bono_repo.obtener_todos_bonos()
        
        # Filtrar bonos del día de hoy y encontrar el último número
        bonos_hoy = [b for b in bonos if b['nombre'].startswith(fecha_hoy)]
        
        if bonos_hoy:
            # Extraer números y encontrar el máximo
            numeros = []
            for bono in bonos_hoy:
                try:
                    # Formato esperado: DDMMYYYY_N
                    partes = bono['nombre'].split('_')
                    if len(partes) >= 2:
                        numeros.append(int(partes[-1]))
                except (ValueError, IndexError):
                    continue
            
            siguiente_numero = max(numeros) + 1 if numeros else 1
        else:
            siguiente_numero = 1
        
        nombre_sugerido = f"{fecha_hoy}_{siguiente_numero}"
        
        return jsonify({
            'success': True,
            'nombre': nombre_sugerido
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/generar', methods=['POST'])
def api_generar_bono_desde_carros():
    """Generar bono a partir de los carros ocupados"""
    try:
        data = request.get_json()
        nombre_bono = data.get('nombre')
        
        if not nombre_bono:
            return jsonify({
                'success': False,
                'message': 'El nombre del bono es requerido'
            }), 400
        
        proyecto_repo = ProyectoRepository(db)
        orden_repo = OrdenRepository(db)
        bono_repo = BonoRepository(db)
        
        # Obtener todos los proyectos con carro asignado
        proyectos = proyecto_repo.obtener_todos_proyectos()
        proyectos_en_carros = [p for p in proyectos if p['carro_asignado'] is not None]
        
        if not proyectos_en_carros:
            return jsonify({
                'success': False,
                'message': 'No hay carros con proyectos asignados'
            }), 400
        
        if len(proyectos_en_carros) > 6:
            return jsonify({
                'success': False,
                'message': 'No se pueden incluir más de 6 carros en un bono'
            }), 400
        
        # Extraer números de orden de los proyectos
        ordenes_ids = []
        carros_info = []
        
        for proyecto in proyectos_en_carros:
            # Extraer número de orden del nombre del proyecto (formato: "60245848 - H0068722")
            try:
                numero_orden = proyecto['nombre'].split(' - ')[0].strip()
            except Exception:
                numero_orden = proyecto['nombre']
            
            ordenes_ids.append(numero_orden)
            
            carros_info.append({
                'carro': proyecto['carro_asignado'],
                'proyecto_nombre': proyecto['nombre'],
                'archivo_excel': proyecto['archivo']
            })
        
        # CREAR EL BONO + ACTUALIZAR ÓRDENES + LIBERAR CARROS DE FORMA ATÓMICA
        # Todo dentro de un único engine.begin(): se commitea junto o se
        # revierte junto si cualquier paso falla.
        descripcion = f"Bono con {len(proyectos_en_carros)} carros"
        with db.engine.begin() as conn:
            bono_id = bono_repo.crear_bono(
                nombre=nombre_bono,
                ordenes_ids=ordenes_ids,
                descripcion=descripcion,
                conn=conn
            )

            # Cambiar estado de las órdenes a 'en_bono' y guardar carro_numero
            for idx, (numero_orden, carro_info) in enumerate(zip(ordenes_ids, carros_info)):
                orden_repo.cambiar_estado(numero_orden, 'en_bono', conn=conn)
                # Guardar el carro_numero en la orden para que el dashboard ponderado funcione
                conn.execute(
                    text("UPDATE ordenes_produccion SET carro_numero=:carro WHERE numero=:numero AND bono_id=:bono_id"),
                    {'carro': carro_info['carro'], 'numero': numero_orden, 'bono_id': bono_id}
                )

            # Liberar los carros (establecer carro_asignado a NULL)
            for proyecto in proyectos_en_carros:
                proyecto_repo.liberar_carro(proyecto['id'], conn=conn)
        
        # Construir respuesta con información del bono
        bono_generado = {
            'nombre': nombre_bono,
            'num_cortes': len(carros_info),
            'carros': carros_info,
            'id': bono_id
        }
        
        return jsonify({
            'success': True,
            'bono': bono_generado
        })
        
    except IntegrityError as e:
        if _es_error_nombre_bono_duplicado(e):
            return jsonify({
                'success': False,
                'message': 'Ya existe un bono con ese nombre. Refresca el nombre sugerido e inténtalo de nuevo.'
            }), 409
        return error_interno(e, 'Error al generar bono')
    except Exception as e:
        return error_interno(e, 'Error al generar bono')
