"""
Rutas del módulo Ensayos de tracción (la lógica está en app/ensayos.py).

Dos públicos distintos:
  - El operario de engastado: consulta si toca ensayo, lo registra, avisa de
    una regulación y, tras un NOK, espera a que el supervisor decida.
  - Calidad: configura máquinas, matrices y fuerzas mínimas, y consulta el
    historial. Leer pide el permiso «ensayos»; cambiar la configuración pide
    además la sesión de administración, como el resto de la configuración.
"""
import io
import os
import uuid
from datetime import datetime, timedelta

import pandas as pd
from flask import request, jsonify, current_app, session, render_template
from sqlalchemy import text

from app import ensayos
from app.auth import requiere_pin_admin, requiere_modulo, verificar_credenciales_personales
from app.routes.base import bp, db, error_interno, operario_puede

TIPO_CAPTURA_SUPERVISOR = 'supervisor_ensayo'
SEGUNDOS_TARJETA_SUPERVISOR = 120


def _rechazo(err):
    return jsonify(err.como_json()), err.status


def _operario_peticion(datos):
    return ((datos.get('operario') or '').strip() or session.get('operario_actual') or '')[:80]


# ==================== PÁGINA ====================

@bp.route('/calidad')
@requiere_modulo('calidad')
def calidad_pagina():
    """Módulo Calidad: report de trazabilidad (app/routes/reports.py) y ensayos."""
    from app.auth import sesion_admin_valida
    return render_template('calidad.html', puede_editar=sesion_admin_valida())


# ==================== OPERARIO: estado y registro ====================

def secciones_terminal_bono(nombre_bono, terminal):
    """Secciones con las que se engasta ese terminal en los Excel del bono."""
    from repositories.bono_repository import BonoRepository
    from repositories.orden_repository import OrdenRepository
    from app.excel_manager import leer_excel_cacheado

    if not nombre_bono or not terminal:
        return []
    bono = BonoRepository(db).obtener_bono_por_nombre(nombre_bono)
    if not bono:
        return []
    objetivo = str(terminal).strip().upper()
    secciones, vistos = set(), set()
    for orden in OrdenRepository(db).obtener_ordenes_por_bono(bono['id']):
        archivo = orden.get('archivo_excel')
        if not archivo or archivo in vistos:
            continue
        vistos.add(archivo)
        ruta = os.path.join(current_app.config['UPLOAD_FOLDER'], archivo)
        if not os.path.exists(ruta):
            continue
        try:
            df = leer_excel_cacheado(ruta)
        except Exception:
            continue
        col_sec = next((c for c in ('Sección', 'Seccion') if c in df.columns), None)
        if not col_sec:
            continue
        for col_t in ('De Terminal', 'Para Terminal'):
            if col_t not in df.columns:
                continue
            filas = df[df[col_t].astype(str).str.strip().str.upper() == objetivo]
            for valor in filas[col_sec]:
                sec = ensayos.normalizar_seccion(valor)
                if sec:
                    secciones.add(sec)

    def _orden(s):
        try:
            return (0, float(s))
        except ValueError:
            return (1, 0.0)
    return sorted(secciones, key=_orden)


@bp.route('/api/ensayos/estado', methods=['GET'])
def api_ensayos_estado():
    """¿Hay que ensayar antes de engastar este terminal en esta máquina?

    Devuelve además las secciones candidatas (las del bono para ese terminal)
    con su fuerza mínima, para que el modal no tenga que adivinar nada.
    """
    maquina_id = (request.args.get('maquina_id') or '').strip()
    terminal = (request.args.get('terminal') or '').strip()
    bono = (request.args.get('bono') or '').strip()
    if not maquina_id or not terminal:
        return jsonify({'success': False, 'message': 'Faltan máquina y terminal'}), 400
    try:
        with db.engine.connect() as conn:
            est = ensayos.estado(conn, maquina_id, terminal)
            secciones = []
            if est['requerido']:
                candidatas = secciones_terminal_bono(bono, terminal)
                if not candidatas:
                    candidatas = [r[0] for r in conn.execute(text(
                        "SELECT DISTINCT seccion FROM ensayos_especificaciones "
                        "WHERE UPPER(terminal_codigo) = UPPER(:t)"), {'t': terminal})]
                for sec in candidatas:
                    spec = ensayos.especificacion(conn, terminal, sec)
                    secciones.append({
                        'seccion': sec,
                        'fuerza_min_n': spec['fuerza_min_n'] if spec else None,
                        'norma': spec.get('norma') if spec else None,
                        'instrucciones': spec.get('instrucciones') if spec else None,
                    })
        return jsonify({'success': True, **est, 'secciones': secciones})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos', methods=['POST'])
def api_ensayos_registrar():
    datos = request.get_json(silent=True) or {}
    try:
        with db.engine.begin() as conn:
            fila = ensayos.registrar_ensayo(
                conn,
                maquina_id=(datos.get('maquina_id') or '').strip(),
                terminal=(datos.get('terminal') or '').strip(),
                seccion=datos.get('seccion'),
                fuerza_n=datos.get('fuerza_n'),
                operario=_operario_peticion(datos),
                bono=(datos.get('bono') or '').strip(),
                orden_id=(datos.get('orden_id') or '').strip(),
                origen=datos.get('origen') or 'manual',
                comentario=(datos.get('comentario') or '').strip()[:500],
            )
        return jsonify({'success': True, 'ensayo': fila})
    except ensayos.EnsayoError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/regulacion', methods=['POST'])
def api_ensayos_regulacion():
    """El operario avisa de que ha regulado la máquina: el ensayo vigente deja
    de valer y el siguiente engaste pide uno nuevo."""
    datos = request.get_json(silent=True) or {}
    try:
        with db.engine.begin() as conn:
            fila = ensayos.registrar_regulacion(
                conn, (datos.get('maquina_id') or '').strip(),
                _operario_peticion(datos), (datos.get('comentario') or '').strip()[:500])
        return jsonify({'success': True, 'regulacion': fila})
    except ensayos.EnsayoError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


# ==================== NOK: decisión del supervisor ====================

def _es_supervisor(nombre):
    return bool(nombre) and operario_puede(nombre, ensayos.PERMISO_SUPERVISOR)


@bp.route('/api/ensayos/supervisores', methods=['GET'])
def api_ensayos_supervisores():
    """Supervisores que pueden identificarse con usuario y clave (sin lector)."""
    try:
        with db.engine.connect() as conn:
            filas = conn.execute(text(
                "SELECT id, nombre FROM operarios WHERE activo = 1 "
                "AND clave_personal_hash IS NOT NULL AND clave_personal_hash != '' ORDER BY nombre"
            )).fetchall()
        return jsonify({'success': True, 'supervisores': [
            {'id': f[0], 'nombre': f[1]} for f in filas if _es_supervisor(f[1])]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/<nok_id>/supervisor/tarjeta', methods=['POST'])
def api_ensayos_supervisor_tarjeta(nok_id):
    """Arma el lector del puesto para que la siguiente tarjeta sea la del
    supervisor (y no un login de operario). Reutiliza la captura armada con
    la que Admin registra tarjetas: la placa no necesita firmware nuevo."""
    from app.routes.pick_to_light import _placa_del_puesto
    from app.routes.sistema import _rfid_load_devices, _rfid_firmware_version
    try:
        with db.engine.connect() as conn:
            nok = ensayos.nok_pendiente(conn, nok_id)
        device_id, _ = _placa_del_puesto(nok.get('puesto_id'))
        sin_lector = ensayos.EnsayoError(
            'Este puesto no tiene lector de tarjetas conectado',
            'El supervisor puede identificarse con su usuario y clave', 409)
        if not device_id:
            return _rechazo(sin_lector)
        lector = (_rfid_load_devices() or {}).get(device_id) or {}
        try:
            online = (datetime.now() - datetime.fromisoformat(lector.get('last_seen', ''))).total_seconds() < 90
        except (TypeError, ValueError):
            online = False
        version = _rfid_firmware_version()
        # Con firmware viejo la placa no atiende capturas: la tarjeta haría
        # login como operario en vez de identificar al supervisor.
        if not online or not version or lector.get('fw') != version:
            return _rechazo(sin_lector)

        token = uuid.uuid4().hex
        expira_at = (datetime.now() + timedelta(seconds=SEGUNDOS_TARJETA_SUPERVISOR)).isoformat()
        with db.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO operario_tag_capturas
                    (device_id, operario_id, token, estado, uid, mensaje, expira_at, tipo, ref)
                VALUES (:d, '', :t, 'armada', NULL, NULL, :e, :tipo, :ref)
                ON CONFLICT(device_id) DO UPDATE SET
                    operario_id = '', token = excluded.token, estado = 'armada',
                    uid = NULL, mensaje = NULL, expira_at = excluded.expira_at,
                    tipo = excluded.tipo, ref = excluded.ref, created_at = datetime('now')
            """), {'d': device_id, 't': token, 'e': expira_at,
                  'tipo': TIPO_CAPTURA_SUPERVISOR, 'ref': nok_id})
        return jsonify({'success': True, 'token': token, 'segundos': SEGUNDOS_TARJETA_SUPERVISOR})
    except ensayos.EnsayoError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/supervisor/tarjeta/<token>', methods=['GET'])
def api_ensayos_supervisor_tarjeta_estado(token):
    try:
        with db.engine.connect() as conn:
            fila = conn.execute(text("""
                SELECT estado, mensaje, expira_at FROM operario_tag_capturas
                WHERE token = :t AND tipo = :tipo
            """), {'t': token, 'tipo': TIPO_CAPTURA_SUPERVISOR}).mappings().first()
        if not fila:
            return jsonify({'success': True, 'estado': 'caducada',
                            'mensaje': 'El lector ya no espera la tarjeta'})
        estado = fila['estado']
        if estado == 'armada':
            try:
                if datetime.fromisoformat(fila['expira_at']) <= datetime.now():
                    estado = 'caducada'
            except (TypeError, ValueError):
                estado = 'caducada'
        return jsonify({'success': True, 'estado': estado,
                        'supervisor': fila['mensaje'] if estado == 'asignada' else None,
                        'mensaje': fila['mensaje']})
    except Exception as e:
        return error_interno(e)


def resolver_tarjeta_supervisor(conn, fila, uid):
    """La placa ha leído una tarjeta con una captura de supervisor armada.
    Lo llama operarios.py:api_esp32_operario_captura_resultado.

    Devuelve (respuesta_json, status). Si la tarjeta no vale, la captura
    sigue armada para que otro supervisor pueda pasar la suya.
    """
    from app.routes.operarios import _operario_por_tag, _captura_tag_resultado
    op = _operario_por_tag(conn, uid)
    if not op or not _es_supervisor(op[1]):
        mensaje = ('Tarjeta no registrada' if not op
                   else f'{op[1]} no tiene permiso de supervisor de ensayos')
        conn.execute(text("UPDATE operario_tag_capturas SET mensaje = :m "
                          "WHERE device_id = :d AND token = :t"),
                     {'m': mensaje, 'd': fila['device_id'], 't': fila['token']})
        return {'success': False, 'error': 'SIN PERMISO SUPERVISOR' if op else 'TARJETA NO REGISTRADA'}, 409
    _captura_tag_resultado(conn, fila, 'asignada', op[1], uid)
    return {'success': True, 'uid': uid, 'operario': op[1]}, 200


@bp.route('/api/ensayos/<nok_id>/decision', methods=['POST'])
def api_ensayos_decision(nok_id):
    """El supervisor, ya identificado, decide: repetir el ensayo o continuar.

    Identificación: el token de una tarjeta ya leída por el lector, o su
    usuario y clave personal (puestos sin lector).
    """
    datos = request.get_json(silent=True) or {}
    token = (datos.get('token') or '').strip()
    try:
        # Identificar al supervisor antes de abrir la transacción: la clave y
        # el permiso se comprueban con conexiones propias.
        cap = None
        if token:
            with db.engine.connect() as conn:
                cap = conn.execute(text("""
                    SELECT device_id, token, mensaje FROM operario_tag_capturas
                    WHERE token = :t AND tipo = :tipo AND ref = :ref AND estado = 'asignada'
                """), {'t': token, 'tipo': TIPO_CAPTURA_SUPERVISOR, 'ref': nok_id}).mappings().first()
            if not cap:
                raise ensayos.EnsayoError('La tarjeta del supervisor ya no es válida',
                                          'Que vuelva a pasar la tarjeta', 403)
            supervisor, via = cap['mensaje'], 'tarjeta'
        else:
            op = verificar_credenciales_personales(
                (datos.get('usuario') or '').strip(), datos.get('clave') or '')
            if not op:
                raise ensayos.EnsayoError('Usuario o clave incorrectos',
                                          'Revisa la clave personal del supervisor', 403)
            supervisor, via = op['nombre'], 'clave'
        if not _es_supervisor(supervisor):
            raise ensayos.EnsayoError(f'{supervisor} no tiene permiso de supervisor de ensayos',
                                      'Admin → Operarios → Módulos permitidos', 403)

        with db.engine.begin() as conn:
            if cap:
                # Un solo uso: la misma lectura no sirve para otra decisión.
                usada = conn.execute(text(
                    "UPDATE operario_tag_capturas SET estado = 'usada' "
                    "WHERE device_id = :d AND token = :t AND estado = 'asignada'"),
                    {'d': cap['device_id'], 't': cap['token']}).rowcount
                if not usada:
                    raise ensayos.EnsayoError('La tarjeta del supervisor ya no es válida',
                                              'Que vuelva a pasar la tarjeta', 403)
            fila = ensayos.registrar_decision(
                conn, nok_id, (datos.get('decision') or '').strip(), supervisor, via,
                comentario=(datos.get('comentario') or '').strip()[:500],
                operario=_operario_peticion(datos) or None)
        return jsonify({'success': True, 'decision': fila})
    except ensayos.EnsayoError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


# ==================== CALIDAD: configuración ====================

@bp.route('/api/ensayos/config', methods=['GET'])
@requiere_modulo('calidad')
def api_ensayos_config():
    """Máquinas con su frecuencia, sus matrices y sus terminales."""
    try:
        with db.engine.connect() as conn:
            maquinas = [dict(r) for r in conn.execute(text("""
                SELECT m.id, m.nombre, m.modelo, m.tipo_operacion, m.lleva_regulacion,
                       m.ensayo_frecuencia, p.nombre AS puesto_nombre
                FROM maquinas m LEFT JOIN puestos p ON p.id = m.puesto_id
                WHERE m.activo = 1 ORDER BY p.nombre, m.nombre
            """)).mappings()]
            matrices = [dict(r) for r in conn.execute(text(
                "SELECT id, maquina_id, nombre, codigo FROM matrices WHERE activo = 1 ORDER BY nombre"
            )).mappings()]
            terminales = [dict(r) for r in conn.execute(text(
                "SELECT maquina_id, terminal_codigo, matriz_id FROM maquinas_terminales "
                "WHERE activo = 1 ORDER BY terminal_codigo"
            )).mappings()]
        for m in maquinas:
            m['matrices'] = [z for z in matrices if z['maquina_id'] == m['id']]
            m['terminales'] = [t for t in terminales if t['maquina_id'] == m['id']]
        return jsonify({'success': True, 'maquinas': maquinas})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/maquinas/<maquina_id>', methods=['PUT'])
@requiere_pin_admin
def api_ensayos_maquina(maquina_id):
    datos = request.get_json(silent=True) or {}
    frecuencia = datos.get('ensayo_frecuencia') or None
    if frecuencia is not None and frecuencia not in ensayos.FRECUENCIAS:
        return jsonify({'success': False, 'message': 'Frecuencia no válida'}), 400
    try:
        with db.engine.begin() as conn:
            n = conn.execute(text(
                "UPDATE maquinas SET ensayo_frecuencia = :f, updated_at = datetime('now') "
                "WHERE id = :id AND activo = 1"), {'f': frecuencia, 'id': maquina_id}).rowcount
        if not n:
            return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/matrices', methods=['POST'])
@requiere_pin_admin
def api_ensayos_matriz_crear():
    datos = request.get_json(silent=True) or {}
    maquina_id = (datos.get('maquina_id') or '').strip()
    nombre = (datos.get('nombre') or '').strip()[:60]
    if not maquina_id or not nombre:
        return jsonify({'success': False, 'message': 'Máquina y nombre son obligatorios'}), 400
    try:
        with db.engine.begin() as conn:
            if not conn.execute(text("SELECT 1 FROM maquinas WHERE id = :id AND activo = 1"),
                                {'id': maquina_id}).fetchone():
                return jsonify({'success': False, 'message': 'Máquina no encontrada'}), 404
            matriz_id = 'mtz_' + uuid.uuid4().hex[:10]
            conn.execute(text("INSERT INTO matrices (id, maquina_id, nombre, codigo) "
                              "VALUES (:id, :m, :n, :c)"),
                         {'id': matriz_id, 'm': maquina_id, 'n': nombre,
                          'c': (datos.get('codigo') or '').strip()[:60] or None})
        return jsonify({'success': True, 'matriz': {'id': matriz_id, 'maquina_id': maquina_id,
                                                    'nombre': nombre}})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/matrices/<matriz_id>', methods=['PUT', 'DELETE'])
@requiere_pin_admin
def api_ensayos_matriz(matriz_id):
    try:
        with db.engine.begin() as conn:
            if request.method == 'DELETE':
                # Baja suave: los ensayos antiguos siguen apuntando a ella.
                n = conn.execute(text("UPDATE matrices SET activo = 0 WHERE id = :id"),
                                 {'id': matriz_id}).rowcount
                conn.execute(text("UPDATE maquinas_terminales SET matriz_id = NULL "
                                  "WHERE matriz_id = :id"), {'id': matriz_id})
            else:
                datos = request.get_json(silent=True) or {}
                nombre = (datos.get('nombre') or '').strip()[:60]
                if not nombre:
                    return jsonify({'success': False, 'message': 'El nombre es obligatorio'}), 400
                n = conn.execute(text("UPDATE matrices SET nombre = :n, codigo = :c "
                                      "WHERE id = :id AND activo = 1"),
                                 {'n': nombre, 'c': (datos.get('codigo') or '').strip()[:60] or None,
                                  'id': matriz_id}).rowcount
        if not n:
            return jsonify({'success': False, 'message': 'Matriz no encontrada'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/terminal-matriz', methods=['PUT'])
@requiere_pin_admin
def api_ensayos_terminal_matriz():
    """Qué matriz de su máquina engasta ese terminal (o ninguna)."""
    datos = request.get_json(silent=True) or {}
    maquina_id = (datos.get('maquina_id') or '').strip()
    terminal = (datos.get('terminal') or '').strip()
    matriz_id = (datos.get('matriz_id') or '').strip() or None
    try:
        with db.engine.begin() as conn:
            if matriz_id and not conn.execute(text(
                    "SELECT 1 FROM matrices WHERE id = :id AND maquina_id = :m AND activo = 1"),
                    {'id': matriz_id, 'm': maquina_id}).fetchone():
                return jsonify({'success': False,
                                'message': 'Esa matriz no es de esta máquina'}), 400
            n = conn.execute(text(
                "UPDATE maquinas_terminales SET matriz_id = :mz "
                "WHERE maquina_id = :m AND terminal_codigo = :t AND activo = 1"),
                {'mz': matriz_id, 'm': maquina_id, 't': terminal}).rowcount
        if not n:
            return jsonify({'success': False,
                            'message': 'Ese terminal no está asignado a esta máquina'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


# ==================== CALIDAD: fuerzas mínimas ====================

@bp.route('/api/ensayos/especificaciones', methods=['GET'])
@requiere_modulo('calidad')
def api_ensayos_especificaciones():
    try:
        with db.engine.connect() as conn:
            filas = [dict(r) for r in conn.execute(text(
                "SELECT * FROM ensayos_especificaciones "
                "ORDER BY terminal_codigo = '', terminal_codigo, CAST(seccion AS REAL)"
            )).mappings()]
        return jsonify({'success': True, 'especificaciones': filas})
    except Exception as e:
        return error_interno(e)


def _guardar_especificacion(conn, terminal, seccion, fuerza, norma=None, instrucciones=None):
    seccion = ensayos.normalizar_seccion(seccion)
    if not seccion:
        raise ensayos.EnsayoError('Sección no válida', 'Escribe los mm², p. ej. 1,5', 400)
    try:
        fuerza = float(str(fuerza).replace(',', '.'))
    except (TypeError, ValueError):
        raise ensayos.EnsayoError('Fuerza mínima no válida', 'Escribe los newtons, p. ej. 155', 400)
    if not (0 < fuerza < 100000):
        raise ensayos.EnsayoError('Fuerza mínima no válida', 'Escribe los newtons, p. ej. 155', 400)
    conn.execute(text("""
        INSERT INTO ensayos_especificaciones
            (terminal_codigo, seccion, fuerza_min_n, norma, instrucciones, updated_at)
        VALUES (:t, :s, :f, :n, :i, datetime('now'))
        ON CONFLICT(terminal_codigo, seccion) DO UPDATE SET
            fuerza_min_n = excluded.fuerza_min_n, norma = excluded.norma,
            instrucciones = excluded.instrucciones, updated_at = datetime('now')
    """), {'t': (terminal or '').strip().upper(), 's': seccion, 'f': fuerza,
          'n': (norma or '').strip()[:120] or None,
          'i': (instrucciones or '').strip()[:2000] or None})


@bp.route('/api/ensayos/especificaciones', methods=['POST'])
@requiere_pin_admin
def api_ensayos_especificacion_guardar():
    datos = request.get_json(silent=True) or {}
    try:
        with db.engine.begin() as conn:
            _guardar_especificacion(conn, datos.get('terminal_codigo'), datos.get('seccion'),
                                    datos.get('fuerza_min_n'), datos.get('norma'),
                                    datos.get('instrucciones'))
        return jsonify({'success': True})
    except ensayos.EnsayoError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ensayos/especificaciones/<int:spec_id>', methods=['DELETE'])
@requiere_pin_admin
def api_ensayos_especificacion_borrar(spec_id):
    try:
        with db.engine.begin() as conn:
            n = conn.execute(text("DELETE FROM ensayos_especificaciones WHERE id = :id"),
                             {'id': spec_id}).rowcount
        if not n:
            return jsonify({'success': False, 'message': 'No encontrada'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


def _columna(df, candidatos):
    normal = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidatos:
        if cand in normal:
            return normal[cand]
    return None


@bp.route('/api/ensayos/especificaciones/importar', methods=['POST'])
@requiere_pin_admin
def api_ensayos_especificaciones_importar():
    """Excel con columnas Terminal (vacía = genérica), Sección y Fuerza mínima
    (N); Norma e Instrucciones opcionales. Todo o nada: si una fila está mal,
    no se guarda ninguna y se dice cuál."""
    fichero = request.files.get('archivo')
    if not fichero:
        return jsonify({'success': False, 'message': 'Falta el archivo'}), 400
    try:
        df = pd.read_excel(io.BytesIO(fichero.read()), dtype=str)
    except Exception:
        return jsonify({'success': False, 'message': 'No se ha podido leer el Excel'}), 400
    col_t = _columna(df, ['terminal', 'terminal_codigo', 'código terminal', 'codigo terminal'])
    col_s = _columna(df, ['sección', 'seccion', 'sección (mm2)', 'seccion (mm2)', 'mm2'])
    col_f = _columna(df, ['fuerza mínima (n)', 'fuerza minima (n)', 'fuerza mínima',
                          'fuerza minima', 'fuerza_min_n', 'fuerza (n)', 'fuerza'])
    col_n = _columna(df, ['norma'])
    col_i = _columna(df, ['instrucciones'])
    if not col_s or not col_f:
        return jsonify({'success': False,
                        'message': 'El Excel necesita las columnas «Sección» y «Fuerza mínima (N)»'}), 400

    def _celda(fila, col):
        if not col:
            return None
        v = fila[col]
        return None if pd.isna(v) else str(v).strip()

    try:
        with db.engine.begin() as conn:
            n = 0
            for i, fila in df.iterrows():
                if not _celda(fila, col_s) and not _celda(fila, col_f):
                    continue
                try:
                    _guardar_especificacion(conn, _celda(fila, col_t), _celda(fila, col_s),
                                            _celda(fila, col_f), _celda(fila, col_n),
                                            _celda(fila, col_i))
                except ensayos.EnsayoError as err:
                    raise ensayos.EnsayoError(f'Fila {i + 2}: {err.motivo}', err.consejo, 400)
                n += 1
        return jsonify({'success': True, 'importadas': n})
    except ensayos.EnsayoError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


# ==================== CALIDAD: historial ====================

@bp.route('/api/ensayos/historial', methods=['GET'])
@requiere_modulo('calidad')
def api_ensayos_historial():
    filtros, params = [], {}
    desde = (request.args.get('desde') or '').strip()
    hasta = (request.args.get('hasta') or '').strip()
    if desde:
        filtros.append('fecha >= :desde')
        params['desde'] = desde[:10] + ' 00:00:00'
    if hasta:
        filtros.append('fecha <= :hasta')
        params['hasta'] = hasta[:10] + ' 23:59:59'
    for campo in ('maquina_id', 'tipo', 'resultado', 'bono', 'operario'):
        valor = (request.args.get(campo) or '').strip()
        if valor:
            filtros.append(f'{campo} = :{campo}')
            params[campo] = valor
    terminal = (request.args.get('terminal') or '').strip()
    if terminal:
        filtros.append('UPPER(terminal_codigo) LIKE UPPER(:terminal)')
        params['terminal'] = f'%{terminal}%'
    try:
        limite = max(1, min(int(request.args.get('limite') or 500), 5000))
    except ValueError:
        limite = 500
    where = ('WHERE ' + ' AND '.join(filtros)) if filtros else ''
    try:
        with db.engine.connect() as conn:
            filas = [dict(r) for r in conn.execute(text(
                f"SELECT * FROM ensayos_traccion {where} ORDER BY fecha DESC, rowid DESC LIMIT {limite}"
            ), params).mappings()]
        return jsonify({'success': True, 'eventos': filas})
    except Exception as e:
        return error_interno(e)
