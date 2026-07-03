"""
Páginas principales y protección por PIN del panel de administración.
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


# ==================== RUTAS PRINCIPALES ====================

@bp.route('/')
def home():
    """Página de inicio"""
    return render_template('home.html')


@bp.route('/modules')
def modules():
    """Página de módulos del sistema"""
    return render_template('modules.html')


# Versión y fecha del manual de uso (fáciles de actualizar aquí)
MANUAL_VERSION = 'v1.2'
MANUAL_FECHA = 'julio 2026'


@bp.route('/manual')
def manual():
    """Manual de uso de la aplicación (documentación, sin PIN)."""
    return render_template(
        'manual.html',
        MANUAL_VERSION=MANUAL_VERSION,
        MANUAL_FECHA=MANUAL_FECHA,
    )


@bp.route('/v3')
def index_v3():
    """Vista principal V3 - Sistema de bonos"""
    return render_template('index-v3.html')


@bp.route('/admin')
@requiere_pin_admin
def admin():
    """Panel de administración"""
    return render_template('admin.html', pin_activo=proteccion_activa())


# Anti fuerza bruta del PIN: intentos fallidos por IP (en memoria, por proceso)
_PIN_INTENTOS = {}  # ip -> (num_fallos, bloqueado_hasta_timestamp)
_PIN_MAX_INTENTOS = 5
_PIN_BLOQUEO_SEG = 15 * 60


@bp.route('/admin/pin', methods=['GET', 'POST'])
def admin_pin():
    """Pantalla de introducción del PIN de administración."""
    # Si la protección no está activa, no tiene sentido pedir PIN
    if not proteccion_activa():
        return redirect(url_for('main.admin'))
    # Si ya está verificado, directo al panel
    if sesion_admin_valida():
        return redirect(url_for('main.admin'))

    error = None
    if request.method == 'POST':
        ip = request.remote_addr or 'desconocida'
        fallos, bloqueado_hasta = _PIN_INTENTOS.get(ip, (0, 0.0))

        if time.time() < bloqueado_hasta:
            minutos = int((bloqueado_hasta - time.time()) // 60) + 1
            error = f'Demasiados intentos fallidos. Espera {minutos} min.'
            return render_template('admin-pin.html', error=error)

        pin = (request.form.get('pin') or '').strip()
        hash_introducido = hashlib.sha256(pin.encode('utf-8')).hexdigest()
        hash_correcto = current_app.config.get('ADMIN_PIN_HASH', '')
        # Comparación en tiempo constante para no filtrar info por timing
        if pin and hmac.compare_digest(hash_introducido, hash_correcto):
            _PIN_INTENTOS.pop(ip, None)
            marcar_sesion_admin()
            return redirect(url_for('main.admin'))

        # Fallo: contar intento y bloquear la IP si supera el máximo
        fallos += 1
        if fallos >= _PIN_MAX_INTENTOS:
            _PIN_INTENTOS[ip] = (0, time.time() + _PIN_BLOQUEO_SEG)
            current_app.logger.warning(f'PIN admin: IP {ip} bloqueada {_PIN_BLOQUEO_SEG // 60} min tras {fallos} fallos')
        else:
            _PIN_INTENTOS[ip] = (fallos, 0.0)
        time.sleep(1)
        error = 'PIN incorrecto'

    return render_template('admin-pin.html', error=error)


@bp.route('/admin/logout', methods=['GET', 'POST'])
def admin_logout():
    """Cierra la sesión de administración."""
    cerrar_sesion_admin()
    return redirect(url_for('main.admin_pin'))


@bp.route('/gestion-puestos')
@requiere_pin_admin
def gestion_puestos():
    """Gestión de puestos y máquinas"""
    return render_template('gestion-puestos.html')


@bp.route('/visualizacion')
def visualizacion():
    """Visualización y monitoreo"""
    return render_template('visualizacion.html', bono_inicial='')


@bp.route('/visualizacion/<string:nombre_bono>')
def visualizacion_bono(nombre_bono):
    """Visualización pre-seleccionando un bono concreto"""
    return render_template('visualizacion.html', bono_inicial=nombre_bono)


@bp.route('/progreso-bono')
def progreso_bono():
    """Dashboard de progreso ponderado (sin bono específico)"""
    return render_template('progreso-bono.html', bono_nombre='')


@bp.route('/progreso-bono/<string:nombre_bono>')
def progreso_bono_especifico(nombre_bono):
    """Dashboard de progreso ponderado para un bono concreto"""
    return render_template('progreso-bono.html', bono_nombre=nombre_bono)


@bp.route('/etiquetas')
def etiquetas():
    """Generación de etiquetas"""
    return render_template('etiquetas.html')
