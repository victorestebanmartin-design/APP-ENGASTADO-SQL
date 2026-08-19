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
from app.excel_manager import ExcelManager, leer_excel_cacheado
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

# La pantalla del carro tiene 8 pulsadores: del 1 al 7 identifican un puesto
# (el operario pulsa el suyo al llegar) y el 8 es el de OK/confirmación.
BOTONES_PUESTO_MAX = 7


# ==================== IDENTIDAD DEL PC (modulo + puesto) ====================
#
# Cada PC de planta esta dedicado a UN modulo. El modulo es una propiedad del
# EQUIPO, no un puesto de la BD:
#
#   - engastado -> ademas necesita saber QUE puesto es (MANUAL, PINES RACK,
#     PUNTERAS...), porque el trabajo de engastado se organiza por puestos.
#   - mangueras / manguitos -> NO tienen puestos. El PC entra directo al
#     modulo; no hay nada que elegir ni que dar de alta en Gestion de Puestos.
#
# La identidad se recuerda de dos formas complementarias:
#   1. Por IP (tabla pc_equipos): la red de planta tiene IPs fijas, sin DHCP,
#      asi que la IP es la identidad mas fiable -- sobrevive a borrar la cache
#      del navegador y a cambiar de navegador. Se anota sola al configurar.
#   2. Por cookie de 10 anios (metodo anterior): sigue funcionando como
#      respaldo si el PC cambia de IP o se accede desde fuera de la red.

COOKIE_PUESTO_PC = 'puesto_pc_id'
COOKIE_PC_MODULO = 'pc_modulo'
COOKIE_PUESTO_PC_MAX_AGE = 315360000  # ~10 anios

# Modulos a los que se puede dedicar un PC.
MODULOS_PC = ('engastado', 'mangueras', 'manguitos')
# De esos, los que NO llevan puesto asociado (entran directos al modulo).
MODULOS_SIN_PUESTO = ('mangueras', 'manguitos')
# Como se llaman de cara al operario (pantallas de login y de configuracion).
MODULOS_APP_LABEL = {
    'engastado': 'Engastado',
    'mangueras': 'Preparación de Mangueras',
    'manguitos': 'Colocación de Manguitos',
}


def _ip_cliente():
    """IP real del cliente considerando cabeceras de proxy."""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return (request.remote_addr or '').strip()


def _pc_equipo_por_ip(ip):
    """Fila de pc_equipos para esa IP, o None."""
    if not ip:
        return None
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT modulo, puesto_id FROM pc_equipos WHERE ip = :ip"
            ), {'ip': ip}).fetchone()
        return {'modulo': row[0], 'puesto_id': row[1]} if row else None
    except Exception:
        return None


def _pc_equipo_guardar(ip, modulo, puesto_id=None):
    """Anota (o actualiza) la identidad de este PC para su IP fija."""
    if not ip:
        return
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO pc_equipos (ip, modulo, puesto_id, updated_at)
                VALUES (:ip, :m, :p, datetime('now'))
                ON CONFLICT(ip) DO UPDATE
                    SET modulo     = excluded.modulo,
                        puesto_id  = excluded.puesto_id,
                        updated_at = excluded.updated_at
            """), {'ip': ip, 'm': modulo, 'p': puesto_id})
            conn.commit()
    except Exception:
        current_app.logger.exception('No se pudo anotar la identidad del PC por IP')


def _pc_identidad():
    """(modulo, puesto_id, puesto_nombre) de ESTE equipo.

    modulo es None si el PC todavia no esta configurado. puesto_id/nombre solo
    tienen valor en engastado; en mangueras y manguitos son None a proposito
    (esos modulos no tienen puestos).

    Prioridad: IP fija del puesto (override manual del admin) -> pc_equipos
    (anotado al configurar el PC) -> cookies.
    """
    repo = PuestoRepository(db)
    ip = _ip_cliente()

    # 1. IP fija asignada a mano a un puesto desde Gestion de Puestos.
    if ip:
        puesto = repo.obtener_puesto_por_ip(ip)
        if puesto:
            return 'engastado', puesto['id'], puesto['nombre']

    # 2. Identidad anotada por IP al configurar el equipo.
    equipo = _pc_equipo_por_ip(ip)
    if equipo:
        modulo = equipo['modulo']
        if modulo in MODULOS_SIN_PUESTO:
            return modulo, None, None
        puesto = repo.obtener_puesto(equipo['puesto_id']) if equipo['puesto_id'] else None
        if puesto:
            return 'engastado', puesto['id'], puesto['nombre']

    # 3. Cookies. El modulo puede estar sin puesto (mangueras/manguitos); si es
    #    engastado hace falta ademas un puesto valido.
    modulo_cookie = (request.cookies.get(COOKIE_PC_MODULO) or '').strip().lower()
    if modulo_cookie in MODULOS_SIN_PUESTO:
        return modulo_cookie, None, None

    puesto_id = (request.cookies.get(COOKIE_PUESTO_PC) or '').strip()
    if puesto_id:
        puesto = repo.obtener_puesto(puesto_id)
        if puesto:
            return 'engastado', puesto_id, puesto['nombre']

    return None, None, None


def _puesto_pc_actual():
    """(puesto_id, nombre) del puesto de engastado de este PC, o (None, None).

    Se conserva porque lo usan las rutas y APIs que solo entienden de puestos
    (engastado). Para saber a que modulo esta dedicado el equipo, usar
    _pc_identidad().
    """
    _, puesto_id, nombre = _pc_identidad()
    return puesto_id, nombre


def _destino_modulo(modulo):
    """Ruta a la que entra directamente un PC dedicado a ese modulo."""
    return {
        'mangueras': '/mangueras',
        'manguitos': '/manguitos',
    }.get(modulo, '/modules')


@bp.route('/api/pc', methods=['GET'])
def api_pc_get():
    """Identidad de ESTE equipo: modulo + (si es engastado) su puesto."""
    modulo, puesto_id, nombre = _pc_identidad()
    return jsonify({
        'success': True,
        'modulo': modulo,
        'puesto_id': puesto_id,
        'puesto_nombre': nombre,
        'configurado': bool(modulo),
        'destino': _destino_modulo(modulo) if modulo else None,
    })


@bp.route('/api/pc/configurar', methods=['POST'])
def api_pc_configurar():
    """Fija a que modulo (y puesto, si es engastado) esta dedicado este PC.

    La primera vez es autoservicio, sin PIN: es la configuracion de un equipo
    recien instalado. Reconfigurar un PC que YA tenia identidad es una accion
    de infraestructura y exige la misma sesion de admin que el resto del panel.
    """
    try:
        data = request.get_json(silent=True) or {}
        modulo = (data.get('modulo') or '').strip().lower()
        if modulo not in MODULOS_PC:
            return jsonify({'success': False,
                            'error': f'Módulo no válido (usa: {", ".join(MODULOS_PC)})'}), 400

        # Reconfiguracion: exige PIN si la proteccion esta activa.
        modulo_actual, _, _ = _pc_identidad()
        if modulo_actual and proteccion_activa() and not sesion_admin_valida():
            return jsonify({'success': False,
                            'error': 'Este equipo ya está configurado. '
                                     'Hace falta el PIN de administración para cambiarlo.'}), 401

        puesto_id, puesto_nombre = None, None
        if modulo == 'engastado':
            puesto_id = (data.get('puesto_id') or '').strip()
            if not puesto_id:
                return jsonify({'success': False,
                                'error': 'Un PC de engastado necesita un puesto'}), 400
            puesto = PuestoRepository(db).obtener_puesto(puesto_id)
            if not puesto:
                return jsonify({'success': False, 'error': 'Puesto no encontrado'}), 404
            puesto_nombre = puesto['nombre']

        # Anotar por IP (identidad principal en la red de planta, sin DHCP)
        _pc_equipo_guardar(_ip_cliente(), modulo, puesto_id)

        resp = jsonify({
            'success': True,
            'modulo': modulo,
            'puesto_id': puesto_id,
            'puesto_nombre': puesto_nombre,
            'destino': _destino_modulo(modulo),
        })
        resp.set_cookie(COOKIE_PC_MODULO, modulo, max_age=COOKIE_PUESTO_PC_MAX_AGE,
                        httponly=True, samesite='Lax')
        if puesto_id:
            resp.set_cookie(COOKIE_PUESTO_PC, puesto_id, max_age=COOKIE_PUESTO_PC_MAX_AGE,
                            httponly=True, samesite='Lax')
        else:
            # Mangueras/manguitos no tienen puesto: limpiar el que hubiera.
            resp.set_cookie(COOKIE_PUESTO_PC, '', max_age=0, expires=0,
                            httponly=True, samesite='Lax')
        return resp
    except Exception as e:
        return error_interno(e)


@bp.route('/api/puesto/pc', methods=['GET'])
def api_puesto_pc_get():
    """Puesto asignado a este navegador (o null si aun no se ha elegido)."""
    modulo, puesto_id, nombre = _pc_identidad()
    return jsonify({'success': True, 'puesto_id': puesto_id,
                    'puesto_nombre': nombre, 'modulo': modulo})


@bp.route('/api/puesto/pc', methods=['POST'])
def api_puesto_pc_set():
    """Fija el puesto de este PC por primera vez (autoservicio, sin PIN: es
    la configuracion inicial de un equipo recien instalado, no un cambio)."""
    try:
        data = request.get_json(silent=True) or {}
        puesto_id = (data.get('puesto_id') or '').strip()
        if not puesto_id:
            return jsonify({'success': False, 'error': 'puesto_id es obligatorio'}), 400
        puesto = PuestoRepository(db).obtener_puesto(puesto_id)
        if not puesto:
            return jsonify({'success': False, 'error': 'Puesto no encontrado'}), 404
        _pc_equipo_guardar(_ip_cliente(), 'engastado', puesto_id)
        resp = jsonify({'success': True, 'puesto_id': puesto_id, 'puesto_nombre': puesto['nombre']})
        resp.set_cookie(COOKIE_PUESTO_PC, puesto_id, max_age=COOKIE_PUESTO_PC_MAX_AGE,
                        httponly=True, samesite='Lax')
        resp.set_cookie(COOKIE_PC_MODULO, 'engastado', max_age=COOKIE_PUESTO_PC_MAX_AGE,
                        httponly=True, samesite='Lax')
        return resp
    except Exception as e:
        return error_interno(e)


@bp.route('/api/puesto/pc/reasignar', methods=['POST'])
@requiere_pin_admin
def api_puesto_pc_reasignar():
    """Cambia el puesto de un PC que ya tenia uno asignado. Protegido por PIN:
    a diferencia de la configuracion inicial, reasignar es una accion de
    infraestructura que no deberia hacer cualquiera desde el suelo de planta."""
    try:
        data = request.get_json(silent=True) or {}
        puesto_id = (data.get('puesto_id') or '').strip()
        if not puesto_id:
            return jsonify({'success': False, 'error': 'puesto_id es obligatorio'}), 400
        puesto = PuestoRepository(db).obtener_puesto(puesto_id)
        if not puesto:
            return jsonify({'success': False, 'error': 'Puesto no encontrado'}), 404
        _pc_equipo_guardar(_ip_cliente(), 'engastado', puesto_id)
        resp = jsonify({'success': True, 'puesto_id': puesto_id, 'puesto_nombre': puesto['nombre']})
        resp.set_cookie(COOKIE_PUESTO_PC, puesto_id, max_age=COOKIE_PUESTO_PC_MAX_AGE,
                        httponly=True, samesite='Lax')
        resp.set_cookie(COOKIE_PC_MODULO, 'engastado', max_age=COOKIE_PUESTO_PC_MAX_AGE,
                        httponly=True, samesite='Lax')
        return resp
    except Exception as e:
        return error_interno(e)


@bp.route('/api/puesto/pc/liberar', methods=['POST'])
@requiere_pin_admin
def api_puesto_pc_liberar():
    """Libera la identidad de ESTE equipo: cookies y anotación por IP.

    Útil para reasignar rápidamente el equipo sin esperar a caducidades.
    Además cierra la sesión de operario local para evitar que el gate de
    login adopte una identidad antigua tras cambiar de puesto.
    """
    try:
        login_id = session.get('operario_login_id')
        with db.engine.connect() as conn:
            if login_id:
                conn.execute(text("UPDATE operario_logins SET activo=0 WHERE id=:id"), {'id': login_id})
            # Sin esto el PC se re-identificaria solo por su IP fija y la
            # liberacion no serviria de nada en la red de planta.
            conn.execute(text("DELETE FROM pc_equipos WHERE ip = :ip"), {'ip': _ip_cliente()})
            conn.commit()

        session.pop('operario_actual', None)
        session.pop('operario_login_id', None)

        resp = jsonify({'success': True, 'message': 'Identidad del PC liberada'})
        resp.set_cookie(COOKIE_PUESTO_PC, '', max_age=0, expires=0,
                        httponly=True, samesite='Lax')
        resp.set_cookie(COOKIE_PC_MODULO, '', max_age=0, expires=0,
                        httponly=True, samesite='Lax')
        return resp
    except Exception as e:
        return error_interno(e)


def normalizar_tag_uid(crudo):
    """Deja un UID de tarjeta NFC en forma canónica: hex en mayúsculas y sin
    separadores. Devuelve '' si viene vacío, o None si no es un UID válido.

    Los UID de las tarjetas van de 4 bytes (MIFARE Classic) a 10 (algunas
    NTAG), y los lectores los escriben de mil formas: 'a1:b2:c3:d4',
    'A1 B2 C3 D4', 'a1b2c3d4'. Todas acaban igual aquí.
    """
    uid = re.sub(r'[\s:.-]', '', str(crudo or '')).upper()
    if not uid:
        return ''
    if not re.fullmatch(r'[0-9A-F]{8,20}', uid) or len(uid) % 2:
        return None
    return uid

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
        # Los puestos son siempre de engastado: mangueras y manguitos no
        # tienen puestos, se asignan al PC entero (ver _pc_identidad).
        ip_fija = (data.get('ip_fija') or '').strip() or None

        if not nombre:
            return jsonify({'success': False, 'message': 'El nombre del puesto es obligatorio'}), 400

        # Validar IP si se proporcionó
        if ip_fija:
            import ipaddress
            try:
                ipaddress.ip_address(ip_fija)
            except ValueError:
                return jsonify({'success': False, 'message': 'IP no válida'}), 400

        puesto_repo = PuestoRepository(db)

        # Comprobar IP no duplicada
        if ip_fija:
            existente = puesto_repo.obtener_puesto_por_ip(ip_fija)
            if existente:
                return jsonify({'success': False,
                                'message': f'La IP {ip_fija} ya está asignada al puesto "{existente["nombre"]}"'}), 409

        puestos_existentes = puesto_repo.obtener_todos_puestos(solo_activos=False)

        import random
        new_id = f"puesto_{len(puestos_existentes) + 1:03d}"
        while any(p['id'] == new_id for p in puestos_existentes):
            new_id = f"puesto_{len(puestos_existentes) + 1:03d}_{random.randint(100, 999)}"

        if puesto_repo.crear_puesto(new_id, nombre, descripcion, modulo='engastado', ip_fija=ip_fija):
            nuevo_puesto = puesto_repo.obtener_puesto(new_id)
            return jsonify({'success': True, 'puesto': nuevo_puesto})
        else:
            return jsonify({'success': False, 'message': 'Error al crear el puesto'}), 500

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

        # Botón de la pantalla del carro: 1-7, o null/'' para quitarlo
        boton, limpiar_boton = None, False
        if 'boton' in data:
            crudo = data.get('boton')
            if crudo in (None, '', 0):
                limpiar_boton = True
            else:
                try:
                    boton = int(crudo)
                except (TypeError, ValueError):
                    return jsonify({'success': False,
                                    'message': 'El botón debe ser un número del 1 al 7'}), 400
                if not 1 <= boton <= BOTONES_PUESTO_MAX:
                    return jsonify({'success': False,
                                    'message': f'El botón debe estar entre 1 y {BOTONES_PUESTO_MAX} '
                                               f'(el 8 es el de OK/confirmación)'}), 400
                # Un botón solo puede estar en un puesto: avisar con nombre
                ocupado = puesto_repo.obtener_puesto_por_boton(boton)
                if ocupado and ocupado['id'] != puesto_id:
                    return jsonify({'success': False,
                                    'message': f'El botón {boton} ya está asignado al puesto '
                                               f'"{ocupado["nombre"]}"'}), 409

        # IP fija: dirección IP estática o '' para limpiar
        ip_fija, limpiar_ip = None, False
        if 'ip_fija' in data:
            crudo_ip = (data.get('ip_fija') or '').strip()
            if not crudo_ip:
                limpiar_ip = True
            else:
                import ipaddress
                try:
                    ipaddress.ip_address(crudo_ip)
                    ip_fija = crudo_ip
                except ValueError:
                    return jsonify({'success': False, 'message': 'IP no válida'}), 400
                # Comprobar que no la use otro puesto
                otro = puesto_repo.obtener_puesto_por_ip(ip_fija)
                if otro and otro['id'] != puesto_id:
                    return jsonify({'success': False,
                                    'message': f'La IP {ip_fija} ya está asignada al puesto '
                                               f'"{otro["nombre"]}"'}), 409

        if puesto_repo.actualizar_puesto(puesto_id, nombre, descripcion,
                                         boton=boton, limpiar_boton=limpiar_boton,
                                         ip_fija=ip_fija, limpiar_ip=limpiar_ip):
            puesto_actualizado = puesto_repo.obtener_puesto(puesto_id)
            return jsonify({'success': True, 'puesto': puesto_actualizado})
        else:
            return jsonify({'success': False, 'message': 'No se realizaron cambios'}), 400
            
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
@requiere_pin_admin
def api_crear_maquina():
    """Crear nueva máquina"""
    try:
        data = request.get_json()
        
        puesto_id = data.get('puesto_id', '').strip()
        nombre = data.get('nombre', '').strip()
        modelo = data.get('modelo', '').strip()
        descripcion = data.get('descripcion', '').strip()
        tipo_operacion = data.get('tipo_operacion', 'MANUAL').strip().upper()
        if tipo_operacion not in ('MANUAL', 'AUTOMATICA', 'SEMI-AUTOMATICA'):
            tipo_operacion = 'MANUAL'
        
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
        if maquina_repo.crear_maquina(new_id, puesto_id, nombre, modelo, descripcion, tipo_operacion):
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
@requiere_pin_admin
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
        puesto_id = data.get('puesto_id')
        tipo_operacion = data.get('tipo_operacion')
        if tipo_operacion:
            tipo_operacion = tipo_operacion.strip().upper()
            if tipo_operacion not in ('MANUAL', 'AUTOMATICA', 'SEMI-AUTOMATICA'):
                tipo_operacion = None
        lleva_regulacion = data.get('lleva_regulacion')
        if lleva_regulacion is not None:
            lleva_regulacion = bool(lleva_regulacion)
        
        if maquina_repo.actualizar_maquina(maquina_id, nombre, modelo, descripcion, puesto_id, tipo_operacion,
                                           lleva_regulacion=lleva_regulacion):
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
@requiere_pin_admin
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


@bp.route('/api/maquinas/<maquina_id>/pdf', methods=['POST'])
@requiere_pin_admin
def api_subir_pdf_maquina(maquina_id):
    """Subir o reemplazar el PDF de instrucciones de una máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404

        if 'pdf' not in request.files:
            return jsonify({'success': False, 'message': 'No se envió ningún archivo'}), 400

        archivo = request.files['pdf']
        if not archivo.filename:
            return jsonify({'success': False, 'message': 'Nombre de archivo vacío'}), 400

        nombre_seguro = secure_filename(archivo.filename)
        if not nombre_seguro.lower().endswith('.pdf'):
            return jsonify({'success': False, 'message': 'Solo se aceptan archivos PDF'}), 400

        pdf_folder = current_app.config['MAQUINAS_PDF_FOLDER']
        os.makedirs(pdf_folder, exist_ok=True)

        # Eliminar PDF anterior si existe
        if maquina.get('pdf_instrucciones'):
            pdf_anterior = os.path.join(pdf_folder, maquina['pdf_instrucciones'])
            if os.path.exists(pdf_anterior):
                os.remove(pdf_anterior)

        # Nombre único: maquina_id + nombre original
        nombre_final = f"{maquina_id}_{nombre_seguro}"
        ruta_destino = os.path.join(pdf_folder, nombre_final)
        archivo.save(ruta_destino)

        maquina_repo.actualizar_maquina(maquina_id, pdf_instrucciones=nombre_final)

        return jsonify({'success': True, 'pdf_instrucciones': nombre_final})

    except Exception as e:
        return error_interno(e, 'Error al subir PDF de máquina')


@bp.route('/api/maquinas/<maquina_id>/pdf', methods=['GET'])
def api_obtener_pdf_maquina(maquina_id):
    """Descargar / visualizar el PDF de instrucciones de una máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404

        nombre_pdf = maquina.get('pdf_instrucciones')
        if not nombre_pdf:
            return jsonify({'success': False, 'message': 'Esta máquina no tiene PDF adjunto'}), 404

        pdf_folder = current_app.config['MAQUINAS_PDF_FOLDER']
        ruta_pdf = os.path.join(pdf_folder, nombre_pdf)

        if not os.path.exists(ruta_pdf):
            return jsonify({'success': False, 'message': 'Archivo PDF no encontrado en disco'}), 404

        return send_file(
            ruta_pdf,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=nombre_pdf
        )

    except Exception as e:
        return error_interno(e, 'Error al obtener PDF de máquina')


@bp.route('/api/maquinas/<maquina_id>/pdf', methods=['DELETE'])
@requiere_pin_admin
def api_eliminar_pdf_maquina(maquina_id):
    """Eliminar el PDF de instrucciones de una máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404

        nombre_pdf = maquina.get('pdf_instrucciones')
        if not nombre_pdf:
            return jsonify({'success': False, 'message': 'No hay PDF que eliminar'}), 404

        pdf_folder = current_app.config['MAQUINAS_PDF_FOLDER']
        ruta_pdf = os.path.join(pdf_folder, nombre_pdf)
        if os.path.exists(ruta_pdf):
            os.remove(ruta_pdf)

        maquina_repo.actualizar_maquina(maquina_id, limpiar_pdf=True)

        return jsonify({'success': True, 'message': 'PDF eliminado correctamente'})

    except Exception as e:
        return error_interno(e, 'Error al eliminar PDF de máquina')


@bp.route('/api/maquinas/<maquina_id>/pdf-regulacion', methods=['POST'])
@requiere_pin_admin
def api_subir_pdf_regulacion(maquina_id):
    """Subir o reemplazar el PDF de regulación de una máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404

        if 'pdf' not in request.files:
            return jsonify({'success': False, 'message': 'No se envió ningún archivo'}), 400

        archivo = request.files['pdf']
        if not archivo.filename:
            return jsonify({'success': False, 'message': 'Nombre de archivo vacío'}), 400

        nombre_seguro = secure_filename(archivo.filename)
        if not nombre_seguro.lower().endswith('.pdf'):
            return jsonify({'success': False, 'message': 'Solo se aceptan archivos PDF'}), 400

        pdf_folder = current_app.config['MAQUINAS_PDF_FOLDER']
        os.makedirs(pdf_folder, exist_ok=True)

        if maquina.get('pdf_regulacion'):
            pdf_anterior = os.path.join(pdf_folder, maquina['pdf_regulacion'])
            if os.path.exists(pdf_anterior):
                os.remove(pdf_anterior)

        nombre_final = f"reg_{maquina_id}_{nombre_seguro}"
        ruta_destino = os.path.join(pdf_folder, nombre_final)
        archivo.save(ruta_destino)

        maquina_repo.actualizar_maquina(maquina_id, pdf_regulacion=nombre_final)
        return jsonify({'success': True, 'pdf_regulacion': nombre_final})

    except Exception as e:
        return error_interno(e, 'Error al subir PDF de regulación')


@bp.route('/api/maquinas/<maquina_id>/pdf-regulacion', methods=['GET'])
def api_obtener_pdf_regulacion(maquina_id):
    """Descargar / visualizar el PDF de regulación de una máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404

        nombre_pdf = maquina.get('pdf_regulacion')
        if not nombre_pdf:
            return jsonify({'success': False, 'message': 'Esta máquina no tiene PDF de regulación'}), 404

        pdf_folder = current_app.config['MAQUINAS_PDF_FOLDER']
        ruta_pdf = os.path.join(pdf_folder, nombre_pdf)
        if not os.path.exists(ruta_pdf):
            return jsonify({'success': False, 'message': 'Archivo PDF no encontrado en disco'}), 404

        return send_file(ruta_pdf, mimetype='application/pdf', as_attachment=False, download_name=nombre_pdf)

    except Exception as e:
        return error_interno(e, 'Error al obtener PDF de regulación')


@bp.route('/api/maquinas/<maquina_id>/pdf-regulacion', methods=['DELETE'])
@requiere_pin_admin
def api_eliminar_pdf_regulacion(maquina_id):
    """Eliminar el PDF de regulación de una máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404

        nombre_pdf = maquina.get('pdf_regulacion')
        if not nombre_pdf:
            return jsonify({'success': False, 'message': 'No hay PDF de regulación que eliminar'}), 404

        pdf_folder = current_app.config['MAQUINAS_PDF_FOLDER']
        ruta_pdf = os.path.join(pdf_folder, nombre_pdf)
        if os.path.exists(ruta_pdf):
            os.remove(ruta_pdf)

        maquina_repo.actualizar_maquina(maquina_id, limpiar_pdf_regulacion=True)
        return jsonify({'success': True, 'message': 'PDF de regulación eliminado correctamente'})

    except Exception as e:
        return error_interno(e, 'Error al eliminar PDF de regulación')


@bp.route('/api/estadisticas-tipo-operacion', methods=['GET'])
def api_estadisticas_tipo_operacion():
    """Estadísticas de tipo de operación por archivo Excel / corte de cable"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()

        maquina_repo = MaquinaRepository(db)
        maquinas = maquina_repo.obtener_todas_maquinas()

        # Construir mapa terminal_codigo → tipo_operacion
        terminal_tipo = {}
        for maquina in maquinas:
            tipo = maquina.get('tipo_operacion') or 'MANUAL'
            for terminal in maquina_repo.obtener_terminales_asignados(maquina['id']):
                terminal_tipo[terminal] = tipo

        upload_folder = current_app.config['UPLOAD_FOLDER']
        por_archivo = []
        g = {'MANUAL': 0, 'AUTOMATICA': 0, 'SEMI-AUTOMATICA': 0, 'sin_asignar': 0, 'total': 0}

        for codigo in codigos:
            archivo = codigo['archivo_excel']
            filepath = os.path.join(upload_folder, archivo)
            if not os.path.exists(filepath):
                continue
            try:
                df = leer_excel_cacheado(filepath)
                terminales_archivo = set()
                for col in df.columns:
                    if 'terminal' in str(col).lower():
                        for t in df[col].dropna().unique():
                            t = str(t).strip()
                            if t and not t.endswith('*'):
                                terminales_archivo.add(t)

                stats = {'MANUAL': 0, 'AUTOMATICA': 0, 'SEMI-AUTOMATICA': 0, 'sin_asignar': 0}
                for t in terminales_archivo:
                    tipo = terminal_tipo.get(t)
                    if tipo:
                        stats[tipo] = stats.get(tipo, 0) + 1
                    else:
                        stats['sin_asignar'] += 1

                total = len(terminales_archivo)
                for k in stats:
                    g[k] = g.get(k, 0) + stats[k]
                g['total'] += total

                nombre = os.path.splitext(archivo)[0]

                por_archivo.append({
                    'archivo': archivo,
                    'nombre': nombre,
                    'codigo': codigo.get('codigo', nombre),
                    'total': total,
                    'manual': stats['MANUAL'],
                    'semi': stats['SEMI-AUTOMATICA'],
                    'automatica': stats['AUTOMATICA'],
                    'sin_asignar': stats['sin_asignar'],
                })
            except Exception:
                pass

        por_archivo.sort(key=lambda x: x['archivo'])

        return jsonify({
            'success': True,
            'por_archivo': por_archivo,
            'global': g
        })
    except Exception as e:
        return error_interno(e, 'Error al calcular estadísticas de tipo de operación')


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
                    df = leer_excel_cacheado(filepath)
                    
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
                    current_app.logger.warning(f"Error leyendo terminales de {archivo}: {e}")
                    errores_lectura.append({
                        'archivo': archivo,
                        'error': 'Error al leer el archivo'
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

        # Cargar terminales ignorados
        rows_ign = db.session.execute(
            text("SELECT terminal_codigo FROM terminales_ignorados")
        ).fetchall()
        ignorados_set = {r[0] for r in rows_ign}

        # Preparar respuesta con estado de cada terminal
        terminales_con_estado = []
        for terminal in sorted(list(terminales_sistema)):
            estado = {
                'terminal': terminal,
                'asignado': terminal in terminales_asignados,
                'asignacion': terminales_asignados.get(terminal, None),
                'imagen_data': imagenes_map.get(terminal),
                'gaveta': gavetas_map.get(terminal),
                'ignorado': terminal in ignorados_set
            }
            terminales_con_estado.append(estado)

        # Contar terminales sin asignar (excluir ignorados)
        sin_asignar = len([t for t in terminales_con_estado if not t['asignado'] and not t['ignorado']])
        
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
@requiere_pin_admin
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
@requiere_pin_admin
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


@bp.route('/api/terminal-ignorar', methods=['POST'])
@requiere_pin_admin
def api_toggle_ignorar_terminal():
    """Activar o desactivar (ignorar) un terminal para que no aparezca en pendientes."""
    try:
        data = request.get_json()
        terminal = (data.get('terminal') or '').strip()
        ignorar = data.get('ignorar', True)

        if not terminal:
            return jsonify({'success': False, 'message': 'Terminal es obligatorio'}), 400

        if ignorar:
            db.session.execute(
                text("INSERT OR IGNORE INTO terminales_ignorados (terminal_codigo) VALUES (:cod)"),
                {'cod': terminal}
            )
        else:
            db.session.execute(
                text("DELETE FROM terminales_ignorados WHERE terminal_codigo = :cod"),
                {'cod': terminal}
            )
        db.session.commit()

        accion = 'ignorado' if ignorar else 'activado'
        return jsonify({'success': True, 'message': f'Terminal {terminal} {accion}', 'ignorado': ignorar})
    except Exception as e:
        return error_interno(e, 'Error al cambiar estado de terminal')


# ==================== IMÁGENES DE TERMINALES ====================

MAX_IMAGEN_BYTES = 420_000  # ~300 KB binario ≈ 420 KB en base64

@bp.route('/api/terminal-imagen/<codigo>', methods=['GET'])
def api_obtener_imagen_terminal(codigo):
    """Obtener la imagen de un terminal (data URL base64)."""
    try:
        row = db.session.execute(
            text("SELECT imagen_data FROM terminales_imagenes WHERE terminal_codigo = :codigo"),
            {'codigo': codigo}
        ).fetchone()
        return jsonify({'success': True, 'imagen_data': row[0] if row else None})
    except Exception as e:
        return error_interno(e, 'Error al obtener imagen de terminal')


@bp.route('/api/terminal-imagen/<codigo>', methods=['PUT'])
@requiere_pin_admin
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
@requiere_pin_admin
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

@bp.route('/api/terminal-gaveta/<codigo>', methods=['GET'])
def api_obtener_gaveta_terminal(codigo):
    """Obtener la gaveta (ubicación física) de un terminal."""
    try:
        row = db.session.execute(
            text("SELECT gaveta FROM terminales_gavetas WHERE terminal_codigo = :codigo"),
            {'codigo': codigo}
        ).fetchone()
        return jsonify({'success': True, 'gaveta': row[0] if row else None})
    except Exception as e:
        return error_interno(e, 'Error al obtener gaveta de terminal')


@bp.route('/api/terminal-gaveta/<codigo>', methods=['PUT'])
@requiere_pin_admin
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
@requiere_pin_admin
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


# ==================== KANBAN DE STOCK ====================

@bp.route('/api/kanban-terminales', methods=['GET'])
def api_kanban_terminales():
    """Devuelve todos los terminales del sistema con: máquina, gaveta, stock, cantidades por archivo y subtotal."""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        upload_folder = current_app.config['UPLOAD_FOLDER']

        terminal_detalle: dict = {}   # {terminal_upper: {nombre_archivo: qty}}
        archivos_ordenados: list = []
        errores: list = []

        def _valido(t):
            return bool(t) and t not in ('NAN', 'S/T', '')

        for codigo in codigos:
            archivo = codigo['archivo_excel']
            filepath = os.path.join(upload_folder, archivo)
            if not os.path.exists(filepath):
                continue
            nombre = os.path.splitext(archivo)[0]
            try:
                df = leer_excel_cacheado(filepath)

                # Detectar columnas de terminal con tolerancia de nombre
                col_de = next((c for c in df.columns if 'de terminal' in str(c).lower()), None)
                col_para = next((c for c in df.columns if 'para terminal' in str(c).lower()), None)
                col_cod = next((c for c in df.columns if 'cod' in str(c).lower() and 'cable' in str(c).lower()), None)
                col_sec = next((c for c in df.columns if 'secci' in str(c).lower() or c.lower() == 'seccion'), None)
                col_de_el = next((c for c in df.columns if 'de elemento' in str(c).lower()), None)
                col_para_el = next((c for c in df.columns if 'para elemento' in str(c).lower()), None)

                if not col_de and not col_para:
                    errores.append({'archivo': archivo, 'motivo': 'sin columnas terminal'})
                    continue

                if nombre not in archivos_ordenados:
                    archivos_ordenados.append(nombre)

                cont: dict = {}
                for _, row in df.iterrows():
                    # Filtrar filas auxiliares
                    if col_cod:
                        cod = str(row.get(col_cod, '')).strip()
                        if not cod or cod.lower() == 'nan':
                            continue
                    if col_sec:
                        sec = str(row.get(col_sec, '')).strip()
                        if not sec or sec.lower() == 'nan':
                            continue

                    de_t   = str(row.get(col_de,   '') if col_de   else '').strip().upper()
                    para_t = str(row.get(col_para, '') if col_para else '').strip().upper()
                    de_np   = str(row.get(col_de_el,   '') if col_de_el   else '').strip().endswith('*')
                    para_np = str(row.get(col_para_el, '') if col_para_el else '').strip().endswith('*')

                    if _valido(de_t) and _valido(para_t) and de_t == para_t:
                        if not (de_np and para_np):
                            cont[de_t] = cont.get(de_t, 0) + (1 if (de_np or para_np) else 2)
                    else:
                        if _valido(de_t) and not de_np:
                            cont[de_t] = cont.get(de_t, 0) + 1
                        if _valido(para_t) and not para_np:
                            cont[para_t] = cont.get(para_t, 0) + 1

                for t, qty in cont.items():
                    if qty > 0:
                        terminal_detalle.setdefault(t, {})[nombre] = qty

            except Exception as exc:
                errores.append({'archivo': archivo, 'motivo': str(exc)})

        maquina_repo = MaquinaRepository(db)
        maquinas = maquina_repo.obtener_todas_maquinas()
        terminal_maquina = {}
        for maq in maquinas:
            for t in maquina_repo.obtener_terminales_asignados(maq['id']):
                terminal_maquina[t] = {
                    'maquina_id':     maq['id'],
                    'maquina_nombre': maq['nombre'],
                    'puesto_nombre':  maq.get('puesto_nombre', ''),
                    'tipo_operacion': maq.get('tipo_operacion', 'MANUAL'),
                }

        rows_gav = db.session.execute(
            text("SELECT terminal_codigo, gaveta FROM terminales_gavetas")
        ).fetchall()
        gavetas_map = {r[0]: r[1] for r in rows_gav}

        rows_stock = db.session.execute(
            text("SELECT terminal_codigo, stock_actual, stock_minimo, notas FROM terminales_stock")
        ).fetchall()
        stock_map = {r[0]: {'stock_actual': r[1], 'stock_minimo': r[2], 'notas': r[3]} for r in rows_stock}

        resultado = []
        for terminal in sorted(terminal_detalle.keys()):
            asig = terminal_maquina.get(terminal)
            st   = stock_map.get(terminal, {'stock_actual': 0, 'stock_minimo': 0, 'notas': None})
            detalle = terminal_detalle[terminal]
            subtotal = sum(detalle.values())
            detalle_lista = [{'nombre': a, 'cantidad': detalle[a]}
                             for a in archivos_ordenados if a in detalle]
            resultado.append({
                'terminal':         terminal,
                'maquina_nombre':   asig['maquina_nombre'] if asig else None,
                'puesto_nombre':    asig['puesto_nombre']  if asig else None,
                'tipo_operacion':   asig['tipo_operacion'] if asig else None,
                'gaveta':           gavetas_map.get(terminal),
                'stock_actual':     st['stock_actual'],
                'stock_minimo':     st['stock_minimo'],
                'notas':            st['notas'],
                'detalle_archivos': detalle_lista,
                'subtotal':         subtotal,
            })

        resp = {
            'success':    True,
            'terminales': resultado,
            'total':      len(resultado),
            'archivos':   archivos_ordenados,
        }
        if errores:
            resp['errores'] = errores
        return jsonify(resp)
    except Exception as e:
        return error_interno(e, 'Error al obtener kanban de terminales')


@bp.route('/api/terminal-stock/<codigo>', methods=['PUT'])
@requiere_pin_admin
def api_guardar_stock_terminal(codigo):
    """Guardar o actualizar stock (actual, mínimo, notas) de un terminal."""
    try:
        data = request.get_json(silent=True) or {}
        stock_actual = int(data.get('stock_actual', 0))
        stock_minimo = int(data.get('stock_minimo', 0))
        notas        = (data.get('notas') or '').strip()[:200] or None

        db.session.execute(text("""
            INSERT INTO terminales_stock (terminal_codigo, stock_actual, stock_minimo, notas, updated_at)
            VALUES (:codigo, :actual, :minimo, :notas, datetime('now'))
            ON CONFLICT(terminal_codigo) DO UPDATE
                SET stock_actual = excluded.stock_actual,
                    stock_minimo = excluded.stock_minimo,
                    notas        = excluded.notas,
                    updated_at   = excluded.updated_at
        """), {'codigo': codigo, 'actual': stock_actual, 'minimo': stock_minimo, 'notas': notas})
        db.session.commit()

        return jsonify({'success': True, 'stock_actual': stock_actual, 'stock_minimo': stock_minimo})
    except Exception as e:
        return error_interno(e, 'Error al guardar stock de terminal')


def _sugerir_stock(subtotal: int):
    """Tabla de tiers calibrada con las referencias del usuario."""
    tiers = [
        (1,   30,  10),
        (3,   40,  20),
        (5,   50,  20),
        (8,   70,  30),
        (11,  100, 40),
        (16,  250, 100),
        (33,  400, 200),
        (50,  600, 250),
        (75,  1000, 500),
        (100, 1200, 500),
        (160, 2000, 800),
        (280, 3500, 1500),
    ]
    for max_sub, actual, minimo in tiers:
        if subtotal <= max_sub:
            return actual, minimo
    return 5000, 2000


@bp.route('/api/kanban-terminales/sugerir-stock', methods=['POST'])
@requiere_pin_admin
def api_sugerir_stock_batch():
    """Calcula y guarda stock sugerido para terminales con stock_actual = 0."""
    try:
        # Obtener todos los subtotales igual que el kanban principal
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        upload_folder = current_app.config['UPLOAD_FOLDER']

        subtotales: dict = {}

        def _valido(t):
            return bool(t) and t not in ('NAN', 'S/T', '')

        for codigo in codigos:
            archivo = codigo['archivo_excel']
            filepath = os.path.join(upload_folder, archivo)
            if not os.path.exists(filepath):
                continue
            nombre = os.path.splitext(archivo)[0]
            try:
                df = leer_excel_cacheado(filepath)
                col_de    = next((c for c in df.columns if 'de terminal'   in str(c).lower()), None)
                col_para  = next((c for c in df.columns if 'para terminal' in str(c).lower()), None)
                col_cod   = next((c for c in df.columns if 'cod' in str(c).lower() and 'cable' in str(c).lower()), None)
                col_sec   = next((c for c in df.columns if 'secci' in str(c).lower() or c.lower() == 'seccion'), None)
                col_de_el = next((c for c in df.columns if 'de elemento'   in str(c).lower()), None)
                col_pa_el = next((c for c in df.columns if 'para elemento' in str(c).lower()), None)
                if not col_de and not col_para:
                    continue
                cont: dict = {}
                for _, row in df.iterrows():
                    if col_cod:
                        cod = str(row.get(col_cod, '')).strip()
                        if not cod or cod.lower() == 'nan':
                            continue
                    if col_sec:
                        sec = str(row.get(col_sec, '')).strip()
                        if not sec or sec.lower() == 'nan':
                            continue
                    de_t   = str(row.get(col_de,   '') if col_de   else '').strip().upper()
                    para_t = str(row.get(col_para, '') if col_para else '').strip().upper()
                    de_np   = str(row.get(col_de_el, '') if col_de_el else '').strip().endswith('*')
                    para_np = str(row.get(col_pa_el, '') if col_pa_el else '').strip().endswith('*')
                    if _valido(de_t) and _valido(para_t) and de_t == para_t:
                        if not (de_np and para_np):
                            cont[de_t] = cont.get(de_t, 0) + (1 if (de_np or para_np) else 2)
                    else:
                        if _valido(de_t) and not de_np:
                            cont[de_t] = cont.get(de_t, 0) + 1
                        if _valido(para_t) and not para_np:
                            cont[para_t] = cont.get(para_t, 0) + 1
                for t, qty in cont.items():
                    subtotales[t] = subtotales.get(t, 0) + qty
            except Exception:
                pass

        # Obtener stock actual
        rows_stock = db.session.execute(
            text("SELECT terminal_codigo, stock_actual FROM terminales_stock")
        ).fetchall()
        tiene_stock = {r[0] for r in rows_stock if r[1] > 0}

        # Solo actualizar terminales sin stock
        actualizados = []
        for terminal, subtotal in subtotales.items():
            if terminal in tiene_stock or subtotal == 0:
                continue
            actual, minimo = _sugerir_stock(subtotal)
            db.session.execute(text("""
                INSERT INTO terminales_stock (terminal_codigo, stock_actual, stock_minimo, updated_at)
                VALUES (:cod, :actual, :minimo, datetime('now'))
                ON CONFLICT(terminal_codigo) DO UPDATE
                    SET stock_actual = excluded.stock_actual,
                        stock_minimo = excluded.stock_minimo,
                        updated_at   = excluded.updated_at
            """), {'cod': terminal, 'actual': actual, 'minimo': minimo})
            actualizados.append({'terminal': terminal, 'subtotal': subtotal,
                                 'stock_actual': actual, 'stock_minimo': minimo})
        db.session.commit()

        return jsonify({'success': True, 'actualizados': len(actualizados), 'detalle': actualizados})
    except Exception as e:
        return error_interno(e, 'Error al sugerir stock')


@bp.route('/api/kanban-terminales/export-excel', methods=['GET'])
@requiere_pin_admin
def api_exportar_pedido_excel():
    """Genera un Excel de hoja de pedido con subtotal y detalle de archivos en una sola columna."""

    def _nombreCorto(nombre: str) -> str:
        import re as _re
        return _re.sub(r'(_\d{8}(_v\d+)?|_v\d+)$', '', nombre, flags=_re.IGNORECASE)

    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        upload_folder = current_app.config['UPLOAD_FOLDER']

        terminal_detalle: dict = {}
        archivos_ordenados: list = []

        def _valido(t):
            return bool(t) and t not in ('NAN', 'S/T', '')

        for codigo in codigos:
            archivo = codigo['archivo_excel']
            filepath = os.path.join(upload_folder, archivo)
            if not os.path.exists(filepath):
                continue
            nombre = os.path.splitext(archivo)[0]
            try:
                df = leer_excel_cacheado(filepath)
                col_de    = next((c for c in df.columns if 'de terminal'   in str(c).lower()), None)
                col_para  = next((c for c in df.columns if 'para terminal' in str(c).lower()), None)
                col_cod   = next((c for c in df.columns if 'cod' in str(c).lower() and 'cable' in str(c).lower()), None)
                col_sec   = next((c for c in df.columns if 'secci' in str(c).lower() or c.lower() == 'seccion'), None)
                col_de_el = next((c for c in df.columns if 'de elemento'   in str(c).lower()), None)
                col_pa_el = next((c for c in df.columns if 'para elemento' in str(c).lower()), None)
                if not col_de and not col_para:
                    continue
                if nombre not in archivos_ordenados:
                    archivos_ordenados.append(nombre)
                cont: dict = {}
                for _, row in df.iterrows():
                    if col_cod:
                        cod = str(row.get(col_cod, '')).strip()
                        if not cod or cod.lower() == 'nan':
                            continue
                    if col_sec:
                        sec = str(row.get(col_sec, '')).strip()
                        if not sec or sec.lower() == 'nan':
                            continue
                    de_t   = str(row.get(col_de,   '') if col_de   else '').strip().upper()
                    para_t = str(row.get(col_para, '') if col_para else '').strip().upper()
                    de_np   = str(row.get(col_de_el, '') if col_de_el else '').strip().endswith('*')
                    para_np = str(row.get(col_pa_el, '') if col_pa_el else '').strip().endswith('*')
                    if _valido(de_t) and _valido(para_t) and de_t == para_t:
                        if not (de_np and para_np):
                            cont[de_t] = cont.get(de_t, 0) + (1 if (de_np or para_np) else 2)
                    else:
                        if _valido(de_t) and not de_np:
                            cont[de_t] = cont.get(de_t, 0) + 1
                        if _valido(para_t) and not para_np:
                            cont[para_t] = cont.get(para_t, 0) + 1
                for t, qty in cont.items():
                    if qty > 0:
                        terminal_detalle.setdefault(t, {})[nombre] = qty
            except Exception:
                pass

        maquina_repo = MaquinaRepository(db)
        maquinas = maquina_repo.obtener_todas_maquinas()
        terminal_maquina = {}
        for maq in maquinas:
            for t in maquina_repo.obtener_terminales_asignados(maq['id']):
                terminal_maquina[t] = {'maquina': maq['nombre'], 'puesto': maq.get('puesto_nombre', '')}

        rows_gav = db.session.execute(text("SELECT terminal_codigo, gaveta FROM terminales_gavetas")).fetchall()
        gavetas_map = {r[0]: r[1] for r in rows_gav}

        rows_stock = db.session.execute(
            text("SELECT terminal_codigo, stock_actual, stock_minimo, notas FROM terminales_stock")
        ).fetchall()
        stock_map = {r[0]: {'stock_actual': r[1], 'stock_minimo': r[2], 'notas': r[3]} for r in rows_stock}

        filas = []
        for terminal in sorted(terminal_detalle.keys()):
            asig = terminal_maquina.get(terminal, {})
            st   = stock_map.get(terminal, {'stock_actual': 0, 'stock_minimo': 0, 'notas': None})
            detalle = terminal_detalle[terminal]
            subtotal = sum(detalle.values())
            detalle_txt = ' | '.join(f"{_nombreCorto(a)}: {detalle[a]}" for a in archivos_ordenados if a in detalle)
            filas.append({
                'Terminal':          terminal,
                'Máquina':           asig.get('maquina', '—'),
                'Puesto':            asig.get('puesto',  '—'),
                'Gaveta':            gavetas_map.get(terminal, '—'),
                'Subtotal crimps':   subtotal,
                'Detalle archivos':  detalle_txt,
                'Stock actual':      st['stock_actual'],
                'Stock mínimo':      st['stock_minimo'],
                'Cantidad pedido':   '',
                'Notas':             st['notas'] or '',
            })

        df_out = pd.DataFrame(filas)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df_out.to_excel(writer, index=False, sheet_name='Pedido Terminales')
            ws = writer.sheets['Pedido Terminales']
            for col_cells in ws.columns:
                max_len = max((len(str(c.value or '')) for c in col_cells), default=10)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 50)
        buf.seek(0)

        fecha = datetime.now().strftime('%Y%m%d')
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'pedido_terminales_{fecha}.xlsx',
        )
    except Exception as e:
        return error_interno(e, 'Error al exportar pedido Excel')
