"""
Progreso de bonos: registro por terminal, parciales y ponderado.
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
from app.excel_manager import ExcelManager, leer_excel_cacheado
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


# ==================== API DE PROGRESO ====================

@bp.route('/api/bonos/<nombre_bono>/progreso', methods=['GET'])
def api_bonos_progreso_get(nombre_bono):
    """Obtener progreso guardado de un bono"""
    try:
        progreso_path = _ruta_progreso_bono(nombre_bono)
        
        if not os.path.exists(progreso_path):
            return jsonify({
                'success': True,
                'progreso': {}
            })
        
        with open(progreso_path, 'r', encoding='utf-8') as f:
            progreso = json.load(f)
        
        return jsonify({
            'success': True,
            'progreso': progreso
        })
        
    except Exception as e:
        return error_interno(e, 'Error al cargar progreso')


def _terminales_disponibles_bono(nombre_bono):
    """Devuelve el conjunto (set) de terminales que tienen datos en los archivos
    del bono. Lógica compartida por el endpoint de terminales-disponibles y por
    el cálculo de si un bono está finalizado. Devuelve None si el bono no existe."""
    bono_repo = BonoRepository(db)
    bono = bono_repo.obtener_bono_por_nombre(nombre_bono)

    if not bono:
        return None

    orden_repo = OrdenRepository(db)
    ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])

    terminales_con_datos = set()
    upload_folder = current_app.config['UPLOAD_FOLDER']

    # Para cada orden, obtener el archivo y extraer terminales
    archivos_procesados = set()
    for orden in ordenes:
        archivo = orden.get('archivo_excel')
        if not archivo or archivo in archivos_procesados:
            continue

        archivos_procesados.add(archivo)
        filepath = os.path.join(upload_folder, archivo)

        if not os.path.exists(filepath):
            continue

        try:
            # Cargar Excel
            df = leer_excel_cacheado(filepath)

            def _terminal_valido(val):
                t = str(val).strip().upper()
                return t and t != 'S/T' and t != 'NAN'

            # Extraer terminales SOLO si realmente se engastan en ese lado.
            # Si el elemento de ese lado termina en '*', el terminal NO se engasta
            # ahí, por lo que NO debe ofrecerse como terminal seleccionable.
            tiene_de   = 'De Terminal' in df.columns
            tiene_para = 'Para Terminal' in df.columns
            for _, fila in df.iterrows():
                # Ignorar filas auxiliares (sin Cod. cable o sin Sección) — mismo
                # criterio que el engaste (agrupar_por_cable_elemento) y el conteo
                # de crimps. Un terminal cuyas filas no tienen Cod. cable/Sección no
                # genera ningún paquete, así que NO debe ofrecerse como seleccionable.
                cod = str(fila.get('Cod. cable', '')).strip()
                if cod == '' or cod.lower() == 'nan':
                    continue
                sec_raw = fila.get('Sección', fila.get('Seccion', ''))
                sec = str(sec_raw).strip()
                if sec == '' or sec.lower() == 'nan':
                    continue

                if tiene_de:
                    de_term = fila.get('De Terminal', '')
                    de_no_poner = str(fila.get('De Elemento', '')).strip().endswith('*')
                    if _terminal_valido(de_term) and not de_no_poner:
                        terminales_con_datos.add(str(de_term).strip().upper())
                if tiene_para:
                    para_term = fila.get('Para Terminal', '')
                    para_no_poner = str(fila.get('Para Elemento', '')).strip().endswith('*')
                    if _terminal_valido(para_term) and not para_no_poner:
                        terminales_con_datos.add(str(para_term).strip().upper())

        except Exception as e:
            print(f"Error procesando archivo {archivo}: {e}")
            continue

    return terminales_con_datos


def _bono_finalizado(nombre_bono, terminales=None):
    """Determina si un bono está finalizado: tiene al menos un terminal con datos
    y TODOS sus terminales disponibles están marcados como 'completado' en el
    progreso guardado. Devuelve False si el bono no tiene terminales o no hay
    progreso."""
    try:
        if terminales is None:
            terminales = _terminales_disponibles_bono(nombre_bono)

        if not terminales:
            return False

        progreso_path = _ruta_progreso_bono(nombre_bono)
        if not os.path.exists(progreso_path):
            return False

        with open(progreso_path, 'r', encoding='utf-8') as f:
            progreso = json.load(f)

        for terminal in terminales:
            info = progreso.get(terminal)
            if not info or info.get('estado') != 'completado':
                return False

        return True
    except Exception:
        return False


@bp.route('/api/bonos/<nombre_bono>/terminales-disponibles', methods=['GET'])
def api_bonos_terminales_disponibles(nombre_bono):
    """Obtener terminales que tienen datos en los archivos del bono"""
    try:
        terminales_con_datos = _terminales_disponibles_bono(nombre_bono)

        if terminales_con_datos is None:
            return jsonify({'success': False, 'message': 'Bono no encontrado'})

        return jsonify({
            'success': True,
            'terminales': sorted(list(terminales_con_datos))
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<nombre_bono>/progreso', methods=['POST'])
def api_bonos_progreso_post(nombre_bono):
    """Guardar progreso de un terminal/carro en un bono"""
    try:
        data = request.get_json()
        terminal = data.get('terminal')
        carro = data.get('carro')
        terminales_proyecto = data.get('terminales_proyecto', [])
        operario = (data.get('operario') or '').strip()

        if not terminal or not (carro or isinstance(carro, int)):
            return jsonify({
                'success': False,
                'message': 'Se requiere terminal y carro'
            })
        
        # Cargar progreso existente
        progreso_path = _ruta_progreso_bono(nombre_bono)
        
        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)
        else:
            progreso = {}
        
        # Inicializar estructura para este terminal si no existe
        if terminal not in progreso:
            progreso[terminal] = {
                'estado': 'en_proceso',
                'carros_completados': [],
                'fecha_inicio': _ahora_iso(),
                'fecha_ultima_actualizacion': _ahora_iso()
            }

        # Guardar operario si se envió
        if operario:
            progreso[terminal]['operario'] = operario

        # Agregar carro a completados si no está ya
        if carro not in progreso[terminal]['carros_completados']:
            progreso[terminal]['carros_completados'].append(carro)

        # Registrar fecha/operario exactos de finalización de ESTE carro
        # (para el report de trazabilidad por carro). Idempotente por carro_key.
        registro = progreso[terminal].get('carros_registro', {})
        registro[str(carro)] = {
            'operario': operario or progreso[terminal].get('operario', ''),
            'fecha': _ahora_iso()
        }
        progreso[terminal]['carros_registro'] = registro

        # Limpiar de carros_con_pendientes si estaba anotado ahí
        carros_pend = progreso[terminal].get('carros_con_pendientes', {})
        carros_pend.pop(str(carro), None)
        progreso[terminal]['carros_con_pendientes'] = carros_pend
        
        # Actualizar fecha
        progreso[terminal]['fecha_ultima_actualizacion'] = _ahora_iso()
        
        # Marcar como completado si ya no hay más carros pendientes
        # Nota: necesitaríamos saber el total de carros del bono, por ahora solo marcamos como en_proceso
        
        # Guardar progreso
        with open(progreso_path, 'w', encoding='utf-8') as f:
            json.dump(progreso, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            'success': True,
            'message': f'Progreso guardado para terminal {terminal}, carro {carro}',
            'progreso_actual': progreso[terminal]
        })
        
    except Exception as e:
        return error_interno(e, 'Error al guardar progreso')

@bp.route('/api/bonos/<nombre_bono>/progreso/parcial', methods=['POST'])
def api_bonos_progreso_parcial(nombre_bono):
    """Guardar progreso parcial de un carro (cancelado a mitad, con paquetes saltados)"""
    try:
        data = request.get_json()
        terminal = data.get('terminal')
        carro = data.get('carro')
        paquetes_saltados = data.get('paquetes_saltados', [])
        paquetes_hechos = data.get('paquetes_hechos', 0)
        operario = (data.get('operario') or '').strip()

        if not terminal:
            return jsonify({'success': False, 'message': 'Se requiere terminal'})

        progreso_path = _ruta_progreso_bono(nombre_bono)

        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)
        else:
            progreso = {}

        if terminal not in progreso:
            progreso[terminal] = {
                'estado': 'en_proceso',
                'carros_completados': [],
                'fecha_inicio': _ahora_iso(),
                'fecha_ultima_actualizacion': _ahora_iso()
            }

        # Guardar operario si se envió
        if operario:
            progreso[terminal]['operario'] = operario

        # Guardar paquetes saltados por carro
        if 'paquetes_saltados_por_carro' not in progreso[terminal]:
            progreso[terminal]['paquetes_saltados_por_carro'] = {}

        carro_key = str(carro) if carro is not None else 'sin_carro'

        paquetes_pendientes = data.get('paquetes_pendientes', paquetes_saltados)  # alias

        if paquetes_pendientes:
            # Hay paquetes pendientes: guardar en carros_con_pendientes (carro NO completado)
            if 'carros_con_pendientes' not in progreso[terminal]:
                progreso[terminal]['carros_con_pendientes'] = {}
            progreso[terminal]['carros_con_pendientes'][carro_key] = {
                'paquetes': paquetes_pendientes,
                'fecha': _ahora_iso()
            }
        else:
            # Sin pendientes: marcar como completado y limpiar cualquier entrada previa
            if 'carros_con_pendientes' in progreso[terminal]:
                progreso[terminal]['carros_con_pendientes'].pop(carro_key, None)
            if carro is not None and carro not in progreso[terminal]['carros_completados']:
                progreso[terminal]['carros_completados'].append(carro)
            # Registrar fecha/operario exactos de finalización de este carro
            if carro is not None:
                registro = progreso[terminal].get('carros_registro', {})
                registro[carro_key] = {
                    'operario': operario or progreso[terminal].get('operario', ''),
                    'fecha': _ahora_iso()
                }
                progreso[terminal]['carros_registro'] = registro

        progreso[terminal]['paquetes_saltados_por_carro'][carro_key] = {
            'paquetes_hechos': paquetes_hechos,
            'saltados': paquetes_saltados,
            'fecha': _ahora_iso()
        }
        progreso[terminal]['fecha_ultima_actualizacion'] = _ahora_iso()

        with open(progreso_path, 'w', encoding='utf-8') as f:
            json.dump(progreso, f, indent=2, ensure_ascii=False)

        return jsonify({
            'success': True,
            'message': f'{paquetes_hechos} paquetes hechos, {len(paquetes_saltados)} saltados guardados para carro {carro}'
        })

    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<nombre_bono>/progreso/estado', methods=['POST'])
def api_bonos_progreso_estado(nombre_bono):
    """Actualizar solo el estado de un terminal (en_proceso / completado)"""
    try:
        data = request.get_json()
        terminal = data.get('terminal')
        estado = data.get('estado')  # 'en_proceso' o 'completado'
        operario = (data.get('operario') or '').strip()

        if not terminal or estado not in ('en_proceso', 'completado'):
            return jsonify({'success': False, 'message': 'Parámetros inválidos'})

        progreso_path = _ruta_progreso_bono(nombre_bono)

        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)
        else:
            progreso = {}

        if terminal not in progreso:
            progreso[terminal] = {
                'estado': estado,
                'carros_completados': [],
                'fecha_inicio': _ahora_iso(),
                'fecha_ultima_actualizacion': _ahora_iso()
            }
        else:
            progreso[terminal]['estado'] = estado
            progreso[terminal]['fecha_ultima_actualizacion'] = _ahora_iso()

        if operario:
            progreso[terminal]['operario'] = operario

        with open(progreso_path, 'w', encoding='utf-8') as f:
            json.dump(progreso, f, indent=2, ensure_ascii=False)

        return jsonify({'success': True, 'terminal': terminal, 'estado': estado})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<nombre_bono>/progreso-por-carro', methods=['GET'])
def api_bonos_progreso_por_carro(nombre_bono):
    """Progreso agrupado por carro: {carro_id: {terminales_completados: [...]}}"""
    try:
        progreso_path = _ruta_progreso_bono(nombre_bono)
        progreso = {}
        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)

        por_carro = {}
        for terminal, data in progreso.items():
            for carro in (data.get('carros_completados') or []):
                carro_key = str(carro)
                if carro_key not in por_carro:
                    por_carro[carro_key] = {'terminales_completados': []}
                por_carro[carro_key]['terminales_completados'].append(terminal)

        return jsonify({'success': True, 'progreso_por_carro': por_carro})

    except Exception as e:
        return error_interno(e)


def _crimps_por_terminal_archivo(archivo: str) -> dict:
    """
    Calcula el nº de crimps (terminales a engastar) por terminal de un archivo Excel,
    usando EXACTAMENTE la misma lógica que la vista de engastado
    (excel_manager.agrupar_por_cable_elemento): cada lado sin '*' = 1 crimp; si el
    terminal está en ambos lados de la fila sin '*' = 2 crimps. Los lados con '*'
    (terminal no se engasta) o terminales vacíos/'S/T' no cuentan.

    Devuelve {TERMINAL_UPPER: num_crimps}. Esto refleja el trabajo REAL del operario,
    a diferencia del antiguo cálculo que solo miraba 'De Terminal' y descartaba los
    grupos cuyo terminal estaba en el lado 'Para' (de_terminal vacío/S/T).
    """
    upload_folder = current_app.config['UPLOAD_FOLDER']
    mgr = ExcelManager(upload_folder)
    if not mgr.cargar_excel_directo(archivo):
        return {}
    df = mgr.current_df
    if df is None:
        return {}

    def _valido(t):
        return t and t not in ('NAN', 'S/T', '')

    cont = {}
    for _, row in df.iterrows():
        # Ignorar filas auxiliares (sin Cod. cable o sin Sección) — igual que el engastado
        cod = str(row.get('Cod. cable', '')).strip()
        if cod == '' or cod.lower() == 'nan':
            continue
        sec_raw = row.get('Sección', row.get('Seccion', ''))
        sec = str(sec_raw).strip()
        if sec == '' or sec.lower() == 'nan':
            continue

        de_t   = str(row.get('De Terminal', '')).strip().upper()
        para_t = str(row.get('Para Terminal', '')).strip().upper()
        de_np   = str(row.get('De Elemento', '')).strip().endswith('*')
        para_np = str(row.get('Para Elemento', '')).strip().endswith('*')

        tiene_o = _valido(de_t)
        tiene_d = _valido(para_t)

        if tiene_o and tiene_d and de_t == para_t:
            # Terminal en ambos lados de la misma fila
            if de_np and para_np:
                pass
            elif de_np or para_np:
                cont[de_t] = cont.get(de_t, 0) + 1
            else:
                cont[de_t] = cont.get(de_t, 0) + 2
        else:
            if tiene_o and not de_np:
                cont[de_t] = cont.get(de_t, 0) + 1
            if tiene_d and not para_np:
                cont[para_t] = cont.get(para_t, 0) + 1

    return cont


@bp.route('/api/bonos/<nombre_bono>/progreso-ponderado', methods=['GET'])
def api_bonos_progreso_ponderado(nombre_bono):
    """
    Progreso ponderado del bono usando num_terminales como peso.
    Devuelve:
      - peso_total_bono, peso_completado_bono, porcentaje_bono
      - terminales: lista con peso_total, peso_completado, porcentaje, estado por terminal
      - progreso_por_carro: {carro_id: {peso_total, peso_completado, porcentaje, terminales_completados}}
    """
    try:
        bono_repo = BonoRepository(db)
        orden_repo = OrdenRepository(db)

        bono = bono_repo.obtener_bono_por_nombre(nombre_bono)
        if not bono:
            return jsonify({'success': False, 'message': 'Bono no encontrado'})

        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])

        # Construir pesos: {terminal: {str(carro_numero): peso_acumulado}}
        pesos_terminal_carro = {}
        _cache_crimps = {}  # archivo -> {terminal: num_crimps}

        for idx, orden in enumerate(ordenes):
            archivo = orden.get('archivo_excel')
            if not archivo:
                continue
            # IMPORTANTE: el carro se numera por POSICIÓN (idx+1), igual que el
            # frontend de engastado (carrosDelBono = ordenes.map((o, idx) => carro: idx+1)).
            # No usar carro_numero de la BD: puede no coincidir con el orden posicional
            # y provoca que carros_completados nunca cuadre con los pesos (progreso a 0).
            carro_key = str(idx + 1)

            # Crimps por terminal con la MISMA lógica que ve el operario (De+Para, sin '*')
            if archivo not in _cache_crimps:
                _cache_crimps[archivo] = _crimps_por_terminal_archivo(archivo)

            for terminal, peso in _cache_crimps[archivo].items():
                if not terminal:
                    continue
                if terminal not in pesos_terminal_carro:
                    pesos_terminal_carro[terminal] = {}
                pesos_terminal_carro[terminal][carro_key] = (
                    pesos_terminal_carro[terminal].get(carro_key, 0) + int(peso or 0)
                )

        # Leer progreso guardado
        progreso_path = _ruta_progreso_bono(nombre_bono)
        progreso = {}
        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)

        # Calcular métricas por terminal
        resumen_terminales = []
        peso_total_bono = 0
        peso_completado_bono = 0

        for terminal, pesos_por_carro in sorted(pesos_terminal_carro.items()):
            peso_total_terminal = sum(pesos_por_carro.values())
            prog_t = progreso.get(terminal, {})
            carros_completados = [str(c) for c in (prog_t.get('carros_completados') or [])]
            tiene_pendientes = bool(prog_t.get('carros_con_pendientes'))
            estado_guardado = prog_t.get('estado')

            peso_completado_terminal = sum(
                pesos_por_carro.get(carro_id, 0) for carro_id in carros_completados
            )
            # Red de seguridad: si el operario marcó el terminal como 'completado',
            # contar todo su peso aunque el mapeo de carros no cuadre perfectamente.
            if estado_guardado == 'completado':
                peso_completado_terminal = peso_total_terminal

            peso_total_bono += peso_total_terminal
            peso_completado_bono += peso_completado_terminal

            if peso_total_terminal > 0 and peso_completado_terminal >= peso_total_terminal:
                estado = 'completado'
            elif peso_completado_terminal > 0 or tiene_pendientes:
                estado = 'en_proceso'
            else:
                estado = 'pendiente'

            resumen_terminales.append({
                'terminal': terminal,
                'peso_total': peso_total_terminal,
                'peso_completado': peso_completado_terminal,
                'porcentaje': round(peso_completado_terminal / peso_total_terminal * 100, 1) if peso_total_terminal > 0 else 0,
                'estado': estado,
                'carros_completados': carros_completados,
                'tiene_pendientes': tiene_pendientes,
                'pesos_por_carro': pesos_por_carro
            })

        porcentaje_bono = round(peso_completado_bono / peso_total_bono * 100, 1) if peso_total_bono > 0 else 0

        # Calcular progreso ponderado por carro
        # Usar las claves de pesos_terminal_carro (ya incluye fallback sintético idx+1)
        carros_unicos = set()
        for pesos in pesos_terminal_carro.values():
            carros_unicos.update(pesos.keys())
        carros_data = {}
        for carro_key in sorted(carros_unicos):
            peso_carro_total = sum(pesos.get(carro_key, 0) for pesos in pesos_terminal_carro.values())
            peso_carro_completado = 0
            terminales_completados = []
            for terminal, pesos in pesos_terminal_carro.items():
                prog_t = progreso.get(terminal, {})
                ccs = [str(c) for c in (prog_t.get('carros_completados') or [])]
                # Cuenta el carro como hecho si está en carros_completados, o si el
                # terminal entero está marcado como 'completado' (red de seguridad).
                if carro_key in ccs or prog_t.get('estado') == 'completado':
                    peso_carro_completado += pesos.get(carro_key, 0)
                    if terminal not in terminales_completados:
                        terminales_completados.append(terminal)
            carros_data[carro_key] = {
                'peso_total': peso_carro_total,
                'peso_completado': peso_carro_completado,
                'porcentaje': round(peso_carro_completado / peso_carro_total * 100, 1) if peso_carro_total > 0 else 0,
                'terminales_completados': terminales_completados
            }

        return jsonify({
            'success': True,
            'peso_total_bono': peso_total_bono,
            'peso_completado_bono': peso_completado_bono,
            'porcentaje_bono': porcentaje_bono,
            'terminales': resumen_terminales,
            'progreso_por_carro': carros_data
        })

    except Exception as e:
        return error_interno(e)
