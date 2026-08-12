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
    requiere_operario,
    proteccion_activa,
    sesion_admin_valida,
    marcar_sesion_admin,
    cerrar_sesion_admin,
)
from app.routes.base import (
    bp, db, error_interno, allowed_file, _ruta_upload_segura,
    _ahora_iso, _detectar_hoja, _es_error_nombre_bono_duplicado,
    MODULOS_APP, modulos_permitidos_de,
)


# ==================== RUTAS PRINCIPALES ====================

@bp.route('/favicon.ico')
def favicon():
    """Icono de pestaña del navegador (evita el 404 de /favicon.ico)."""
    return send_file(
        os.path.join(current_app.static_folder, 'img', 'reloj_100.png'),
        mimetype='image/png',
    )


@bp.route('/')
@requiere_operario
def home():
    """Página de inicio"""
    return render_template('home.html')


@bp.route('/modules')
@requiere_operario
def modules():
    """Página de módulos del sistema, filtrada por lo que el operario en
    sesión tiene permitido (ver MODULOS_APP/modulos_permitidos_de en
    app/routes/base.py). Con el gate desactivado, o para un operario sin
    modulos_permitidos configurado (NULL = "todos"), se ve la rejilla
    completa, igual que siempre. El filtrado SOLO se aplica con el gate
    activo: si se desactiva, no debe importar qué sesión de operario haya
    quedado colgada de antes -- todo vuelve a verse, sin excepciones."""
    from app.auth import gate_operario_activo
    permitidos = set(MODULOS_APP.keys())  # por defecto, todos
    if gate_operario_activo():
        nombre = session.get('operario_actual')
        if nombre:
            with db.engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT modulos_permitidos FROM operarios WHERE nombre=:n AND activo=1"
                ), {'n': nombre}).fetchone()
            if row:
                calculados = modulos_permitidos_de(row[0])
                if calculados is not None:
                    permitidos = calculados
                else:
                    # Sin permisos explícitos aún: todo menos Admin.
                    permitidos = {m for m in MODULOS_APP.keys() if m != 'admin'}
    return render_template('modules.html', permitidos=permitidos)


@bp.route('/puesto/seleccionar')
def puesto_seleccionar():
    """Configuración inicial (o reasignación) del puesto de este PC.

    Sin puesto asignado a este navegador, main.home/main.modules redirigen
    aquí (ver requiere_operario en app/auth.py) y NO hace falta PIN: es la
    configuración de un equipo recién instalado, autoservicio. Pero si el PC
    YA tenía un puesto asignado, esto es una reasignación -- exige la misma
    sesión de admin que el resto del panel, así que se manda por el PIN
    (con next= de vuelta aquí) antes de mostrar nada.
    """
    from app.routes.puestos import _puesto_pc_actual
    puesto_id_actual, _ = _puesto_pc_actual()
    if puesto_id_actual and proteccion_activa() and not sesion_admin_valida():
        return redirect(url_for('main.admin_pin', next=url_for('main.puesto_seleccionar')))

    from repositories.puesto_repository import PuestoRepository
    puestos = PuestoRepository(db).obtener_todos_puestos()
    return render_template('puesto_selector.html', puestos=puestos, puesto_actual_id=puesto_id_actual)


@bp.route('/login')
def login_operario():
    """Pantalla "pasa tu tarjeta": puerta de entrada a toda la app.

    Requiere que este PC ya tenga puesto asignado (si no, main.home/
    main.modules ya lo habrían mandado antes a /puesto/seleccionar). Sondea
    los logins de ESE puesto (evita adoptar el login de otro puesto) y, al
    detectar uno, adopta la sesión y sigue a /modules.
    """
    from app.routes.puestos import _puesto_pc_actual
    puesto_id, puesto_nombre = _puesto_pc_actual()
    if not puesto_id:
        return redirect(url_for('main.puesto_seleccionar'))
    return render_template('login_operario.html', puesto_id=puesto_id, puesto_nombre=puesto_nombre)


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


def _destino_pin_seguro(crudo):
    """Solo rutas internas ('/algo'), nunca '//host' (protocol-relative) ni
    URLs absolutas -- evita que 'next' se use para un open redirect."""
    if crudo and crudo.startswith('/') and not crudo.startswith('//'):
        return crudo
    return url_for('main.admin')


@bp.route('/admin/pin', methods=['GET', 'POST'])
def admin_pin():
    """Pantalla de introducción del PIN de administración.

    Acepta ?next=/ruta-interna para volver a donde estaba el usuario tras
    verificar el PIN (usado por la reasignación de puesto de un PC, ver
    main.puesto_seleccionar) en vez de mandarlo siempre a /admin.
    """
    destino = _destino_pin_seguro(request.values.get('next'))
    forzar = str(request.values.get('force', '')).lower() in ('1', 'true', 'si', 'sí', 'yes', 'on')

    # Si la protección no está activa, no tiene sentido pedir PIN
    if not proteccion_activa():
        return redirect(destino)
    # Si ya está verificado, directo al destino (salvo petición forzada SOS)
    if sesion_admin_valida() and not forzar:
        return redirect(destino)

    # Forzado: siempre exigir PIN fresco.
    if forzar and request.method == 'GET':
        cerrar_sesion_admin()

    error = None
    if request.method == 'POST':
        ip = request.remote_addr or 'desconocida'
        fallos, bloqueado_hasta = _PIN_INTENTOS.get(ip, (0, 0.0))

        if time.time() < bloqueado_hasta:
            minutos = int((bloqueado_hasta - time.time()) // 60) + 1
            error = f'Demasiados intentos fallidos. Espera {minutos} min.'
            return render_template('admin-pin.html', error=error, next=destino, force=forzar)

        pin = (request.form.get('pin') or '').strip()
        hash_introducido = hashlib.sha256(pin.encode('utf-8')).hexdigest()
        hash_correcto = current_app.config.get('ADMIN_PIN_HASH', '')
        # Comparación en tiempo constante para no filtrar info por timing
        if pin and hmac.compare_digest(hash_introducido, hash_correcto):
            _PIN_INTENTOS.pop(ip, None)
            marcar_sesion_admin()
            return redirect(destino)

        # Fallo: contar intento y bloquear la IP si supera el máximo
        fallos += 1
        if fallos >= _PIN_MAX_INTENTOS:
            _PIN_INTENTOS[ip] = (0, time.time() + _PIN_BLOQUEO_SEG)
            current_app.logger.warning(f'PIN admin: IP {ip} bloqueada {_PIN_BLOQUEO_SEG // 60} min tras {fallos} fallos')
        else:
            _PIN_INTENTOS[ip] = (fallos, 0.0)
        time.sleep(1)
        error = 'PIN incorrecto'

    return render_template('admin-pin.html', error=error, next=destino, force=forzar)


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
