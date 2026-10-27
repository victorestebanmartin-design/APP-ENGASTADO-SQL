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
        # Órdenes que componen cada bono (para el tooltip de las listas)
        por_bono = {}
        for o in bono_repo.execute_select(
                "SELECT bono_id, numero, proyecto, descripcion, cantidad, carro_numero "
                "FROM ordenes_produccion WHERE bono_id IS NOT NULL "
                "ORDER BY carro_numero, numero"):
            por_bono.setdefault(o['bono_id'], []).append({
                'numero': o['numero'],
                'proyecto': o['proyecto'],
                'descripcion': o['descripcion'],
                'cantidad': o['cantidad'],
                'carro': o['carro_numero'],
            })

        for bono in bonos:
            bono['finalizado'] = _bono_finalizado(bono.get('nombre'))
            bono['ordenes_resumen'] = por_bono.get(bono['id'], [])

        return jsonify({
            'success': True,
            'bonos': bonos
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<path:nombre>', methods=['GET'])
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
            'numeracion_carros': bono.get('numeracion_carros', 'posicional'),
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


@bp.route('/api/bonos/<path:nombre>', methods=['DELETE'])
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


_NOMBRE_BONO_VALIDO = re.compile(r'^[\w.\- ]+$')
_NOMBRE_BONO_NUEVO = re.compile(r'^(\d{7})_(\d{4})$')
_ESTADOS_BONO = ('activo', 'completado', 'pausado')


@bp.route('/api/bonos/<path:nombre>', methods=['PUT'])
def api_actualizar_bono(nombre):
    """Cambiar nombre y/o estado de un bono.

    El progreso vive en progreso_bono_<nombre>.json, así que renombrar mueve
    ese fichero a la vez que la fila de la BD: si una de las dos cosas falla,
    no se queda ninguna a medias. No se permite renombrar con un puesto
    trabajando en el bono (seguiría escribiendo el progreso con el nombre viejo).
    """
    try:
        data = request.get_json(silent=True) or {}
        bono_repo = BonoRepository(db)
        bono = bono_repo.obtener_bono_por_nombre(nombre)
        if not bono:
            return jsonify({'success': False, 'error': 'Bono no encontrado'}), 404

        nuevo_nombre = str(data.get('nombre', nombre)).strip()
        estado = data.get('estado', bono['estado'])
        if not nuevo_nombre or not _NOMBRE_BONO_VALIDO.match(nuevo_nombre) \
                or nuevo_nombre.strip('. ') != nuevo_nombre:
            return jsonify({
                'success': False,
                'error': 'El nombre solo puede llevar letras, números, espacios, '
                         'guion, guion bajo y punto'
            }), 400
        if estado not in _ESTADOS_BONO:
            return jsonify({
                'success': False,
                'error': f"Estado no válido. Usa: {', '.join(_ESTADOS_BONO)}"
            }), 400

        renombrar = nuevo_nombre != nombre
        if renombrar:
            archivos = {o.get('archivo_excel')
                        for o in OrdenRepository(db).obtener_ordenes_por_bono(bono['id'])
                        if o.get('archivo_excel')}
            trabajando = [s for s in SesionTrabajoRepository(db).obtener_sesiones_activas()
                          if s.get('archivo_excel') in archivos]
            if trabajando:
                return jsonify({
                    'success': False,
                    'error': 'Hay un puesto trabajando con este bono. Termina o libera '
                             'su sesión antes de cambiarle el nombre.'
                }), 409

        from app.routes.progreso import _obtener_lock_progreso
        ruta_vieja = _ruta_progreso_bono(nombre)
        ruta_nueva = _ruta_progreso_bono(nuevo_nombre)
        with _obtener_lock_progreso(nombre):
            if renombrar and os.path.exists(ruta_vieja) and os.path.exists(ruta_nueva):
                return jsonify({
                    'success': False,
                    'error': 'Ya existe un fichero de progreso con ese nombre'
                }), 409
            movido = False
            try:
                with db.engine.begin() as conn:
                    conn.execute(
                        text("UPDATE bonos SET nombre = :n, estado = :e WHERE id = :id"),
                        {'n': nuevo_nombre, 'e': estado, 'id': bono['id']})
                    if renombrar and os.path.exists(ruta_vieja):
                        os.replace(ruta_vieja, ruta_nueva)
                        movido = True
            except Exception:
                if movido and os.path.exists(ruta_nueva) and not os.path.exists(ruta_vieja):
                    os.replace(ruta_nueva, ruta_vieja)
                raise

        return jsonify({'success': True, 'nombre': nuevo_nombre, 'estado': estado})
    except IntegrityError as e:
        if _es_error_nombre_bono_duplicado(e):
            return jsonify({'success': False, 'error': 'Ya existe un bono con ese nombre'}), 409
        return error_interno(e)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos', methods=['POST'])
def api_crear_bono():
    """Crear nuevo bono"""
    try:
        data = request.get_json()

        nombre = str(data['nombre']).strip()
        if not _NOMBRE_BONO_VALIDO.match(nombre) or nombre.strip('. ') != nombre:
            return jsonify({
                'success': False,
                'message': 'El nombre del bono solo puede llevar letras, números, espacios, punto, guion y guion bajo (sin "/").'
            }), 400

        bono_repo = BonoRepository(db)
        with db.engine.begin() as conn:
            bono_id = bono_repo.crear_bono(
                nombre=nombre,
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
    """Obtener nombre sugerido para el siguiente bono en formato NNNNNNN_AAAA.

    El contador reinicia cada año y el año va en el nombre, así que 0000001_2026
    y 0000001_2027 no chocan. Los bonos con el formato antiguo (DDMMYYYY_N) se
    ignoran: no cuentan para el contador.
    """
    try:
        bono_repo = BonoRepository(db)
        anio = str(datetime.now().year)

        ultimo = 0
        for bono in bono_repo.obtener_todos_bonos():
            m = _NOMBRE_BONO_NUEVO.match(bono['nombre'])
            if m and m.group(2) == anio:
                ultimo = max(ultimo, int(m.group(1)))

        nombre_sugerido = f"{ultimo + 1:07d}_{anio}"

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
        seleccion = data.get('carros')
        if seleccion is not None and (
            not isinstance(seleccion, list) or not seleccion or len(seleccion) > 6
            or any(type(numero) is not int or not 1 <= numero <= 6 for numero in seleccion)
            or len(set(seleccion)) != len(seleccion)
        ):
            return jsonify(success=False, message='Selecciona entre uno y seis carros distintos'), 400
        
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
        if seleccion is not None:
            proyectos_en_carros = [proyecto for proyecto in proyectos_en_carros if proyecto['carro_asignado'] in seleccion]
            if {proyecto['carro_asignado'] for proyecto in proyectos_en_carros} != set(seleccion):
                return jsonify(success=False, message='El contenido de los carros ha cambiado. Actualiza la pantalla.'), 409
        proyectos_en_carros.sort(key=lambda proyecto: proyecto['carro_asignado'])
        
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
            conn.execute(text('UPDATE carros SET numero = numero'))
            for proyecto in proyectos_en_carros:
                actual = conn.execute(text('SELECT * FROM proyectos WHERE id = :id'), {'id': proyecto['id']}).mappings().first()
                carro = conn.execute(text('SELECT * FROM carros WHERE numero = :numero'), {'numero': proyecto['carro_asignado']}).mappings().first()
                if not actual or actual['carro_asignado'] != proyecto['carro_asignado'] or not carro or carro['bono_id'] or carro['estado'] == 'en_proceso':
                    return jsonify(success=False, message='Los carros han cambiado o ya estan ocupados por un bono'), 409
                if proyecto['orden_id']:
                    orden = conn.execute(text('SELECT * FROM ordenes_produccion WHERE id = :id'), {'id': proyecto['orden_id']}).mappings().first()
                    if not orden or orden['bono_id'] or orden['estado'] != 'en_proceso':
                        return jsonify(success=False, message='Una orden ya no esta disponible para este bono'), 409
            bono_id = bono_repo.crear_bono(
                nombre=nombre_bono,
                ordenes_ids=ordenes_ids,
                descripcion=descripcion,
                conn=conn
            )
            conn.execute(text("UPDATE bonos SET numeracion_carros = 'fisica' WHERE id = :id"), {'id': bono_id})

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
                conn.execute(text("UPDATE carros SET bono_id = :bono, estado = 'en_proceso' WHERE numero = :numero"), {'bono': bono_id, 'numero': proyecto['carro_asignado']})
        
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
