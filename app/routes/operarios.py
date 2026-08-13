"""
Operarios (identificación controlada).
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
from datetime import datetime, timedelta
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


# ==================== OPERARIOS ====================

@bp.route('/api/modulos', methods=['GET'])
def api_modulos_get():
    """Lista de módulos de la app (MODULOS_APP), para las casillas de
    permisos en Admin -> Operarios. Fuente única de verdad: app/routes/base.py."""
    from app.routes.base import MODULOS_APP
    return jsonify({'success': True, 'modulos': [
        {'slug': slug, 'label': info['label']} for slug, info in MODULOS_APP.items()
    ]})


def _operario_por_tag(conn, tag_uid):
    """Operario activo asociado a esa tarjeta NFC, o None."""
    return conn.execute(text(
        "SELECT id, nombre FROM operarios WHERE tag_uid = :t AND activo = 1"
    ), {'t': tag_uid}).fetchone()


@bp.route('/api/operarios', methods=['GET'])
def api_operarios_get():
    """Listar operarios activos"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, nombre, activo, created_at, tag_uid, modulos_permitidos "
                "FROM operarios ORDER BY nombre"
            )).fetchall()
        return jsonify({'success': True, 'operarios': [
            {'id': r[0], 'nombre': r[1], 'activo': r[2], 'created_at': r[3], 'tag_uid': r[4],
             # null = todos los modulos; lista = justo esos (ver base.py:modulos_permitidos_de)
             'modulos_permitidos': json.loads(r[5]) if r[5] else None}
            for r in rows
        ]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios', methods=['POST'])
def api_operarios_create():
    """Crear nuevo operario"""
    try:
        import uuid
        data = request.get_json() or {}
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400
        op_id = str(uuid.uuid4())[:8]
        with db.engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO operarios (id, nombre) VALUES (:id, :nombre)"
            ), {'id': op_id, 'nombre': nombre})
            conn.commit()
        return jsonify({'success': True, 'operario': {'id': op_id, 'nombre': nombre, 'activo': 1}})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>', methods=['PUT'])
def api_operarios_update(op_id):
    """Actualizar operario: nombre, su tarjeta NFC y/o sus módulos permitidos."""
    try:
        from app.routes.puestos import normalizar_tag_uid
        from app.routes.base import MODULOS_APP
        data = request.get_json() or {}

        # Tarjeta NFC del operario: UID en hex, o null/'' para quitarla.
        tag_uid, tocar_tag, limpiar_tag = None, False, False
        if 'tag_uid' in data:
            tocar_tag = True
            crudo = data.get('tag_uid')
            if crudo in (None, ''):
                limpiar_tag = True
            else:
                tag_uid = normalizar_tag_uid(crudo)
                if tag_uid is None:
                    return jsonify({'success': False,
                                    'error': 'El UID de la tarjeta no es válido '
                                             '(se espera hexadecimal, de 4 a 10 bytes)'}), 400

        # Módulos permitidos: lista de slugs, o null para "todos" (ver
        # app/routes/base.py:modulos_permitidos_de). Se valida contra
        # MODULOS_APP para no guardar slugs inventados.
        modulos_json, tocar_modulos = None, False
        if 'modulos_permitidos' in data:
            tocar_modulos = True
            crudo_mod = data.get('modulos_permitidos')
            if crudo_mod is None:
                modulos_json = None  # "todos los modulos"
            elif isinstance(crudo_mod, list):
                invalidos = [m for m in crudo_mod if m not in MODULOS_APP]
                if invalidos:
                    return jsonify({'success': False,
                                    'error': f'Módulo(s) desconocido(s): {", ".join(invalidos)}'}), 400
                modulos_json = json.dumps(sorted(set(crudo_mod)))
            else:
                return jsonify({'success': False,
                                'error': 'modulos_permitidos debe ser una lista o null'}), 400

        # Si solo se toca la tarjeta o los modulos, el nombre no es obligatorio.
        nombre = None
        if 'nombre' in data or not (tocar_tag or tocar_modulos):
            nombre = (data.get('nombre') or '').strip()
            if not nombre:
                return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400

        with db.engine.connect() as conn:
            if tocar_tag and not limpiar_tag:
                ocupado = _operario_por_tag(conn, tag_uid)
                if ocupado and ocupado[0] != op_id:
                    return jsonify({'success': False,
                                    'error': f'Esa tarjeta ya está asignada a '
                                             f'"{ocupado[1]}"'}), 409
            if nombre is not None:
                conn.execute(text("UPDATE operarios SET nombre=:nombre WHERE id=:id"),
                             {'nombre': nombre, 'id': op_id})
            if tocar_tag:
                conn.execute(text("UPDATE operarios SET tag_uid=:t WHERE id=:id"),
                             {'t': None if limpiar_tag else tag_uid, 'id': op_id})
            if tocar_modulos:
                conn.execute(text("UPDATE operarios SET modulos_permitidos=:m WHERE id=:id"),
                             {'m': modulos_json, 'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except IntegrityError:
        return jsonify({'success': False,
                        'error': 'Esa tarjeta ya está asignada a otro operario'}), 409
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>', methods=['DELETE'])
def api_operarios_delete(op_id):
    """Desactivar operario"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET activo=0 WHERE id=:id"
            ), {'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>/activar', methods=['POST'])
def api_operarios_activar(op_id):
    """Reactivar operario desactivado"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET activo=1 WHERE id=:id"
            ), {'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


# ==================== LOGIN EXCLUSIVO DE OPERARIOS ====================
#
# Al entrar al módulo de engastado el operario se identifica en el modal
# inicial. Ese login queda registrado en operario_logins y es exclusivo:
# mientras esté activo, ningún otro puesto puede entrar con el mismo
# operario. El navegador manda un latido periódico; si deja de llegar
# (cierre brusco del navegador, corte de luz), el login caduca solo.

LOGIN_CADUCIDAD_MINUTOS = 3  # sin latido durante este tiempo => login fantasma


def _expirar_logins_fantasma(conn):
    """Desactiva logins cuyo último latido es demasiado antiguo."""
    limite = (datetime.now() - timedelta(minutes=LOGIN_CADUCIDAD_MINUTOS)).isoformat()
    conn.execute(text(
        "UPDATE operario_logins SET activo=0 WHERE activo=1 AND ultimo_latido < :limite"
    ), {'limite': limite})


@bp.route('/api/operarios/login', methods=['POST'])
def api_operario_login():
    """Logear un operario en el módulo de engastado (login exclusivo).

    Devuelve 409 si el operario ya está dentro desde otro puesto.
    """
    try:
        import uuid
        data = request.get_json(silent=True) or {}
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400

        with db.engine.connect() as conn:
            _expirar_logins_fantasma(conn)

            existente = conn.execute(text(
                "SELECT timestamp_login FROM operario_logins "
                "WHERE activo=1 AND operario_nombre=:n"
            ), {'n': nombre}).fetchone()
            if existente:
                conn.commit()  # persistir la expiración de fantasmas
                hora = (existente[0] or '')[11:16]
                msg = f'{nombre} ya está dentro del módulo en otro puesto'
                if hora:
                    msg += f' (desde las {hora})'
                return jsonify({'success': False, 'error': msg}), 409

            login_id = str(uuid.uuid4())
            ahora = datetime.now().isoformat()
            try:
                conn.execute(text(
                    "INSERT INTO operario_logins "
                    "(id, operario_nombre, timestamp_login, ultimo_latido, activo) "
                    "VALUES (:id, :n, :t, :t, 1)"
                ), {'id': login_id, 'n': nombre, 't': ahora})
                conn.commit()
            except IntegrityError:
                # Carrera: otro puesto se logeó con este nombre en el mismo instante
                return jsonify({
                    'success': False,
                    'error': f'{nombre} ya está dentro del módulo en otro puesto'
                }), 409

        return jsonify({'success': True, 'login_id': login_id})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/logout', methods=['POST'])
def api_operario_logout():
    """Cerrar el login del operario.

    Llamado también vía sendBeacon al cerrar/refrescar la pestaña, por lo
    que se acepta el JSON aunque llegue sin Content-Type application/json.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        login_id = (data.get('login_id') or '').strip()
        if not login_id:
            return jsonify({'success': False, 'error': 'login_id es obligatorio'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operario_logins SET activo=0 WHERE id=:id"
            ), {'id': login_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/login/latido', methods=['POST'])
def api_operario_latido():
    """Mantener vivo el login del operario (latido periódico del navegador).

    Si el login ya no está activo (caducó o un admin lo liberó) responde
    expirado=True; el frontend intentará re-logearse con el mismo nombre.
    """
    try:
        data = request.get_json(silent=True) or {}
        login_id = (data.get('login_id') or '').strip()
        if not login_id:
            return jsonify({'success': False, 'error': 'login_id es obligatorio'}), 400
        with db.engine.connect() as conn:
            res = conn.execute(text(
                "UPDATE operario_logins SET ultimo_latido=:t WHERE id=:id AND activo=1"
            ), {'t': datetime.now().isoformat(), 'id': login_id})
            conn.commit()
        if res.rowcount == 0:
            return jsonify({'success': False, 'expirado': True})
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/logins', methods=['GET'])
def api_operario_logins_get():
    """Listar logins activos (quién está dentro del módulo ahora mismo).

    Incluye puesto_id/puesto_nombre cuando el login vino de un lector RFID
    asignado a un puesto: el frontend lo sondea para saltarse la selección
    manual de puesto (ver static/js/v3/v3-rfid-entrada.js).

    Con ?puesto_id=X, filtra a solo los logins de ESE puesto -- imprescindible
    para el gate global de login (ver static/js/shared/rfid-login.js): sin
    este filtro, cualquier PC que sondee "el ultimo login que aparezca en
    cualquier sitio" podria adoptar por error el login de OTRO puesto. El
    sondeo sin filtro (usado hoy por Engastado V3) sigue funcionando igual.
    """
    try:
        puesto_id = (request.args.get('puesto_id') or '').strip() or None
        with db.engine.connect() as conn:
            _expirar_logins_fantasma(conn)
            conn.commit()
            rows = conn.execute(text(
                "SELECT ol.id, ol.operario_nombre, ol.timestamp_login, ol.ultimo_latido, "
                "       ol.puesto_id, p.nombre "
                "FROM operario_logins ol LEFT JOIN puestos p ON p.id = ol.puesto_id "
                "WHERE ol.activo=1 AND (:puesto_id IS NULL OR ol.puesto_id = :puesto_id) "
                "ORDER BY ol.timestamp_login"
            ), {'puesto_id': puesto_id}).fetchall()
        return jsonify({'success': True, 'logins': [
            {'id': r[0], 'operario': r[1], 'desde': r[2], 'ultimo_latido': r[3],
             'puesto_id': r[4], 'puesto_nombre': r[5]}
            for r in rows
        ]})
    except Exception as e:
        return error_interno(e)


# ==================== SESION GLOBAL DE OPERARIO (gate de login) ====================
#
# operario_logins (arriba) es la sesion "de trabajo" -- exclusiva por
# operario, con latido, pensada para Engastado V3. Esto es distinto: una vez
# que un PC ve (via el sondeo con ?puesto_id=) que su operario ha pasado la
# tarjeta, adopta ese login guardando su identidad en la sesion de Flask de
# ESE navegador (vida corta, por pestaña/navegador), para que requiere_operario
# (app/auth.py) sepa quien esta detras de cada peticion sin volver a sondear.


@bp.route('/api/sesion/operario/adoptar', methods=['POST'])
def api_sesion_operario_adoptar():
    """Fija la sesion de Flask de este navegador a partir de un login_id ya
    creado (por un lector RFID). Llamado por static/js/shared/rfid-login.js
    tras detectar un login nuevo en el sondeo de /api/operarios/logins."""
    try:
        data = request.get_json(silent=True) or {}
        login_id = (data.get('login_id') or '').strip()
        if not login_id:
            return jsonify({'success': False, 'error': 'login_id es obligatorio'}), 400
        with db.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT operario_nombre FROM operario_logins WHERE id=:id AND activo=1"
            ), {'id': login_id}).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Ese login ya no está activo'}), 404
        session['operario_actual'] = row[0]
        session['operario_login_id'] = login_id
        return jsonify({'success': True, 'operario_nombre': row[0]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/operario', methods=['GET'])
def api_sesion_operario_get():
    """Operario adoptado en la sesion de ESTE navegador, o null si no hay
    ninguno (o si su login de servidor ya caduco por falta de latido).

    Incluye login_id: lo usa Engastado V3 (ver static/js/v3/v3-estado.js)
    para reutilizar la identificacion ya hecha en el gate global y no volver
    a pedir tarjeta al entrar al modulo -- ese login_id es el mismo id de
    operario_logins que ya gestiona el latido del gate, asi que V3 puede
    seguir usandolo tal cual para su propio latido."""
    try:
        nombre = session.get('operario_actual')
        login_id = session.get('operario_login_id')
        if not nombre or not login_id:
            return jsonify({'success': True, 'operario_nombre': None, 'login_id': None})
        with db.engine.connect() as conn:
            _expirar_logins_fantasma(conn)
            conn.commit()
            vivo = conn.execute(text(
                "SELECT 1 FROM operario_logins WHERE id=:id AND activo=1"
            ), {'id': login_id}).fetchone()
        if not vivo:
            session.pop('operario_actual', None)
            session.pop('operario_login_id', None)
            return jsonify({'success': True, 'operario_nombre': None, 'login_id': None})
        return jsonify({'success': True, 'operario_nombre': nombre, 'login_id': login_id})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/operario/salir', methods=['POST'])
def api_sesion_operario_salir():
    """Cierra la sesion de operario de ESTE navegador Y desactiva su login en
    el servidor: es una salida real, no solo un olvido local. Si no
    desactivaramos el login, volver a /login antes de que caduque solo (3
    min sin latido) lo adoptaria de nuevo sin pasar la tarjeta -- justo el
    bug que esto corrige."""
    login_id = session.get('operario_login_id')
    if login_id:
        with db.engine.connect() as conn:
            conn.execute(text("UPDATE operario_logins SET activo=0 WHERE id=:id"), {'id': login_id})
            conn.commit()
    session.pop('operario_actual', None)
    session.pop('operario_login_id', None)
    return jsonify({'success': True})


@bp.route('/api/sesion/operario/latido', methods=['POST'])
def api_sesion_operario_latido():
    """Late de la sesion de operario de ESTE navegador mientras navega por
    /modules y el resto de la app. Sin esto, operario_logins caducaria solo
    a los 3 minutos (ver _expirar_logins_fantasma) aunque el operario siga
    trabajando -- el login por tarjeta global no tenia ningun latido propio
    (a diferencia del de Engastado V3, que si lo tiene)."""
    login_id = session.get('operario_login_id')
    if not login_id:
        return jsonify({'success': False})
    with db.engine.connect() as conn:
        res = conn.execute(text(
            "UPDATE operario_logins SET ultimo_latido=:t WHERE id=:id AND activo=1"
        ), {'t': datetime.now().isoformat(), 'id': login_id})
        conn.commit()
    if res.rowcount == 0:
        session.pop('operario_actual', None)
        session.pop('operario_login_id', None)
        return jsonify({'success': False, 'expirado': True})
    return jsonify({'success': True})


@bp.route('/api/operarios/logins/<login_id>/liberar', methods=['POST'])
@requiere_pin_admin
def api_operario_login_liberar(login_id):
    """Liberar a la fuerza un login (admin): expulsa al operario del módulo."""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operario_logins SET activo=0 WHERE id=:id"
            ), {'id': login_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


# ==================== RFID ENTRY FOR ENGASTADO V3 ====================
#
# Dedicated RFID reader at Engastado V3 workstation entrance. Operario scans
# card to automatically log in to the module. Called by ESP32 firmware.
#
# Cada lector puede estar asignado a un puesto concreto desde Admin ->
# Lectores RFID (ver app/routes/sistema.py, endpoints /api/esp32/rfid/devices
# y el registro que se guarda en data/esp32_rfid_devices.json). Si lo está,
# el PC no tiene que preguntar el puesto: esta ruta se lo devuelve ya
# resuelto junto con el operario.


def _rfid_devices_file_path():
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'esp32_rfid_devices.json')


def _puesto_asignado_al_lector(device_id):
    """(puesto_id, puesto_nombre) asignados a ese lector, o (None, None)."""
    if not device_id:
        return None, None
    try:
        with open(_rfid_devices_file_path()) as f:
            devs = json.load(f)
    except Exception:
        return None, None
    dev = devs.get(device_id) or {}
    puesto_id = dev.get('puesto_id') or None
    return (puesto_id, dev.get('puesto_nombre') or None) if puesto_id else (None, None)


@bp.route('/api/puestos/engastado_v3/entrada', methods=['POST'])
def api_engastado_v3_entrada():
    """RFID card scan at Engastado V3 workstation entrance.

    ESP32 reader sends the card's UID (hex string) and its own device_id.
    This endpoint:
    1. Looks up operario by tag_uid in database
    2. Creates/reuses operario_logins session (exclusive login)
    3. If the reading device has a puesto assigned (Admin -> Lectores RFID),
       resolves it so the frontend can skip the manual puesto-selection step
    4. Returns operario name + login_id (+ puesto, if any) for the frontend

    Request:  { "tag_uid": "A1B2C3D4", "device_id": "a1b2c3d4e5f6" }
    Response 200:
      {
        "success": true,
        "operario_nombre": "Juan Pérez",
        "login_id": "uuid-here",
        "puesto_id": "puesto_001",       (null si el lector no tiene puesto asignado)
        "puesto_nombre": "Engastado 1",  (null si no aplica)
        "message": "Entrada registrada"
      }
    Response 404:
      {
        "success": false,
        "error": "Tarjeta RFID no registrada"
      }
    Response 409:
      {
        "success": false,
        "error": "Juan Pérez ya está dentro del módulo en otro puesto"
      }
    """
    try:
        data = request.get_json(silent=True) or {}
        tag_uid = (data.get('tag_uid') or '').strip().upper()
        device_id = (data.get('device_id') or '').strip()[:32] or None
        if not tag_uid:
            return jsonify({'success': False, 'error': 'tag_uid es obligatorio'}), 400

        # Registrar como "ultima tarjeta vista", igual que hace la pantalla
        # del carro con /api/esp32/evento?tipo=tag. Es lo que sondea Admin ->
        # Operarios al pulsar "Capturar tag": con esto, la captura funciona
        # igual de bien acercando la tarjeta a un lector RFID de puesto que
        # al lector NFC del carro -- mas logico si ya estas en tu puesto.
        try:
            from app.routes.sistema import _esp32_tags_file
            with open(_esp32_tags_file(), 'w') as f:
                json.dump({'uid': tag_uid, 'device_id': device_id, 'carro': '',
                          'ts': datetime.now().isoformat()}, f)
        except Exception:
            current_app.logger.exception('No se pudo registrar la ultima tarjeta vista (lector RFID)')

        # Deja constancia en el historial de eventos (Admin -> Diagnóstico
        # ESP32): es la única forma de comprobar en remoto que un lector de
        # puesto realmente lee tarjetas, sin depender solo de su 'online'.
        def _log(detalle, operario=''):
            try:
                from app.routes.sistema import _esp32_registrar_evento
                _esp32_registrar_evento({
                    'tipo': 'entrada_rfid', 'fase': '', 'device_id': device_id or '',
                    'carro': '', 'puesto': puesto_id or '', 'operario': operario,
                    'lote': '', 'grupo': '', 'uid': tag_uid, 'detalle': detalle,
                    'ts': datetime.now().isoformat(),
                })
            except Exception:
                current_app.logger.exception('No se pudo registrar el evento de entrada RFID')

        puesto_id, puesto_nombre = _puesto_asignado_al_lector(device_id)

        with db.engine.connect() as conn:
            # Look up operario by RFID tag
            op = _operario_por_tag(conn, tag_uid)
            if not op:
                _log('Tarjeta no registrada')
                return jsonify({
                    'success': False,
                    'error': 'Tarjeta RFID no registrada'
                }), 404

            op_id, nombre = op

            # Check if operario already has active session
            _expirar_logins_fantasma(conn)
            existente = conn.execute(text(
                "SELECT id FROM operario_logins WHERE activo=1 AND operario_nombre=:n"
            ), {'n': nombre}).fetchone()

            if existente:
                # Reuse existing session. Refresca el puesto por si el
                # operario ha vuelto a pasar la tarjeta en un lector distinto.
                login_id = existente[0]
                if puesto_id:
                    conn.execute(text(
                        "UPDATE operario_logins SET puesto_id=:p WHERE id=:id"
                    ), {'p': puesto_id, 'id': login_id})
                    conn.commit()
                _log('Sesión existente reutilizada', nombre)
                return jsonify({
                    'success': True,
                    'operario_nombre': nombre,
                    'login_id': login_id,
                    'puesto_id': puesto_id,
                    'puesto_nombre': puesto_nombre,
                    'message': 'Sesión existente reutilizada'
                }), 200

            # Create new session
            import uuid
            login_id = str(uuid.uuid4())
            ahora = datetime.now().isoformat()
            try:
                conn.execute(text(
                    "INSERT INTO operario_logins "
                    "(id, operario_nombre, timestamp_login, ultimo_latido, activo, puesto_id) "
                    "VALUES (:id, :n, :t, :t, 1, :p)"
                ), {'id': login_id, 'n': nombre, 't': ahora, 'p': puesto_id})
                conn.commit()
            except IntegrityError:
                # Race condition: operario logged in from another workstation
                _log(f'{nombre} ya está dentro del módulo en otro puesto', nombre)
                return jsonify({
                    'success': False,
                    'error': f'{nombre} ya está dentro del módulo en otro puesto'
                }), 409

            _log('Entrada registrada', nombre)
            return jsonify({
                'success': True,
                'operario_nombre': nombre,
                'login_id': login_id,
                'puesto_id': puesto_id,
                'puesto_nombre': puesto_nombre,
                'message': 'Entrada registrada'
            }), 200

    except Exception as e:
        return error_interno(e)
