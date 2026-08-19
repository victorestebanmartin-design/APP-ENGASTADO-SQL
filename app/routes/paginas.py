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
    requiere_modulo,
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
        os.path.join(current_app.static_folder, 'img', 'icon-192.png'),
        mimetype='image/png',
    )


@bp.route('/sw.js')
def service_worker():
    """Service worker de la PWA, servido desde la RAIZ a proposito.

    El ambito de un service worker no puede subir por encima de la carpeta
    desde la que se sirve: en /static/sw.js solo controlaria /static/, y el
    navegador no daria la app por instalable. Desde aqui su ambito es '/'.
    """
    resp = send_file(
        os.path.join(current_app.static_folder, 'sw.js'),
        mimetype='application/javascript',
    )
    # Que un sw viejo no se quede cacheado tras una actualizacion
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@bp.route('/')
@requiere_operario
def home():
    """Página de inicio.

    En un PC de planta no pinta nada: ese equipo va a su módulo. Se delega en
    main.modules, que ya sabe a dónde mandar a cada rol (y qué hacer si el
    operario no tiene permiso para el módulo de su propio equipo).
    """
    from app.auth import gate_operario_activo
    from app.routes.puestos import _pc_identidad, MODULOS_PC
    if gate_operario_activo():
        modulo_pc, _, _ = _pc_identidad()
        if modulo_pc in MODULOS_PC:
            return redirect(url_for('main.modules'))
    return render_template('home.html')


@bp.route('/modules')
@requiere_operario
def modules():
    """Rejilla de módulos. En la práctica es la pantalla DEL SERVIDOR.

    Un PC de planta está dedicado a un módulo y entra directo a él (ver
    _destino_modulo): el operario de un puesto entra a trabajar, no a elegir.
    Por eso aquí se redirige a los PCs dedicados -- también si llegan a mano o
    con el botón atrás del navegador, que si no sería la puerta de atrás a
    todo lo que ese operario tenga permitido.

    En el servidor sí se ve la rejilla entera y sin pedir tarjeta. Con el gate
    desactivado se comporta como siempre: todo visible, sin filtrar."""
    from app.auth import gate_operario_activo
    from app.routes.puestos import _pc_identidad, _destino_modulo, MODULOS_PC, ROL_SERVIDOR
    permitidos = set(MODULOS_APP.keys())  # por defecto, todos
    if gate_operario_activo():
        nombre = session.get('operario_actual')
        modulo_pc, _, _ = _pc_identidad()

        # El servidor ve y puede todo, sin tarjeta.
        if modulo_pc == ROL_SERVIDOR:
            return render_template('modules.html', permitidos=permitidos)

        # PC de planta: a su módulo. Si el operario NO tiene permiso para el
        # módulo del equipo se le deja ver la rejilla a propósito: redirigirle
        # le mandaría a un 403 del que no podría salir.
        if modulo_pc in MODULOS_PC:
            from app.routes.base import operario_puede
            if nombre and operario_puede(nombre, modulo_pc):
                return redirect(_destino_modulo(modulo_pc))

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
    """Configuración de ESTE equipo: a qué módulo está dedicado y, solo si es
    engastado, a qué puesto.

    Sin configurar, main.home/main.modules redirigen aquí (ver
    requiere_operario en app/auth.py) y NO hace falta PIN: es la instalación
    de un equipo nuevo, autoservicio. Pero si el PC YA estaba configurado,
    llegar aquí es una reconfiguración -- exige la misma sesión de admin que
    el resto del panel, así que se manda por el PIN (con next= de vuelta
    aquí) antes de mostrar nada.

    Mangueras y manguitos NO tienen puestos: se elige el módulo y se acabó.
    """
    from app.routes.puestos import _pc_identidad
    from repositories.puesto_repository import PuestoRepository

    modulo_actual, puesto_id_actual, _ = _pc_identidad()
    if modulo_actual and proteccion_activa() and not sesion_admin_valida():
        return redirect(url_for('main.admin_pin', next=url_for('main.puesto_seleccionar')))

    puestos = PuestoRepository(db).obtener_todos_puestos()
    return render_template('puesto_selector.html',
                           puestos=puestos,
                           modulo_actual=modulo_actual,
                           puesto_actual_id=puesto_id_actual)


@bp.route('/login')
def login_operario():
    """Pantalla "pasa tu tarjeta": puerta de entrada a toda la app.

    Requiere que este PC ya esté configurado (si no, main.home/main.modules
    ya lo habrían mandado antes a /puesto/seleccionar). Sondea solo los logins
    que le corresponden -- por puesto en engastado, por módulo en mangueras y
    manguitos -- para no adoptar el login de otro equipo. Al detectar uno,
    adopta la sesión y entra DIRECTAMENTE al módulo de este PC.
    """
    from app.routes.puestos import _pc_identidad, _destino_modulo, MODULOS_APP_LABEL
    modulo, puesto_id, puesto_nombre = _pc_identidad()
    if not modulo:
        return redirect(url_for('main.puesto_seleccionar'))
    return render_template('login_operario.html',
                           modulo=modulo,
                           modulo_label=MODULOS_APP_LABEL.get(modulo, modulo),
                           puesto_id=puesto_id,
                           puesto_nombre=puesto_nombre,
                           destino=_destino_modulo(modulo))


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
@requiere_modulo('engastado')
def index_v3():
    """Vista principal V3 - Sistema de bonos.

    Es el destino directo de un PC de engastado: al pasar la tarjeta se entra
    aquí, no a la rejilla. Por eso pc_dedicado -- en ese caso cerrar V3 es
    salir (volver al lector), no volver a /modules.
    """
    from app.auth import pc_dedicado_a
    return render_template('index-v3.html', pc_dedicado=pc_dedicado_a('engastado'))


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
