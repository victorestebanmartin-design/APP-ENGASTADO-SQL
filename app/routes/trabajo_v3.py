"""
Vista de trabajo V3: datos por terminal y sesiones de bloqueo concurrente.
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


@bp.route('/api/datos_trabajo_v3')
def datos_trabajo_v3():
    """
    Obtener datos de trabajo para V3
    Parámetros: archivo, terminal, maquina
    Procesa el Excel y retorna los paquetes agrupados para el terminal
    """
    try:
        archivo = request.args.get('archivo')
        terminal = request.args.get('terminal')
        maquina = request.args.get('maquina')
        
        if not archivo or not terminal:
            return jsonify({
                'success': False,
                'message': 'Parámetros incompletos (se requiere archivo y terminal)'
            })
        
        # Crear instancia del ExcelManager
        upload_folder = current_app.config['UPLOAD_FOLDER']
        manager = ExcelManager(upload_folder)
        
        # Cargar el archivo Excel
        if not manager.cargar_excel_directo(archivo):
            return jsonify({
                'success': False,
                'message': f'No se pudo cargar el archivo {archivo}. Verifica que existe en data/cortes/'
            })
        
        # Buscar datos del terminal
        resultados = manager.buscar_terminal(terminal)
        
        if not resultados:
            return jsonify({
                'success': True,
                'paquetes': [],
                'total_terminales': 0,
                'grupos': [],
                'message': f'Terminal {terminal} no encontrado en el archivo'
            })
        
        # Agrupar por cable y elemento
        grupos = manager.agrupar_por_cable_elemento(resultados, terminal)
        
        # Convertir a lista de paquetes
        paquetes_raw = []
        total_terminales = 0

        for grupo in grupos.values():
            paquete = {
                'cod_cable': grupo['cod_cable'],
                'elemento': grupo['elemento'],
                'descripcion': grupo['descripcion'],
                'seccion': grupo['seccion'],
                'longitud': grupo['longitud'],
                'cables': grupo['todos_cables'],
                'num_cables': grupo['num_cables'],
                'num_terminales': grupo['num_terminales'],
                'cables_doble_terminal': grupo.get('cables_doble_terminal', []),
                'cables_de_terminal': grupo.get('cables_de_terminal', []),
                'cables_para_terminal': grupo.get('cables_para_terminal', []),
                'archivo_excel': archivo,  # para lookup de etiqueta correcto por archivo
                'serie_col': grupo.get('serie_col', ''),
            }
            paquetes_raw.append(paquete)
            total_terminales += grupo['num_terminales']

        # Ocultar paquetes que no tienen NADA que engastar para este terminal.
        # Ocurre cuando todas las filas del grupo tienen el elemento marcado con '*'
        # (terminal no se engasta ahí): las tres listas de cables quedan vacías.
        # El operario no debe ver esos paquetes (no hay trabajo que hacer en ellos).
        def _tiene_engaste(p):
            return (len(p.get('cables_de_terminal', [])) +
                    len(p.get('cables_para_terminal', [])) +
                    len(p.get('cables_doble_terminal', []))) > 0

        paquetes_raw = [p for p in paquetes_raw if _tiene_engaste(p)]

        # Fusionar paquetes de la misma serie — fuente: columna 'Series' del Excel
        series_paquetes = {}       # serie_code -> [paquete, ...]
        paquetes_individuales = []
        for p in paquetes_raw:
            sc = (p.get('serie_col') or '').strip()
            if sc:
                series_paquetes.setdefault(sc, []).append(p)
            else:
                paquetes_individuales.append(p)

        # NOTA: NO se eliminan individuales cuyo nombre base exista como hijo de serie.
        # TB1 y TB1(S206) son grupos distintos aunque compartan cod_cable y base del nombre.

        paquetes = list(paquetes_individuales)
        for serie_code, miembros in series_paquetes.items():
            for sub_idx, mp in enumerate(miembros, 1):
                mp['sub_numero'] = sub_idx
                mp['grupo_serie'] = serie_code
            paquetes.append({
                'cod_cable': 'GRUPO_SERIE',
                'elemento': serie_code,
                'descripcion': f'Grupo serie {serie_code}',
                'seccion': miembros[0]['seccion'] if miembros else '',
                'longitud': 0.0,
                'cables': [],
                'num_cables': sum(m['num_cables'] for m in miembros),
                'num_terminales': sum(m['num_terminales'] for m in miembros),
                'cables_doble_terminal': [c for m in miembros for c in m.get('cables_doble_terminal', [])],
                'cables_de_terminal':    [c for m in miembros for c in m.get('cables_de_terminal', [])],
                'cables_para_terminal':  [c for m in miembros for c in m.get('cables_para_terminal', [])],
                'es_grupo': True,
                'grupo_serie': serie_code,
                'sub_paquetes': miembros
            })
        
        # -------------------------------------------------------
        # Bloqueo concurrente: verificar y, opcionalmente, crear sesión
        # -------------------------------------------------------
        iniciar_sesion = request.args.get('iniciar_sesion', '').lower() in ('1', 'true')
        sesion_id_param = request.args.get('sesion_id', '').strip() or None

        sesion_repo = SesionTrabajoRepository(db)
        sesion_id_nuevo = None

        if iniciar_sesion and maquina:
            # Crear sesión con lista vacía: los paquetes se actualizarán desde el frontend
            # de 5 en 5 (página a página), para no bloquear paquetes que aún no están
            # en pantalla del operario.
            sesion_id_nuevo = sesion_repo.crear_sesion(
                maquina_id=maquina,
                terminal_codigo=terminal,
                archivo_excel=archivo,
                carro_numero=request.args.get('carro', ''),
                paquetes=[]
            )
            # Verificar qué paquetes están reclamados por OTRAS sesiones
            bloqueos = sesion_repo.verificar_bloqueos(paquetes, sesion_id_excluir=sesion_id_nuevo)
        else:
            # Solo consulta (preview de carros, sin crear sesión)
            excluir = sesion_id_param
            bloqueos = sesion_repo.verificar_bloqueos(paquetes, sesion_id_excluir=excluir)

        # Anotar en cada paquete si está bloqueado y por qué máquina
        paquetes_bloqueados_count = 0
        for paquete in paquetes:
            if paquete.get('es_grupo'):
                # Paquete virtual de serie: verificar sub_paquetes individuales
                sub_bloqueados = 0
                for sub in paquete.get('sub_paquetes', []):
                    clave = (sub['cod_cable'], sub['elemento'])
                    info_bloqueo = bloqueos.get(clave)
                    if info_bloqueo:
                        sub['bloqueado'] = True
                        sub['bloqueado_por'] = info_bloqueo['maquina_nombre']
                        sub['bloqueado_terminal'] = info_bloqueo['terminal_codigo']
                        sub_bloqueados += 1
                    else:
                        sub['bloqueado'] = False
                        sub['bloqueado_por'] = None
                        sub['bloqueado_terminal'] = None
                paquete['bloqueado'] = sub_bloqueados > 0
                paquete['bloqueado_por'] = None
                paquete['bloqueado_terminal'] = None
                if sub_bloqueados > 0:
                    paquetes_bloqueados_count += 1
            else:
                clave = (paquete['cod_cable'], paquete['elemento'])
                info_bloqueo = bloqueos.get(clave)
                if info_bloqueo:
                    paquete['bloqueado'] = True
                    paquete['bloqueado_por'] = info_bloqueo['maquina_nombre']
                    paquete['bloqueado_terminal'] = info_bloqueo['terminal_codigo']
                    paquetes_bloqueados_count += 1
                else:
                    paquete['bloqueado'] = False
                    paquete['bloqueado_por'] = None
                    paquete['bloqueado_terminal'] = None

        respuesta = {
            'success': True,
            'paquetes': paquetes,
            'total_terminales': total_terminales,
            'grupos': list(grupos.values()),
            'terminal': terminal,
            'archivo': archivo,
            'paquetes_bloqueados': paquetes_bloqueados_count,
            'paquetes_libres': len(paquetes) - paquetes_bloqueados_count
        }
        if sesion_id_nuevo:
            respuesta['sesion_id'] = sesion_id_nuevo

        return jsonify(respuesta)

    except Exception as e:
        return error_interno(e, 'Error al obtener datos')


# ==================== SESIONES DE TRABAJO (BLOQUEO CONCURRENTE) ====================

@bp.route('/api/sesion/liberar', methods=['POST'])
def api_liberar_sesion():
    """
    Libera una sesión de trabajo activa (todos sus paquetes quedan libres).
    Llamado cuando el operario termina el terminal o navega fuera.
    """
    try:
        data = request.get_json() or {}
        sesion_id = data.get('sesion_id', '').strip()

        if not sesion_id:
            return jsonify({'success': False, 'message': 'sesion_id es obligatorio'}), 400

        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.liberar_sesion(sesion_id)
        return jsonify({'success': True})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/liberar-paquete', methods=['POST'])
def api_liberar_paquete_sesion():
    """
    Libera un paquete concreto de una sesión (el operario lo saltó).
    Si la sesión queda sin paquetes, se libera por completo.
    """
    try:
        data = request.get_json() or {}
        sesion_id = data.get('sesion_id', '').strip()
        cod_cable = data.get('cod_cable', '').strip()
        elemento = data.get('elemento', '').strip()

        if not sesion_id or not elemento:
            return jsonify({'success': False, 'message': 'sesion_id y elemento son obligatorios'}), 400

        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.liberar_paquete_de_sesion(sesion_id, cod_cable, elemento)
        return jsonify({'success': True})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/actualizar-paquetes', methods=['PUT'])
def api_actualizar_paquetes_sesion():
    """
    Reemplaza los paquetes de una sesión activa con el lote actual visible en pantalla.
    El frontend llama a este endpoint cada vez que muestra una nueva página de paquetes,
    de modo que la sesión solo bloquea los paquetes que el operario tiene en ese momento.
    """
    try:
        data = request.get_json() or {}
        sesion_id = data.get('sesion_id', '').strip()
        paquetes = data.get('paquetes', [])

        if not sesion_id:
            return jsonify({'success': False, 'message': 'sesion_id es obligatorio'}), 400

        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.actualizar_paquetes_sesion(sesion_id, paquetes)
        return jsonify({'success': True})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/verificar-pendientes', methods=['POST'])
def api_verificar_pendientes():
    """
    Comprueba qué paquetes de una lista están bloqueados por otras sesiones activas.

    Body JSON:
      { "paquetes": [{"cod_cable": "X", "elemento": "Y"}, ...],
        "sesion_id_excluir": "<uuid>"  (opcional, para no contarse a uno mismo) }

    Responde con:
      - bloqueados: paquetes todavía en uso por otra sesión
      - libres:     paquetes disponibles ahora
      - total:      número total consultado
    """
    try:
        data = request.get_json() or {}
        paquetes = data.get('paquetes', [])
        sesion_id_excluir = data.get('sesion_id_excluir', '').strip() or None

        if not paquetes:
            return jsonify({'success': True, 'bloqueados': [], 'libres': [], 'total': 0})

        sesion_repo = SesionTrabajoRepository(db)
        bloqueos = sesion_repo.verificar_bloqueos(paquetes, sesion_id_excluir=sesion_id_excluir)

        bloqueados = []
        libres = []
        for p in paquetes:
            clave = (p.get('cod_cable', ''), p.get('elemento', ''))
            if clave in bloqueos:
                info = bloqueos[clave]
                bloqueados.append({**p,
                    'bloqueado_por': info.get('maquina_nombre') or info.get('maquina_id', ''),
                    'bloqueado_terminal': info.get('terminal_codigo', '')
                })
            else:
                libres.append(p)

        return jsonify({
            'success': True,
            'total': len(paquetes),
            'bloqueados': bloqueados,
            'libres': libres,
            'num_bloqueados': len(bloqueados),
            'num_libres': len(libres)
        })

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/sesiones-activas', methods=['GET'])
@requiere_pin_admin
def api_sesiones_activas():
    """
    Devuelve las sesiones activas con info del bono al que pertenecen.
    Parámetro opcional: ?bono=nombre_bono para filtrar por bono.
    """
    try:
        filtro_bono = request.args.get('bono', '').strip() or None

        sesion_repo = SesionTrabajoRepository(db)
        # Extender la consulta para incluir bono a través de carro
        query = """
            SELECT st.id, st.maquina_id, st.terminal_codigo,
                   st.archivo_excel, st.carro_numero,
                   st.timestamp_inicio, st.paquetes_json,
                   m.nombre AS maquina_nombre,
                   b.nombre AS bono_nombre
            FROM sesiones_trabajo st
            LEFT JOIN maquinas m ON st.maquina_id = m.id
            LEFT JOIN carros c ON CAST(c.numero AS TEXT) = st.carro_numero
            LEFT JOIN bonos b ON b.id = c.bono_id
            WHERE st.activo = 1
        """
        params = {}
        if filtro_bono:
            query += " AND b.nombre = :bono"
            params['bono'] = filtro_bono
        query += " ORDER BY st.timestamp_inicio DESC"

        sesiones = sesion_repo.execute_select(query, params)
        result = []
        for s in sesiones:
            try:
                paquetes = json.loads(s['paquetes_json'] or '[]')
            except Exception:
                paquetes = []
            result.append({
                'id': s['id'],
                'maquina_nombre': s.get('maquina_nombre') or s['maquina_id'],
                'terminal_codigo': s['terminal_codigo'],
                'carro_numero': s['carro_numero'],
                'bono_nombre': s.get('bono_nombre') or '—',
                'timestamp_inicio': s['timestamp_inicio'],
                'num_paquetes': len(paquetes),
                'paquetes': paquetes
            })
        return jsonify({'success': True, 'sesiones': result, 'total': len(result)})
    except Exception as e:
        return error_interno(e)



@bp.route('/api/sesion/liberar-sesion/<sesion_id>', methods=['POST'])
@requiere_pin_admin
def api_liberar_sesion_admin(sesion_id):
    """Libera una sesión concreta por su ID."""
    try:
        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.liberar_sesion(sesion_id)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/limpiar-sesiones-fantasma', methods=['POST'])
@requiere_pin_admin
def api_limpiar_sesiones_fantasma():
    """Libera TODAS las sesiones activas de golpe."""
    try:
        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.execute_query(
            "UPDATE sesiones_trabajo SET activo = 0 WHERE activo = 1", {}
        )
        return jsonify({'success': True, 'message': 'Todos los bloqueos liberados'})
    except Exception as e:
        return error_interno(e)
