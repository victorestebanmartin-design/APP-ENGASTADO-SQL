"""
Matrícula y etiqueta RFID de las máquinas.

Sirve para que el report de engastado diga qué máquina hizo cada carro. Las
manuales son móviles: en un puesto con lector, la máquina se pasa por él al
elegirla. No depende del pick-to-light ni de firmware nuevo:

- Dar de alta la etiqueta reutiliza la captura armada de operario_tag_capturas
  (tipo='maquina', ref=id de la máquina).
- En uso, el lector manda la etiqueta a la misma entrada que una tarjeta de
  operario (operarios.py:api_engastado_v3_entrada). Si es de una máquina, se
  apunta aquí como última lectura del puesto y no se crea ningún login. El
  navegador del puesto la recoge por sondeo.

Como el pick-to-light, nada de esto puede dejar a nadie sin trabajar: sin lector
o con la placa desenchufada se responde 200 con activo=False.
"""
import os
import re
import uuid
from datetime import datetime, timedelta

from flask import current_app, jsonify, request
from sqlalchemy import text

from app.auth import requiere_pin_admin
from app.estado_json import actualizar as _json_actualizar, cargar as _json_cargar
from app.routes.base import bp, db, error_interno
from repositories.maquina_repository import MaquinaRepository

TIPO_CAPTURA_MAQUINA = 'maquina'
SEGUNDOS_CAPTURA_MAQUINA = 45

_MATRICULA_VALIDA = re.compile(r'[A-Z0-9Ñ][A-Z0-9Ñ ._/-]{0,39}')


def validar_matricula(crudo, excluir_id=None):
    """(matricula normalizada, error). Vacía es válida: la máquina aún no tiene."""
    matricula = re.sub(r'\s+', ' ', str(crudo or '')).strip().upper()
    if not matricula:
        return '', None
    if not _MATRICULA_VALIDA.fullmatch(matricula):
        return None, ('La matrícula solo admite letras, números, espacios y . _ / - '
                      '(máximo 40 caracteres)')
    ocupada = MaquinaRepository(db).matricula_ocupada(matricula, excluir_id)
    if ocupada:
        return None, f'La matrícula {matricula} ya está en la máquina "{ocupada}"'
    return matricula, None


def validar_inspeccion(crudo):
    """(fecha AAAA-MM-DD, error). Vacía es válida: aún no se ha anotado."""
    fecha = str(crudo or '').strip()
    if not fecha:
        return '', None
    try:
        return datetime.strptime(fecha, '%Y-%m-%d').strftime('%Y-%m-%d'), None
    except ValueError:
        return None, 'La fecha de validez de la inspección no es correcta'


@bp.route('/api/maquinas/<maquina_id>/inspeccion', methods=['GET'])
def api_maquina_inspeccion(maquina_id):
    """Lo que engastado pregunta al elegir máquina. Ver app/inspeccion.py."""
    from app import inspeccion
    try:
        with db.engine.connect() as conn:
            return jsonify({'success': True, **inspeccion.estado_maquina(conn, maquina_id)})
    except Exception as e:
        return error_interno(e, 'Error al consultar la inspección')


# ==================== ETIQUETA: ALTA DESDE GESTIÓN DE PUESTOS ====================

def _lector_listo(device_id):
    """Online y con el firmware al día: con uno viejo la placa no atiende capturas
    y la etiqueta se tomaría por una tarjeta de operario."""
    from app.routes.sistema import _rfid_firmware_version, _rfid_load_devices
    lector = (_rfid_load_devices() or {}).get(device_id) or {}
    try:
        visto = datetime.fromisoformat(lector.get('last_seen', ''))
    except (TypeError, ValueError):
        return False, 'El lector no está conectado'
    if (datetime.now() - visto).total_seconds() >= 90:
        return False, 'El lector no está conectado'
    version = _rfid_firmware_version()
    if not version or lector.get('fw') != version:
        return False, 'Actualiza el firmware del lector antes de registrar etiquetas'
    return True, None


@bp.route('/api/maquinas/<maquina_id>/rfid/captura', methods=['POST'])
@requiere_pin_admin
def api_maquina_rfid_captura_iniciar(maquina_id):
    """Arma un lector para que la siguiente etiqueta sea la de esta máquina."""
    datos = request.get_json(silent=True) or {}
    device_id = (datos.get('device_id') or '').strip().lower()[:64]
    if not device_id:
        return jsonify({'success': False, 'error': 'Selecciona un lector RFID'}), 400
    try:
        if not MaquinaRepository(db).obtener_maquina(maquina_id):
            return jsonify({'success': False, 'error': 'Máquina no encontrada'}), 404
        listo, motivo = _lector_listo(device_id)
        if not listo:
            return jsonify({'success': False, 'error': motivo}), 409

        token = uuid.uuid4().hex
        expira_at = (datetime.now() + timedelta(seconds=SEGUNDOS_CAPTURA_MAQUINA)).isoformat()
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
                  'tipo': TIPO_CAPTURA_MAQUINA, 'ref': maquina_id})
        return jsonify({'success': True, 'token': token, 'segundos': SEGUNDOS_CAPTURA_MAQUINA})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/maquinas/<maquina_id>/rfid/captura/<token>', methods=['GET', 'DELETE'])
@requiere_pin_admin
def api_maquina_rfid_captura_estado(maquina_id, token):
    """Consulta o cancela la captura de la etiqueta de una máquina."""
    from app.routes.operarios import _captura_tag_expirada, _captura_tag_resultado
    try:
        with db.engine.begin() as conn:
            fila = conn.execute(text("""
                SELECT device_id, token, estado, uid, mensaje, expira_at
                FROM operario_tag_capturas
                WHERE token = :t AND tipo = :tipo AND ref = :ref
            """), {'t': token, 'tipo': TIPO_CAPTURA_MAQUINA, 'ref': maquina_id}).mappings().first()
            if not fila:
                return jsonify({'success': False, 'error': 'Captura no encontrada'}), 404
            estado, mensaje = fila['estado'], fila['mensaje']
            if request.method == 'DELETE' and estado == 'armada':
                estado, mensaje = 'cancelada', 'Captura cancelada'
                _captura_tag_resultado(conn, fila, estado, mensaje)
            elif estado == 'armada' and _captura_tag_expirada(fila):
                estado, mensaje = 'caducada', 'Se agotó el tiempo para pasar la etiqueta'
                _captura_tag_resultado(conn, fila, estado, mensaje)
            return jsonify({'success': True, 'estado': estado, 'uid': fila['uid'], 'mensaje': mensaje})
    except Exception as e:
        return error_interno(e)


def resolver_captura_maquina(conn, fila, uid):
    """La placa ha leído una etiqueta con una captura de máquina armada. Lo llama
    operarios.py:api_esp32_operario_captura_resultado. Devuelve (respuesta, status)."""
    from app.routes.operarios import _captura_tag_resultado, _maquina_por_tag, _operario_por_tag

    def _error(mensaje):
        _captura_tag_resultado(conn, fila, 'error', mensaje, uid)
        return {'success': False, 'error': mensaje}, 409

    maquina = conn.execute(text(
        "SELECT id, nombre, matricula, tag_uid FROM maquinas WHERE id = :id AND activo = 1"
    ), {'id': fila['ref']}).mappings().first()
    if not maquina:
        return _error('La máquina ya no está activa')
    op = _operario_por_tag(conn, uid)
    if op:
        return _error(f'Esa es la tarjeta de "{op[1]}"')
    otra = _maquina_por_tag(conn, uid)
    if otra and otra['id'] != maquina['id']:
        return _error(f'Esa etiqueta ya está en la máquina "{otra["nombre"]}"')
    conn.execute(text("UPDATE maquinas SET tag_uid = :uid, updated_at = datetime('now') WHERE id = :id"),
                 {'uid': uid, 'id': maquina['id']})
    _actualizar_canales_de_maquina(conn, maquina, uid)
    _captura_tag_resultado(conn, fila, 'asignada', 'Etiqueta asignada', uid)
    return {'success': True, 'uid': uid, 'operario': maquina['matricula'] or maquina['nombre']}, 200


@bp.route('/api/maquinas/<maquina_id>/rfid', methods=['DELETE'])
@requiere_pin_admin
def api_maquina_rfid_quitar(maquina_id):
    """Quita la etiqueta de una máquina."""
    try:
        with db.engine.begin() as conn:
            maquina = conn.execute(text(
                "SELECT id, nombre, tag_uid FROM maquinas WHERE id = :id AND activo = 1"
            ), {'id': maquina_id}).mappings().first()
            conn.execute(text("UPDATE maquinas SET tag_uid = NULL, updated_at = datetime('now') WHERE id = :id"),
                         {'id': maquina_id})
            if maquina:
                _actualizar_canales_de_maquina(conn, maquina, None)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


# ==================== HERENCIA EN EL PICK-TO-LIGHT ====================
#
# La etiqueta se registra una vez, en la máquina. Un canal de herramienta del PTL
# la hereda en su uid_rfid, y se enlaza con la máquina por el nombre, igual que
# verificarMaquinaPtl (v3-gavetas.js) al elegirla. Una etiqueta que Admin haya
# puesto a mano en el canal, distinta de la de la máquina, no se pisa.

def _maquina_del_canal(conn, puesto_id, codigo):
    """Máquina de una herramienta del PTL: la del puesto y, si allí no hay, la única
    con ese nombre (las manuales se mueven). None si no hay o es ambiguo."""
    filas = conn.execute(text("""
        SELECT id, puesto_id, tag_uid FROM maquinas
        WHERE activo = 1 AND SUBSTR(TRIM(nombre), 1, 40) = :codigo
    """), {'codigo': codigo}).mappings().all()
    candidatas = [f for f in filas if f['puesto_id'] == puesto_id] or filas
    return candidatas[0] if len(candidatas) == 1 else None


def _uid_en_otro_canal(conn, uid, puesto_id, canal):
    return conn.execute(text("""
        SELECT puesto_id, canal, terminal_codigo FROM pick_to_light_canales
        WHERE (uid_rfid = :uid OR uid_rfid_2 = :uid) AND activo = 1
          AND NOT (puesto_id = :puesto_id AND canal = :canal)
    """), {'uid': uid, 'puesto_id': puesto_id, 'canal': canal}).first()


def heredar_etiqueta_en_canal(puesto_id, canal, codigo):
    """Da al canal recién asignado la etiqueta que ya tiene su máquina.

    Devuelve (uid heredado o None, aviso o None). No hace falta pasar la etiqueta
    otra vez; si ya está en otro canal no se copia, porque un UID solo puede estar
    en uno, y el aviso lo dice.
    """
    with db.engine.begin() as conn:
        actual = conn.execute(text("""
            SELECT uid_rfid FROM pick_to_light_canales
            WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
        """), {'puesto_id': puesto_id, 'canal': canal}).first()
        if not actual or actual[0]:
            return None, None
        maquina = _maquina_del_canal(conn, puesto_id, codigo)
        if not maquina or not maquina['tag_uid']:
            return None, None
        uid = maquina['tag_uid']
        choque = _uid_en_otro_canal(conn, uid, puesto_id, canal)
        if choque:
            return None, ('La etiqueta de la máquina ya está en el canal %d (%s). Quítala de '
                          'allí para usarla en este canal.' % (choque[1], choque[2]))
        conn.execute(text("""
            UPDATE pick_to_light_canales SET uid_rfid = :uid, updated_at = datetime('now')
            WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
        """), {'uid': uid, 'puesto_id': puesto_id, 'canal': canal})
        return uid, None


def _actualizar_canales_de_maquina(conn, maquina, uid_nuevo):
    """La etiqueta de la máquina ha cambiado o se ha quitado: su canal no puede
    seguir pidiendo la vieja. Solo toca canales vacíos o con la etiqueta anterior."""
    codigo = (maquina['nombre'] or '').strip()[:40]
    canales = conn.execute(text("""
        SELECT puesto_id, canal, uid_rfid FROM pick_to_light_canales
        WHERE tipo = 'herramienta' AND activo = 1 AND terminal_codigo = :codigo
    """), {'codigo': codigo}).mappings().all()
    for c in canales:
        if c['uid_rfid'] and c['uid_rfid'] != maquina['tag_uid']:
            continue
        suya = _maquina_del_canal(conn, c['puesto_id'], codigo)
        if not suya or suya['id'] != maquina['id']:
            continue
        if uid_nuevo and _uid_en_otro_canal(conn, uid_nuevo, c['puesto_id'], c['canal']):
            continue
        conn.execute(text("""
            UPDATE pick_to_light_canales SET uid_rfid = :uid, updated_at = datetime('now')
            WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
        """), {'uid': uid_nuevo, 'puesto_id': c['puesto_id'], 'canal': c['canal']})


# ==================== LECTURA EN EL PUESTO ====================

def _lecturas_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(
        os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'rfid_maquina_lecturas.json')


def registrar_lectura(puesto_id, maquina_id):
    """Apunta la última máquina que ha pasado por el lector de ese puesto."""
    def _apuntar(lecturas):
        lecturas[puesto_id] = {'maquina_id': maquina_id, 'ts': datetime.now().isoformat()}
        return lecturas
    _json_actualizar(_lecturas_file(), {}, _apuntar)


@bp.route('/api/puestos/<puesto_id>/maquina-leida', methods=['GET'])
def api_puesto_maquina_leida(puesto_id):
    """Lo que sondea engastado mientras espera una máquina. Responde siempre 200.

    Query: since = 'ahora' de una respuesta anterior; solo cuentan las lecturas
    posteriores, para que la de hace un rato no elija máquina sola. Sin since no
    devuelve lectura: es la primera llamada, la que fija el punto de partida.
    """
    from app.routes.pick_to_light import _placa_del_puesto, _placa_en_contacto
    try:
        device_id, _ = _placa_del_puesto(puesto_id)
        activo = _placa_en_contacto(device_id)
        respuesta = {
            'success': True,
            'activo': activo,
            'motivo': None if activo else ('El lector del puesto no responde' if device_id
                                           else 'Este puesto no tiene lector'),
            'ahora': datetime.now().isoformat(),
            'lectura': None,
        }
        since = (request.args.get('since') or '').strip()
        lectura = (_json_cargar(_lecturas_file(), {}) or {}).get(puesto_id)
        if since and lectura and (lectura.get('ts') or '') > since:
            repo = MaquinaRepository(db)
            maquina = repo.obtener_maquina(lectura.get('maquina_id'))
            if maquina:
                maquina['terminales_asignados'] = repo.obtener_terminales_asignados(maquina['id'])
                respuesta['lectura'] = {'ts': lectura['ts'], 'maquina': maquina}
        return jsonify(respuesta)
    except Exception as e:
        return error_interno(e, 'Error al consultar la máquina leída')
