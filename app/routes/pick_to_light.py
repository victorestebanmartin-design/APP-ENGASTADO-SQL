"""
Pick-to-light de gavetas: enciende la luz del cajon del terminal elegido.

El operario elige un terminal en engastado y se le enciende en verde el LED de
su gaveta; al sacarla, la placa lo confirma y la app le muestra los paquetes.
El hardware cuelga de la MISMA ESP32 del lector RFID del puesto (esquema en
esp32/HARDWARE_PICK_TO_LIGHT.md), asi que aqui no hay ningun tipo de
dispositivo nuevo: se reaprovecha el registro de Admin -> Lectores RFID.

Dos decisiones que explican la forma de este fichero:

- **El servidor EMPUJA a la placa**, no al reves. La luz tiene que encenderse
  en el mismo gesto del dedo, y la IP de cada placa ya la conoce el servidor
  por el latido del OTA. De paso, si la placa no contesta se sabe al instante
  y la app puede seguir sin luz en vez de esperar a un sondeo.

- **Nada de esto puede bloquear al operario.** Sin gaveta, sin lector asignado
  o con la placa desenchufada, todos los endpoints responden 200 con
  `activo: False` y un motivo legible. Un 500 aqui pararia el trabajo por una
  bombilla.
"""
import http.client
import json
import os
import uuid
from datetime import datetime

from flask import request, jsonify, current_app
from sqlalchemy import text

from app.auth import requiere_pin_admin
from app.estado_json import cargar, guardar, actualizar
from app.routes.base import bp, db, error_interno

PUERTO_PLACA = 80          # el mini servidor HTTP de esp32/lib/gavetas.py
TIMEOUT_PLACA = 1.5        # segundos: en LAN sobra, y un corte se nota ya
TIMEOUT_PLACA_PROBAR = 4.0 # 'probar' es una accion de admin sin prisa: la
                           # placa lee los expansores I2C antes de responder
                           # y eso a veces tarda mas que el timeout normal
RUTA_PLACA = '/gaveta'
MAX_EVENTOS_PUESTO = 20    # historial corto por puesto, para no crecer sin fin


# ==================== ESTADO COMPARTIDO ====================

def _estado_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(
        os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'pick_to_light_estado.json')


def _estado_cargar():
    return cargar(_estado_file(), {})


def _estado_guardar(estado):
    guardar(_estado_file(), estado)


def _estado_actualizar(fn):
    """read-modify-write atómico del estado del pick-to-light (todos los
    puestos). 'fn' recibe el dict {puesto_id: {...}} y lo modifica in situ."""
    return actualizar(_estado_file(), {}, fn)


# ==================== PRUEBAS POR SONDEO ====================
#
# Los comandos de prueba se empujan a la placa por su puerto 80, que es
# instantaneo pero solo funciona si el servidor puede abrir una conexion hacia
# su IP. Desde PythonAnywhere no puede: la placa vive en una IP privada y el
# intento muere con ConnectionRefusedError.
#
# Para ese caso el comando se deja aqui aparcado, la placa lo recoge en su
# sondeo (cada 750 ms) y devuelve el resultado por otra peticion. Es el mismo
# camino que ya usan encender/probar, pero de ida y vuelta: 'test_micros' no
# sirve de nada si no vuelve la lista de gavetas.
#
# Se guarda por device_id, no por puesto: mientras se prueba el cableado el
# lector puede no estar asignado a ningun puesto todavia.

def _test_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(
        os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'pick_to_light_test.json')


def _test_cargar():
    return cargar(_test_file(), {})


def _test_guardar(datos):
    guardar(_test_file(), datos)


def _test_encolar(device_id, comando):
    """Aparca un comando para que la placa lo recoja en su sondeo.

    Devuelve el numero de secuencia con el que preguntar por el resultado. El
    resultado anterior se borra: si no, el panel leeria el de la prueba de
    antes y diria que ya esta hecha.
    """
    seq_ref = {}

    def _encolar(todo):
        entrada = todo.get(device_id) or {}
        seq_ref['n'] = int(entrada.get('seq') or 0) + 1
        todo[device_id] = {'cmd': comando, 'seq': seq_ref['n']}
        return todo

    actualizar(_test_file(), {}, _encolar)
    return seq_ref['n']


# ==================== LA PLACA DEL PUESTO ====================

def _placa_del_puesto(puesto_id):
    """(device_id, ip) del lector RFID asignado a ese puesto, o (None, None).

    Lee el mismo registro que Admin -> Lectores RFID, para que asignar el
    lector a un puesto siga siendo el unico paso de configuracion.
    """
    from app.routes.sistema import _rfid_load_devices
    if not puesto_id:
        return None, None
    for device_id, dev in (_rfid_load_devices() or {}).items():
        if dev.get('puesto_id') == puesto_id:
            return device_id, (dev.get('ip') or '')
    return None, None


def _puesto_de_la_placa(device_id):
    from app.routes.sistema import _rfid_load_devices
    dev = (_rfid_load_devices() or {}).get(device_id) or {}
    return dev.get('puesto_id') or ''


def _enviar_a_placa_con_datos(ip, payload, timeout=TIMEOUT_PLACA_PROBAR):
    """Como _enviar_a_placa pero devuelve también el JSON de la respuesta.

    Usado por los endpoints de prueba de cableado, donde la respuesta de la
    placa contiene los datos de los micros o el estado del LED.
    """
    if not ip:
        return False, 'El lector todavía no ha dicho su IP', {}
    cuerpo = json.dumps(payload).encode('utf-8')
    conexion = None
    try:
        conexion = http.client.HTTPConnection(ip, PUERTO_PLACA, timeout=timeout)
        conexion.request('POST', RUTA_PLACA, body=cuerpo,
                         headers={'Content-Type': 'application/json'})
        respuesta = conexion.getresponse()
        datos = respuesta.read(4096)
        if respuesta.status != 200:
            return False, 'La placa respondió %d' % respuesta.status, {}
        try:
            parsed = json.loads(datos.decode('utf-8'))
        except Exception:
            parsed = {}
        if parsed.get('ok') is False:
            return False, parsed.get('error') or 'La placa rechazó la orden', parsed
        return True, '', parsed
    except Exception as e:
        current_app.logger.info('pick-to-light test: la placa %s no responde: %s', ip, e)
        return False, 'La placa no responde (%s)' % type(e).__name__, {}
    finally:
        if conexion is not None:
            try:
                conexion.close()
            except Exception:
                pass


def _resolver_placa_test(datos):
    """Devuelve (device_id, ip) para un comando de prueba.

    Acepta device_id o puesto_id: durante pruebas de cableado el lector puede
    no estar asignado todavía a ningún puesto.
    """
    device_id = (datos.get('device_id') or '').strip().lower()[:64]
    if device_id:
        from app.routes.sistema import _rfid_load_devices
        dev = (_rfid_load_devices() or {}).get(device_id) or {}
        return device_id, dev.get('ip') or ''
    puesto_id = (datos.get('puesto_id') or '').strip()[:24]
    return _placa_del_puesto(puesto_id)


def _enviar_a_placa(ip, payload, timeout=TIMEOUT_PLACA):
    """POST corto al mini servidor de la placa. Devuelve (ok, motivo).

    Nunca lanza: un fallo de red aqui significa "sin luz", no "peticion rota".
    """
    if not ip:
        return False, 'El lector de este puesto todavia no ha dicho su IP'
    cuerpo = json.dumps(payload).encode('utf-8')
    conexion = None
    try:
        conexion = http.client.HTTPConnection(ip, PUERTO_PLACA, timeout=timeout)
        conexion.request('POST', RUTA_PLACA, body=cuerpo,
                         headers={'Content-Type': 'application/json'})
        respuesta = conexion.getresponse()
        datos = respuesta.read(2048)
        if respuesta.status != 200:
            return False, 'La placa respondio %d' % respuesta.status
        try:
            parsed = json.loads(datos.decode('utf-8'))
        except Exception:
            parsed = {}
        if parsed.get('ok') is False:
            return False, parsed.get('error') or 'La placa rechazo la orden'
        return True, ''
    except Exception as e:
        current_app.logger.info('pick-to-light: la placa %s no responde: %s', ip, e)
        return False, 'La placa de las gavetas no responde'
    finally:
        if conexion is not None:
            try:
                conexion.close()
            except Exception:
                pass


def _puesto_del_terminal(terminal):
    """Puesto al que pertenece un terminal, via su maquina.

    Sirve para que gestion de puestos pueda probar una gaveta sin tener que
    saberse el puesto: el terminal ya lo dice.
    """
    row = db.session.execute(text("""
        SELECT m.puesto_id
        FROM maquinas_terminales mt
        JOIN maquinas m ON m.id = mt.maquina_id
        WHERE mt.terminal_codigo = :codigo AND mt.activo = 1
        LIMIT 1
    """), {'codigo': terminal}).fetchone()
    return row[0] if row else ''



# ==================== CANALES PICK-TO-LIGHT (por puesto) ====================
#
# pick_to_light_canales sustituye a la vieja terminales_gavetas: una fila por
# (puesto, canal) en vez de por terminal solo, porque el LED 1 del puesto A y
# el LED 1 del puesto B son dos cajones fisicos completamente distintos (cada
# placa tiene su propia numeracion 1..N). 'activo' en vez de borrar de verdad
# conserva historico sin que el indice UNIQUE de fila activa lo bloquee.
#
# ESTA es la unica tabla desde la que se escribe la asignacion terminal ->
# gaveta -> LED -> RFID. La ficha de Terminales (app/routes/puestos.py) solo
# lee de aqui para mostrarla; no tiene ningun PUT/DELETE propio.

def _canales_del_puesto(puesto_id):
    """{canal: {'terminal':..., 'gaveta':..., 'uid_rfid':...}} activos de este puesto."""
    if not puesto_id:
        return {}
    filas = db.session.execute(text("""
        SELECT canal, terminal_codigo, etiqueta_gaveta, uid_rfid
        FROM pick_to_light_canales
        WHERE puesto_id = :puesto_id AND activo = 1
    """), {'puesto_id': puesto_id}).fetchall()
    return {fila[0]: {'terminal': fila[1], 'gaveta': fila[2], 'uid_rfid': fila[3]} for fila in filas}


def _gavetas_validas_del_puesto(puesto_id):
    """LEDs con un terminal de verdad detras, entre los de este puesto.

    Un expansor MCP23017 trae 16 canales aunque solo se haya cableado un
    microinterruptor: los que faltan quedan flotando con el pull-up interno y
    leen "abierto" todo el rato. Sin esta lista la placa los confundiria con
    gavetas robadas. Con ella, cualquier canal que no sea el numero de LED de
    algun terminal de este puesto es ruido del expansor y se ignora.
    """
    return sorted(_canales_del_puesto(puesto_id).keys())


def _canal_del_terminal_en_puesto(terminal, puesto_id):
    """(canal, etiqueta_gaveta, uid_rfid) del terminal EN ESE puesto, o (None, None, None).

    Buscar por (puesto, terminal) y no solo por terminal es lo que evita que
    un terminal con el mismo codigo asignado (por error) en dos puestos a la
    vez encienda la placa equivocada.
    """
    if not terminal or not puesto_id:
        return None, None, None
    row = db.session.execute(text("""
        SELECT canal, etiqueta_gaveta, uid_rfid FROM pick_to_light_canales
        WHERE puesto_id = :puesto_id AND terminal_codigo = :terminal AND activo = 1
    """), {'puesto_id': puesto_id, 'terminal': terminal}).fetchone()
    if not row:
        return None, None, None
    return row[0], row[1], row[2]


def _maquina_del_terminal_en_puesto(terminal, puesto_id):
    """True si el terminal esta asignado a alguna maquina de ESE puesto."""
    row = db.session.execute(text("""
        SELECT 1 FROM maquinas_terminales mt
        JOIN maquinas m ON m.id = mt.maquina_id
        WHERE mt.terminal_codigo = :terminal AND mt.activo = 1 AND m.puesto_id = :puesto_id
        LIMIT 1
    """), {'terminal': terminal, 'puesto_id': puesto_id}).fetchone()
    return row is not None


def _normalizar_uid(bruto):
    """Mayusculas, sin espacios ni separadores: mismo formato en firmware,
    API y SQLite para que una comparacion de cadenas baste."""
    if not bruto:
        return ''
    return ''.join(str(bruto).split()).upper().replace(':', '').replace('-', '')


def asignar_canal(puesto_id, canal, terminal, etiqueta):
    """Valida y guarda una asignacion de canal. Devuelve (ok, error_o_None).

    Comparte esta funcion la API interactiva y la importacion masiva del
    kanban: las mismas reglas tienen que cumplirse vengan de donde vengan.
    """
    from app.routes.puestos import LED_GAVETA_MAX
    if not puesto_id:
        return False, 'Falta el puesto'
    if not 1 <= canal <= LED_GAVETA_MAX:
        return False, 'El canal tiene que estar entre 1 y %d' % LED_GAVETA_MAX
    if not terminal:
        return False, 'Falta el terminal'
    etiqueta = (etiqueta or '').strip()[:80]
    if not etiqueta:
        return False, 'La etiqueta de la gaveta no puede estar vacía'

    from app.routes.sistema import _rfid_load_devices
    device_id, _ = _placa_del_puesto(puesto_id)
    if device_id:
        dev = (_rfid_load_devices() or {}).get(device_id) or {}
        total = int(dev.get('gavetas') or 0)
        if total and canal > total:
            return False, 'El canal %d no existe: esta placa solo tiene %d' % (canal, total)

    if not _maquina_del_terminal_en_puesto(terminal, puesto_id):
        return False, ('El terminal %s no pertenece a ninguna máquina de este puesto' % terminal)

    ocupante_canal = db.session.execute(text("""
        SELECT terminal_codigo FROM pick_to_light_canales
        WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
    """), {'puesto_id': puesto_id, 'canal': canal}).fetchone()
    if ocupante_canal and ocupante_canal[0] != terminal:
        return False, 'El canal %d ya lo usa el terminal %s en este puesto' % (canal, ocupante_canal[0])

    ocupante_terminal = db.session.execute(text("""
        SELECT canal FROM pick_to_light_canales
        WHERE puesto_id = :puesto_id AND terminal_codigo = :terminal AND activo = 1
    """), {'puesto_id': puesto_id, 'terminal': terminal}).fetchone()
    if ocupante_terminal and ocupante_terminal[0] != canal:
        return False, ('El terminal %s ya está en el canal %d de este puesto'
                       % (terminal, ocupante_terminal[0]))

    db.session.execute(text("""
        INSERT INTO pick_to_light_canales (puesto_id, canal, terminal_codigo, etiqueta_gaveta, activo)
        VALUES (:puesto_id, :canal, :terminal, :etiqueta, 1)
        ON CONFLICT(puesto_id, canal) WHERE activo = 1 DO UPDATE
            SET terminal_codigo = excluded.terminal_codigo,
                etiqueta_gaveta = excluded.etiqueta_gaveta,
                updated_at      = datetime('now')
    """), {'puesto_id': puesto_id, 'canal': canal, 'terminal': terminal, 'etiqueta': etiqueta})
    db.session.commit()
    return True, None


def desasignar_canal(puesto_id, canal):
    """activo=0 en vez de borrar: conserva el historico de esa asignacion."""
    db.session.execute(text("""
        UPDATE pick_to_light_canales SET activo = 0, updated_at = datetime('now')
        WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
    """), {'puesto_id': puesto_id, 'canal': canal})
    db.session.commit()


@bp.route('/api/pick-to-light/canal', methods=['PUT'])
@requiere_pin_admin
def api_pick_to_light_asignar_canal():
    """Asigna o cambia el terminal de un canal fisico de un puesto.

    Unico sitio desde el que se escribe la asignacion terminal -> gaveta ->
    LED: la ficha de Terminales solo lee de aqui, nunca escribe.
    """
    try:
        datos = request.get_json(silent=True) or {}
        puesto_id = (datos.get('puesto_id') or '').strip()[:24]
        try:
            canal = int(datos.get('canal'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'El canal tiene que ser un número'}), 400
        terminal = (datos.get('terminal') or '').strip()[:40]
        etiqueta = (datos.get('etiqueta_gaveta') or '').strip()[:80]

        ok, error = asignar_canal(puesto_id, canal, terminal, etiqueta)
        if not ok:
            return jsonify({'success': False, 'message': error}), 400
        return jsonify({'success': True, 'puesto_id': puesto_id, 'canal': canal,
                        'terminal': terminal, 'etiqueta_gaveta': etiqueta})
    except Exception as e:
        return error_interno(e, 'Error al asignar el canal')


@bp.route('/api/pick-to-light/canal', methods=['DELETE'])
@requiere_pin_admin
def api_pick_to_light_desasignar_canal():
    try:
        puesto_id = (request.args.get('puesto_id') or '').strip()[:24]
        try:
            canal = int(request.args.get('canal'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'El canal tiene que ser un número'}), 400
        if not puesto_id:
            return jsonify({'success': False, 'message': 'Falta el puesto'}), 400

        desasignar_canal(puesto_id, canal)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al desasignar el canal')


# ==================== ALTA DE RFID POR CANAL (admin) ====================
#
# Las etiquetas RFID de gaveta se leen con el MISMO PN532 que ya usa el
# lector para el login de operarios: no hay hardware nuevo, hay que saber
# distinguir una lectura de la otra. La placa arma un "modo" (armado aqui, en
# el servidor) para la SIGUIENTE tarjeta que pase; mientras no este armado,
# el lector se comporta exactamente igual que siempre (login normal).
#
# El armado viaja por el mismo canal de comandos de prueba por sondeo
# (_test_encolar/_test_cargar) que ya usan test_led/test_micros: la placa lo
# recoge en su sondeo de /api/esp32/rfid/gaveta/orden (cada 750 ms) y activa
# el modo durante RFID_ARMADO_DURACION_MS. Un solo tiro: la propia placa lo
# desarma en cuanto lee una tarjeta, o solo si pasa el tiempo sin que nadie
# acerque nada.

RFID_ARMADO_DURACION_MS = 30_000   # "20-30 segundos" pedido: admin de pie delante del lector
# El modo de VERIFICACION (orden productiva) dura lo que un operario tarda en
# elegir el terminal, ir a por la gaveta y acercarla al lector: no puede ir
# por el canal de comandos de un solo tiro (_test_encolar), porque ESE mismo
# canal es el que usa /api/esp32/rfid/gaveta/orden para la orden de LED de
# cada puesto, y un comando ahi pendiente le roba el turno al 'led' normal en
# cuanto el sondeo lo ve (ver api_pick_to_light_orden). En vez de eso,
# 'rfid_modo' se calcula solo de lo que ya hay en el estado (uid_esperado +
# rfid_confirmado) y se manda en CADA sondeo junto al 'led': el propio
# lector_puesto.py lo va sincronizando solo, poll a poll, sin comandos sueltos
# que haya que acordarse de desarmar.


def _rfid_modo_de(actual):
    """rfid_modo que le toca mandar a la placa en el sondeo, o None."""
    if actual.get('uid_esperado') and not actual.get('rfid_confirmado'):
        return {'canal': actual.get('led'), 'orden_id': actual.get('orden_id')}
    return None


def _registrar_incidencia(puesto_id, canal, terminal, tipo, detalle=None):
    """Historial de incidencias de Pick-to-Light (RFID incorrecto/bypass/
    timeout, canal cruzado en la prueba guiada, micro sin respuesta...).

    Trazabilidad, no control de flujo: un fallo aqui nunca debe tumbar la
    peticion que lo origino.
    """
    try:
        db.session.execute(text("""
            INSERT INTO pick_to_light_incidencias (puesto_id, canal, terminal_codigo, tipo, detalle)
            VALUES (:puesto_id, :canal, :terminal, :tipo, :detalle)
        """), {'puesto_id': puesto_id, 'canal': canal, 'terminal': terminal,
              'tipo': tipo, 'detalle': detalle})
        db.session.commit()
    except Exception as e:
        current_app.logger.warning('No se pudo registrar incidencia PTL (%s): %s', tipo, e)


def _rfid_armado_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(
        os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'pick_to_light_rfid_armado.json')


def _rfid_armado_cargar():
    return cargar(_rfid_armado_file(), {})


def _rfid_armado_guardar(datos):
    guardar(_rfid_armado_file(), datos)


def _rfid_ocupante(uid, excluir_puesto=None, excluir_canal=None):
    """(puesto_id, canal, terminal) donde ya esta activo este UID, o None.

    'excluir_*' deja pasar la fila que se esta editando (cambiar la etiqueta
    de la MISMA gaveta no puede chocar consigo misma).
    """
    fila = db.session.execute(text("""
        SELECT puesto_id, canal, terminal_codigo FROM pick_to_light_canales
        WHERE uid_rfid = :uid AND activo = 1
    """), {'uid': uid}).fetchone()
    if not fila:
        return None
    if fila[0] == excluir_puesto and fila[1] == excluir_canal:
        return None
    return fila


@bp.route('/api/pick-to-light/canal/rfid/armar', methods=['POST'])
@requiere_pin_admin
def api_pick_to_light_rfid_armar():
    """Deja el lector del puesto a la espera de la PRÓXIMA tarjeta leída.

    No hace falta que el canal tenga ya un terminal asignado: se puede armar
    para identificar una etiqueta antes de decidir a qué gaveta va, aunque el
    flujo normal (Admin) primero asigna terminal y luego arma el RFID.
    """
    try:
        datos = request.get_json(silent=True) or {}
        puesto_id = (datos.get('puesto_id') or '').strip()[:24]
        try:
            canal = int(datos.get('canal'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'El canal tiene que ser un número'}), 400

        device_id, _ = _placa_del_puesto(puesto_id)
        if not device_id:
            return jsonify({'success': False, 'message': 'Este puesto no tiene lector asignado'}), 404

        seq = _test_encolar(device_id, {
            'ptl_rfid_modo': 'alta', 'canal': canal,
            'duracion_ms': RFID_ARMADO_DURACION_MS,
        })
        armado = _rfid_armado_cargar()
        armado[device_id] = {'puesto_id': puesto_id, 'canal': canal, 'seq': seq,
                             'uid': None, 'listo': False}
        _rfid_armado_guardar(armado)

        return jsonify({'success': True, 'device_id': device_id, 'seq': seq,
                        'segundos': RFID_ARMADO_DURACION_MS // 1000})
    except Exception as e:
        return error_interno(e, 'Error al armar la lectura RFID')


@bp.route('/api/pick-to-light/canal/rfid/armar', methods=['GET'])
@requiere_pin_admin
def api_pick_to_light_rfid_sondear():
    """Lo que sondea el panel de admin mientras espera a que se acerque la gaveta."""
    try:
        device_id = (request.args.get('device_id') or '').strip().lower()[:64]
        try:
            seq = int(request.args.get('seq') or 0)
        except (TypeError, ValueError):
            seq = 0
        entrada = (_rfid_armado_cargar().get(device_id) or {})
        listo = bool(seq and int(entrada.get('seq') or 0) == seq and entrada.get('listo'))
        return jsonify({'success': True, 'listo': listo,
                        'uid': entrada.get('uid') if listo else None})
    except Exception as e:
        return error_interno(e, 'Error al consultar la lectura RFID')


@bp.route('/api/pick-to-light/canal/rfid', methods=['PUT'])
@requiere_pin_admin
def api_pick_to_light_rfid_confirmar():
    """Confirma y guarda el UID leído para un canal que YA tiene terminal."""
    try:
        datos = request.get_json(silent=True) or {}
        puesto_id = (datos.get('puesto_id') or '').strip()[:24]
        try:
            canal = int(datos.get('canal'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'El canal tiene que ser un número'}), 400
        uid = _normalizar_uid(datos.get('uid'))
        if not uid:
            return jsonify({'success': False, 'message': 'Falta el UID leído'}), 400

        fila = db.session.execute(text("""
            SELECT terminal_codigo FROM pick_to_light_canales
            WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
        """), {'puesto_id': puesto_id, 'canal': canal}).fetchone()
        if not fila:
            return jsonify({'success': False,
                            'message': 'Asigna primero un terminal a este canal'}), 400

        choque = _rfid_ocupante(uid, excluir_puesto=puesto_id, excluir_canal=canal)
        if choque:
            return jsonify({'success': False,
                            'message': ('Este UID ya está asignado al canal %d (terminal %s) '
                                       'de otro puesto' % (choque[1], choque[2]))
                                       if choque[0] != puesto_id else
                                       ('Este UID ya está asignado al canal %d (terminal %s) '
                                       'de este mismo puesto' % (choque[1], choque[2]))}), 409

        db.session.execute(text("""
            UPDATE pick_to_light_canales SET uid_rfid = :uid, updated_at = datetime('now')
            WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
        """), {'uid': uid, 'puesto_id': puesto_id, 'canal': canal})
        db.session.commit()
        return jsonify({'success': True, 'uid': uid})
    except Exception as e:
        return error_interno(e, 'Error al guardar el RFID del canal')


@bp.route('/api/pick-to-light/canal/rfid', methods=['DELETE'])
@requiere_pin_admin
def api_pick_to_light_rfid_desvincular():
    try:
        puesto_id = (request.args.get('puesto_id') or '').strip()[:24]
        try:
            canal = int(request.args.get('canal'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'El canal tiene que ser un número'}), 400

        db.session.execute(text("""
            UPDATE pick_to_light_canales SET uid_rfid = NULL, updated_at = datetime('now')
            WHERE puesto_id = :puesto_id AND canal = :canal AND activo = 1
        """), {'puesto_id': puesto_id, 'canal': canal})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al desvincular el RFID')


@bp.route('/api/esp32/rfid/gaveta/lectura', methods=['POST'])
def api_esp32_rfid_gaveta_lectura():
    """La placa manda una lectura RFID de GAVETA (alta o verificación).

    Nunca se confunde con el login de operarios: solo llega aquí cuando el
    servidor había armado el modo (ver /canal/rfid/armar) y la placa lo
    desarma sola tras una lectura, así que esto nunca compite con
    /api/esp32/rfid/entrada.
    """
    try:
        from app.routes.sistema import _esp32_device_id
        datos = request.get_json(silent=True) or {}
        device_id = _esp32_device_id(datos.get('device_id'))
        if not device_id:
            return jsonify({'success': False, 'message': 'Falta device_id'}), 400

        uid = _normalizar_uid(datos.get('uid'))
        tipo = (datos.get('tipo') or '').strip()[:20]
        if not uid:
            return jsonify({'success': False, 'ok': False, 'mensaje': 'Lectura vacía'}), 400

        if tipo == 'alta':
            armado = _rfid_armado_cargar()
            entrada = armado.get(device_id)
            if not entrada:
                # Se desarmo (caducidad/otra prueba) antes de que llegara la lectura.
                return jsonify({'success': True, 'ok': False,
                                'mensaje': 'La lectura llegó tarde, vuelve a pulsar "Asignar RFID"'})
            choque = _rfid_ocupante(uid, excluir_puesto=entrada.get('puesto_id'),
                                    excluir_canal=entrada.get('canal'))
            entrada['uid'] = uid
            entrada['listo'] = True
            armado[device_id] = entrada
            _rfid_armado_guardar(armado)
            if choque:
                return jsonify({'success': True, 'ok': False,
                                'mensaje': 'Esa etiqueta ya está en uso en otra gaveta'})
            return jsonify({'success': True, 'ok': True, 'mensaje': 'Leído: %s' % uid})

        if tipo == 'verificar':
            orden_id = (datos.get('orden_id') or '').strip()
            puesto_id = _puesto_de_la_placa(device_id)
            if not puesto_id:
                return jsonify({'success': True, 'ok': False, 'mensaje': 'Lector sin puesto'})

            actual = _estado_cargar().get(puesto_id) or {}
            # Del lector de OTRO puesto no puede llegar (device_id ya resuelve
            # el puesto), y una orden vieja (id distinto, o ya sin objetivo)
            # no puede confirmar la de ahora: por eso manda el orden_id, no
            # basta con que el puesto coincida.
            if not actual.get('led') or not orden_id or actual.get('orden_id') != orden_id:
                return jsonify({'success': True, 'ok': False,
                                'mensaje': 'Esta lectura ya no corresponde a ningún trabajo activo'})

            uid_esperado = actual.get('uid_esperado')
            if not uid_esperado:
                return jsonify({'success': True, 'ok': False, 'mensaje': 'Esta gaveta no lleva RFID'})

            correcto = uid == uid_esperado

            def _marcar(estado):
                act = estado.get(puesto_id) or {}
                # Revalida bajo el candado: entre la lectura de arriba y aqui
                # la orden puede haber cambiado.
                if not act.get('led') or act.get('orden_id') != orden_id:
                    return estado
                if correcto:
                    act['rfid_confirmado'] = True
                    act['uid_incorrecto'] = None
                else:
                    act['uid_incorrecto'] = uid
                estado[puesto_id] = act
                return estado

            _estado_actualizar(_marcar)

            if not correcto:
                _registrar_incidencia(puesto_id, actual.get('led'), actual.get('terminal'),
                                      'rfid_incorrecto', 'esperado=%s leido=%s' % (uid_esperado, uid))
                return jsonify({'success': True, 'ok': False,
                                'mensaje': 'La etiqueta leída no corresponde a la gaveta esperada'})
            # UID correcto: se guarda como validado aunque el micro correcto
            # aun no se haya abierto (puede llegar antes); la confirmacion
            # final la decide _calcular_estado_orden con las dos cosas.
            return jsonify({'success': True, 'ok': True, 'mensaje': 'Gaveta verificada'})

        return jsonify({'success': True, 'ok': False, 'mensaje': 'Modo no soportado'}), 400
    except Exception as e:
        return error_interno(e, 'Error al procesar la lectura RFID')


def _backend_pythonanywhere():
    """True si el servidor no puede abrir conexiones a las IP privadas."""
    host = (request.host or '').split(':', 1)[0].lower()
    return host.endswith('.pythonanywhere.com')


def _parsear_intrusas(crudo):
    """'3,5' -> [3, 5]. Lista de gavetas abiertas que no tocaban."""
    numeros = []
    for trozo in (crudo or '').split(',')[:64]:
        trozo = trozo.strip()
        if not trozo:
            continue
        try:
            numeros.append(int(trozo))
        except ValueError:
            continue
    return sorted(set(numeros))


# ==================== API PARA LA APP ====================

@bp.route('/api/pick-to-light/encender', methods=['POST'])
def api_pick_to_light_encender():
    """Enciende la gaveta del terminal elegido en el puesto indicado.

    Responde SIEMPRE 200. 'activo' dice si hay luz de verdad; cuando es False,
    'motivo' explica por que, para poder enseñarlo sin dejar a nadie parado.
    """
    try:
        datos = request.get_json(silent=True) or {}
        puesto_id = (datos.get('puesto_id') or '').strip()[:24]
        terminal = (datos.get('terminal') or '').strip()[:40]

        if not puesto_id or not terminal:
            return jsonify({'success': True, 'activo': False,
                            'motivo': 'Falta el puesto o el terminal'})

        led, gaveta, uid_rfid = _canal_del_terminal_en_puesto(terminal, puesto_id)
        if not led:
            return jsonify({'success': True, 'activo': False, 'gaveta': gaveta,
                            'motivo': 'El terminal %s no tiene gaveta con luz en este puesto' % terminal})

        device_id, ip = _placa_del_puesto(puesto_id)
        if not device_id:
            return jsonify({'success': True, 'activo': False, 'gaveta': gaveta, 'led': led,
                            'motivo': 'Este puesto no tiene lector asignado en Admin'})

        validas = _gavetas_validas_del_puesto(puesto_id)
        ok, motivo = _enviar_a_placa(ip, {'led': led, 'terminal': terminal, 'validas': validas})

        # Cada encendido es una orden nueva: el orden_id es lo que evita que
        # una lectura RFID tardia de la orden ANTERIOR (p.ej. el operario tapa
        # la etiqueta ya con el terminal siguiente elegido) confirme algo que
        # no toca. Si esta gaveta lleva RFID, /orden ira mandando el modo de
        # verificacion en cada sondeo mientras 'rfid_confirmado' siga a False
        # (ver _rfid_modo_de); si no lleva, no se manda nada.
        orden_id = uuid.uuid4().hex[:12]

        # Se apunta la peticion aunque la placa no conteste: asi el sondeo del
        # navegador sabe que ya no espera nada de un terminal anterior.
        def _set(estado):
            estado[puesto_id] = {'led': led, 'terminal': terminal, 'gaveta': gaveta,
                                 'recogida': False, 'devuelta': False, 'validas': validas,
                                 'error_led': None, 'intrusas': [], 'eventos': [],
                                 'orden_id': orden_id, 'uid_esperado': uid_rfid,
                                 'rfid_confirmado': False, 'uid_incorrecto': None}
            return estado
        _estado_actualizar(_set)

        remoto = not ok and _backend_pythonanywhere()
        return jsonify({'success': True, 'activo': ok or remoto, 'led': led, 'gaveta': gaveta,
                'rfid': bool(uid_rfid),
                'motivo': ('La placa recibirá la orden por sondeo.' if remoto else motivo)})
    except Exception as e:
        return error_interno(e, 'Error al encender la gaveta')


@bp.route('/api/pick-to-light/apagar', methods=['POST'])
def api_pick_to_light_apagar():
    """Apaga todas las luces del puesto (terminal terminado o cambiado)."""
    try:
        datos = request.get_json(silent=True) or {}
        puesto_id = (datos.get('puesto_id') or '').strip()[:24]
        if not puesto_id:
            return jsonify({'success': True, 'activo': False, 'motivo': 'Falta el puesto'})

        device_id, ip = _placa_del_puesto(puesto_id)
        ok = False
        if device_id:
            ok, _ = _enviar_a_placa(ip, {'apagar': True})

        def _borrar(estado):
            estado.pop(puesto_id, None)
            return estado
        _estado_actualizar(_borrar)

        return jsonify({'success': True, 'activo': ok})
    except Exception as e:
        return error_interno(e, 'Error al apagar las gavetas')


def _calcular_estado_orden(actual):
    """Estado de la orden en curso, calculado a partir de lo ya guardado
    (no se persiste aparte, para no tener dos fuentes de verdad).

    pendiente | esperando_micro | esperando_rfid | confirmada | rfid_incorrecto
    """
    if not actual.get('led'):
        return 'pendiente'
    if actual.get('uid_incorrecto'):
        return 'rfid_incorrecto'
    if not actual.get('recogida'):
        return 'esperando_micro'
    if actual.get('uid_esperado') and not actual.get('rfid_confirmado'):
        return 'esperando_rfid'
    return 'confirmada'


@bp.route('/api/pick-to-light/estado', methods=['GET'])
def api_pick_to_light_estado():
    """Lo que sondea el navegador mientras espera a que saquen la gaveta."""
    try:
        puesto_id = (request.args.get('puesto_id') or '').strip()[:24]
        actual = _estado_cargar().get(puesto_id) or {}
        return jsonify({
            'success': True,
            'led': actual.get('led'),
            'terminal': actual.get('terminal'),
            'gaveta': actual.get('gaveta'),
            'recogida': bool(actual.get('recogida')),
            'devuelta': bool(actual.get('devuelta')),
            'error_led': actual.get('error_led'),
            'intrusas': list(actual.get('intrusas') or []),
            'orden_id': actual.get('orden_id'),
            'uid_esperado': bool(actual.get('uid_esperado')),
            'rfid_confirmado': bool(actual.get('rfid_confirmado')),
            'uid_incorrecto': bool(actual.get('uid_incorrecto')),
            'estado': _calcular_estado_orden(actual),
        })
    except Exception as e:
        return error_interno(e, 'Error al consultar las gavetas')


@bp.route('/api/esp32/rfid/gaveta/orden', methods=['GET'])
def api_pick_to_light_orden():
    """Orden pendiente para el sondeo de una placa que está tras NAT.

    En planta el servidor puede abrir una conexión directa al lector. Desde
    PythonAnywhere no puede llegar a su IP privada, así que la propia placa
    consulta esta ruta y aplica la misma orden de forma local.

    De paso, la placa aprovecha este mismo sondeo (cada 750 ms, ver
    lector_puesto.py) para RECONFIRMAR el estado de la gaveta objetivo
    ('led'/'recogida'/'puesta' como query params). Los avisos inmediatos de
    /api/esp32/rfid/gaveta siguen existiendo por la latencia, pero son un
    POST suelto: si se pierden (un handshake TLS lento hacia PythonAnywhere,
    un corte de wifi de medio segundo), nadie los repite y la app se queda
    sin enterarse de que la sacaron o de que ya la han devuelto. El GET de
    aqui SÍ se repite solo cada 750 ms, así que confirmar también por este
    lado lo autocorrige sin depender de que un único intento llegue.
    """
    try:
        device_id = (request.args.get('device_id') or '').strip().lower()[:64]

        # Un comando de prueba manda sobre la gaveta de trabajo: quien lo ha
        # pedido esta delante del armario mirando que LED se enciende.
        pendiente = (_test_cargar().get(device_id) or {})
        if pendiente.get('cmd'):
            return jsonify({'success': True,
                            'test': pendiente['cmd'],
                            'test_seq': pendiente.get('seq')})

        puesto_id = _puesto_de_la_placa(device_id)

        try:
            led_reportado = int(request.args.get('led') or 0)
        except (TypeError, ValueError):
            led_reportado = 0
        arg_recogida = request.args.get('recogida') == '1'
        arg_puesta = request.args.get('puesta') == '1'
        intrusas = _parsear_intrusas(request.args.get('intrusas'))

        def _falta_reconfirmar(actual):
            if not actual or led_reportado != actual.get('led'):
                return False
            if arg_recogida and not actual.get('recogida'):
                return True
            if bool(actual.get('devuelta')) != arg_puesta:
                return True
            return list(actual.get('intrusas') or []) != intrusas

        def _reconfirmar(estado_todo):
            # La placa reconfirma en cada sondeo el estado de SU gaveta. Va bajo
            # el candado del fichero (via _estado_actualizar) para no pisar la
            # reconfirmacion simultanea de otra placa: son claves distintas del
            # mismo dict, pero el fichero se reescribe entero.
            actual = estado_todo.get(puesto_id) or {}
            if led_reportado != actual.get('led'):
                return estado_todo
            if arg_recogida and not actual.get('recogida'):
                actual['recogida'] = True
                actual['error_led'] = None
            if bool(actual.get('devuelta')) != arg_puesta:
                actual['devuelta'] = arg_puesta
            # La placa manda la lista ENTERA de gavetas abiertas que no tocan,
            # no un cambio suelto: asi el estado no se queda con una intrusa
            # fantasma si se perdio el aviso de que la devolvieron.
            if list(actual.get('intrusas') or []) != intrusas:
                actual['intrusas'] = intrusas
                actual['error_led'] = intrusas[0] if intrusas else None
            estado_todo[puesto_id] = actual
            return estado_todo

        estado_todo = _estado_cargar()
        if (puesto_id and led_reportado
                and _falta_reconfirmar(estado_todo.get(puesto_id) or {})):
            estado_todo = _estado_actualizar(_reconfirmar)

        estado = estado_todo.get(puesto_id) if puesto_id else None
        led = (estado or {}).get('led')
        return jsonify({'success': True,
                        'apagar': not bool(led),
                        'led': led,
                        'terminal': (estado or {}).get('terminal') or '',
                        'validas': (estado or {}).get('validas') or [],
                        'rfid_modo': _rfid_modo_de(estado or {})})
    except Exception as e:
        return error_interno(e, 'Error al consultar la orden de gaveta')


@bp.route('/api/esp32/rfid/gaveta/test-resultado', methods=['POST'])
def api_pick_to_light_test_resultado():
    """La placa devuelve lo que dio el comando de prueba que recogio sondeando.

    Sin esto el panel se quedaria esperando para siempre, y 'test_micros' no
    tendria por donde devolver que gavetas estan fuera.
    """
    try:
        datos = request.get_json(silent=True) or {}
        device_id = (datos.get('device_id') or '').strip().lower()[:64]
        if not device_id:
            return jsonify({'success': False, 'message': 'Falta device_id'}), 400

        todo = _test_cargar()
        entrada = todo.get(device_id) or {}
        try:
            seq = int(datos.get('seq') or 0)
        except (TypeError, ValueError):
            seq = 0

        # Un resultado de un comando anterior (la placa reintentando tarde) no
        # puede pisar al que el panel esta esperando ahora.
        if seq and seq == int(entrada.get('seq') or 0):
            entrada['resultado'] = datos.get('resultado') or {}
            entrada['resultado_seq'] = seq
            entrada['cmd'] = None      # ya ejecutado: no repetirlo en el sondeo
            todo[device_id] = entrada
            _test_guardar(todo)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al recoger el resultado de la prueba')


@bp.route('/api/pick-to-light/test/resultado', methods=['GET'])
@requiere_pin_admin
def api_ptl_test_resultado():
    """Lo que sondea el panel de admin mientras espera a la placa."""
    try:
        device_id = (request.args.get('device_id') or '').strip().lower()[:64]
        try:
            seq = int(request.args.get('seq') or 0)
        except (TypeError, ValueError):
            seq = 0
        entrada = (_test_cargar().get(device_id) or {})
        listo = seq and int(entrada.get('resultado_seq') or 0) == seq
        return jsonify({'success': True, 'listo': bool(listo),
                        'resultado': entrada.get('resultado') if listo else None})
    except Exception as e:
        return error_interno(e, 'Error al consultar el resultado de la prueba')


@bp.route('/api/pick-to-light/probar', methods=['POST'])
@requiere_pin_admin
def api_pick_to_light_probar():
    """Enciende un LED por su numero, para identificar cajones al montar."""
    try:
        datos = request.get_json(silent=True) or {}
        puesto_id = (datos.get('puesto_id') or '').strip()[:24]
        terminal = (datos.get('terminal') or '').strip()[:40]
        if not puesto_id and terminal:
            puesto_id = _puesto_del_terminal(terminal)
        apagar = bool(datos.get('apagar'))

        # Mismo criterio que al guardar la gaveta (app/routes/puestos.py): un
        # numero que no se podria guardar tampoco se manda a la placa.
        from app.routes.puestos import _led_gaveta_valido
        led, error_led = _led_gaveta_valido(datos.get('led'))
        if not apagar and (error_led or not led):
            return jsonify({'success': False,
                            'message': error_led or 'Falta el numero de gaveta'}), 400

        device_id, ip = _placa_del_puesto(puesto_id)
        if not device_id:
            mensaje = ('Este puesto no tiene lector asignado en Admin'
                       if puesto_id else
                       'El terminal %s no esta asignado a ninguna maquina, '
                       'asi que no se sabe en que puesto encender la gaveta' % terminal)
            return jsonify({'success': False, 'message': mensaje}), 404

        payload = {'apagar': True} if apagar else {'led': led}
        ok, motivo = _enviar_a_placa(ip, payload, timeout=TIMEOUT_PLACA_PROBAR)
        remoto = not ok and _backend_pythonanywhere()
        if not ok and not remoto:
            return jsonify({'success': False, 'message': motivo}), 502

        if remoto:
            def _prueba(estado):
                if apagar:
                    estado.pop(puesto_id, None)
                else:
                    estado[puesto_id] = {'led': led, 'terminal': '',
                                         'gaveta': 'Prueba LED %d' % led,
                                         'recogida': False, 'error_led': None, 'eventos': []}
                return estado
            _estado_actualizar(_prueba)
        return jsonify({'success': True,
                        'message': 'La placa recibirá la orden por sondeo.' if remoto else ''})
    except Exception as e:
        return error_interno(e, 'Error al probar la gaveta')


# ==================== MODO PRUEBA DE CABLEADO (admin) ====================

def _test_enviar(device_id, ip, comando, extra=None):
    """Manda un comando de prueba a la placa y arma la respuesta del panel.

    Primero se intenta el empuje directo, que es instantaneo. Si no se puede
    llegar a la placa (tipico desde PythonAnywhere: su IP es privada), el
    comando se aparca para el sondeo y el panel espera el resultado con
    /test/resultado en vez de dar un 502 que no se puede arreglar tocando
    la placa.
    """
    ok, motivo, respuesta = _enviar_a_placa_con_datos(ip, comando)
    if ok:
        salida = {'success': True, 'pendiente': False,
                  'estado': respuesta.get('estado')}
        for clave in (extra or ()):
            if clave in respuesta:
                salida[clave] = respuesta[clave]
        return jsonify(salida)

    seq = _test_encolar(device_id, comando)
    return jsonify({'success': True, 'pendiente': True, 'seq': seq,
                    'device_id': device_id,
                    'message': 'La placa recogerá la orden en su próximo sondeo.',
                    'motivo_directo': motivo})


@bp.route('/api/pick-to-light/test/led', methods=['POST'])
@requiere_pin_admin
def api_ptl_test_led():
    """Prueba: enciende un LED concreto con color libre (sin activar flujo normal).

    Acepta device_id o puesto_id; la placa entra en modo prueba y solo la
    desactiva test_fin o un corte de corriente. Sirve para identificar qué
    numero fisico corresponde a cada LED de la tira.
    """
    try:
        datos = request.get_json(silent=True) or {}
        try:
            led = int(datos.get('led') or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'LED no es un número'}), 400
        if not 1 <= led <= 128:
            return jsonify({'success': False, 'message': 'LED fuera de rango (1-128)'}), 400

        color = datos.get('color') or [180, 180, 180]
        device_id, ip = _resolver_placa_test(datos)
        if not device_id:
            return jsonify({'success': False, 'message': 'Lector no encontrado'}), 404

        return _test_enviar(device_id, ip, {'test_led': led, 'color': color})
    except Exception as e:
        return error_interno(e, 'Error al probar LED')


@bp.route('/api/pick-to-light/test/todos', methods=['POST'])
@requiere_pin_admin
def api_ptl_test_todos():
    """Prueba: enciende todos los LEDs con el color indicado."""
    try:
        datos = request.get_json(silent=True) or {}
        color = datos.get('color') or [60, 60, 60]
        device_id, ip = _resolver_placa_test(datos)
        if not device_id:
            return jsonify({'success': False, 'message': 'Lector no encontrado'}), 404

        return _test_enviar(device_id, ip, {'test_todos': True, 'color': color},
                            extra=('gavetas',))
    except Exception as e:
        return error_interno(e, 'Error al encender todos los LEDs')


@bp.route('/api/pick-to-light/test/micros', methods=['POST'])
@requiere_pin_admin
def api_ptl_test_micros():
    """Prueba: lee el estado de todos los micro-interruptores.

    Devuelve qué gavetas están fuera (contacto abierto) y cuáles puestas
    (contacto cerrado a masa). Con todas puestas: 'fuera' vacío, 'puestas'
    = lista completa 1..N. Sacar y poner una gaveta y releer confirma que
    ese micro y ese canal del MCP23017 están bien cableados.
    """
    try:
        datos = request.get_json(silent=True) or {}
        device_id, ip = _resolver_placa_test(datos)
        if not device_id:
            return jsonify({'success': False, 'message': 'Lector no encontrado'}), 404

        return _test_enviar(device_id, ip, {'test_micros': True},
                            extra=('fuera', 'puestas', 'total', 'canales_error'))
    except Exception as e:
        return error_interno(e, 'Error al leer micro-interruptores')


@bp.route('/api/pick-to-light/test/fin', methods=['POST'])
@requiere_pin_admin
def api_ptl_test_fin():
    """Prueba: sale del modo prueba y apaga todos los LEDs."""
    try:
        datos = request.get_json(silent=True) or {}
        device_id, ip = _resolver_placa_test(datos)
        if not device_id:
            return jsonify({'success': False, 'message': 'Lector no encontrado'}), 404

        return _test_enviar(device_id, ip, {'test_fin': True})
    except Exception as e:
        return error_interno(e, 'Error al salir del modo prueba')


# ==================== MAPA DE COBERTURA (admin) ====================

@bp.route('/api/pick-to-light/mapa', methods=['GET'])
@requiere_pin_admin
def api_pick_to_light_mapa():
    """Consola de un puesto: estado del lector + rejilla completa de canales.

    Acepta 'puesto_id' (flujo normal: elegir puesto primero) o 'device_id'
    (compatibilidad con el resto del panel, que ya trabaja con el lector).
    Solo la parte ESTATICA de cada canal (terminal/etiqueta/RFID): el estado
    en vivo (abierta/cerrada, error de expansor) lo trae ya el sondeo de
    /test/micros existente, que el panel cruza con esto en el navegador para
    no duplicar trafico hacia la placa.
    """
    try:
        from app.routes.sistema import _rfid_load_devices
        device_id = (request.args.get('device_id') or '').strip().lower()[:64]
        puesto_id_pedido = (request.args.get('puesto_id') or '').strip()[:24]

        devices = _rfid_load_devices() or {}
        dev = None
        if device_id:
            dev = devices.get(device_id)
        elif puesto_id_pedido:
            for did, d in devices.items():
                if d.get('puesto_id') == puesto_id_pedido:
                    device_id, dev = did, d
                    break
        if not dev:
            return jsonify({'success': False, 'message': 'Lector no encontrado'}), 404

        puesto_id = dev.get('puesto_id') or ''
        total = int(dev.get('gavetas') or 0)
        asignados = _canales_del_puesto(puesto_id) if puesto_id else {}
        canales = [{'canal': canal,
                    'terminal': (asignados.get(canal) or {}).get('terminal'),
                    'gaveta': (asignados.get(canal) or {}).get('gaveta'),
                    'rfid': bool((asignados.get(canal) or {}).get('uid_rfid'))}
                  for canal in range(1, total + 1)]

        # Terminales de las maquinas de este puesto que aun no tienen canal:
        # son los unicos que tiene sentido ofrecer al asignar uno nuevo.
        terminales_disponibles = []
        if puesto_id:
            asignados_ya = {info['terminal'] for info in asignados.values()}
            filas = db.session.execute(text("""
                SELECT DISTINCT mt.terminal_codigo, m.nombre
                FROM maquinas_terminales mt
                JOIN maquinas m ON m.id = mt.maquina_id
                WHERE m.puesto_id = :puesto_id AND mt.activo = 1
                ORDER BY mt.terminal_codigo
            """), {'puesto_id': puesto_id}).fetchall()
            terminales_disponibles = [{'terminal': fila[0], 'maquina': fila[1]}
                                      for fila in filas if fila[0] not in asignados_ya]

        online = False
        try:
            # Mismo margen (90s) que Admin -> Lectores RFID: el latido se
            # manda cada 60s, asi que un par de vueltas de margen evita
            # parpadeos de "sin contacto" por una peticion tardia suelta.
            online = (datetime.now() - datetime.fromisoformat(dev.get('last_seen', ''))
                     ).total_seconds() < 90
        except Exception:
            pass

        return jsonify({
            'success': True, 'device_id': device_id,
            'puesto_id': puesto_id, 'puesto_nombre': dev.get('puesto_nombre') or '',
            'dispositivo': {
                'nombre': dev.get('nombre') or '', 'ip': dev.get('ip') or '',
                'last_seen': dev.get('last_seen') or '', 'expansores': int(dev.get('expansores') or 0),
                'ptl_http': dev.get('ptl_http'), 'en_prueba': bool(dev.get('en_prueba')),
                'fw': dev.get('fw') or '', 'online': online,
            },
            'total_gavetas': total, 'canales': canales,
            'terminales_disponibles': terminales_disponibles,
        })
    except Exception as e:
        return error_interno(e, 'Error al construir el mapa de cobertura')


# ============ INFORME DE CORRESPONDENCIA LED-MICRO (admin) ============
#
# Solo diagnostico: la prueba guiada nunca toca terminales_gavetas sola. Se
# guarda unicamente el ULTIMO informe por placa, "de forma sencilla" como se
# pidio; si mas adelante hace falta historial, esto es lo primero a cambiar.

def _correspondencia_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(
        os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'pick_to_light_correspondencia.json')


def _correspondencia_cargar():
    return cargar(_correspondencia_file(), {})


def _correspondencia_guardar(datos):
    guardar(_correspondencia_file(), datos)


@bp.route('/api/pick-to-light/correspondencia/informe', methods=['POST'])
@requiere_pin_admin
def api_ptl_guardar_informe():
    """Guarda el ultimo informe de la prueba guiada LED-micro de esta placa."""
    try:
        from app.routes.sistema import _rfid_load_devices
        datos = request.get_json(silent=True) or {}
        device_id = (datos.get('device_id') or '').strip().lower()[:64]
        if not device_id:
            return jsonify({'success': False, 'message': 'Falta device_id'}), 400

        dev = (_rfid_load_devices() or {}).get(device_id) or {}
        informe = {
            'fecha': datetime.now().isoformat(),
            'device_id': device_id,
            'puesto_id': dev.get('puesto_id') or '',
            'puesto_nombre': dev.get('puesto_nombre') or '',
            'cancelado': bool(datos.get('cancelado')),
            'resumen': datos.get('resumen') or {},
            'detalle': datos.get('detalle') or [],
        }
        todo = _correspondencia_cargar()
        todo[device_id] = informe
        _correspondencia_guardar(todo)

        # Los cruces y las gavetas sin respuesta detectados en la prueba
        # guiada tambien cuentan como incidencia de trazabilidad, no solo
        # como fila del informe (que solo guarda el ultimo, este historial no).
        puesto_id = informe['puesto_id']
        for fila in informe['detalle']:
            if not isinstance(fila, dict):
                continue
            resultado = fila.get('resultado')
            if resultado == 'cruzado':
                _registrar_incidencia(puesto_id, fila.get('canal'), fila.get('terminal'),
                                      'canal_cruzado', 'abrio_canal=%s' % fila.get('abrio_canal'))
            elif resultado == 'sin_respuesta':
                _registrar_incidencia(puesto_id, fila.get('canal'), fila.get('terminal'),
                                      'micro_sin_respuesta')
        if informe['cancelado']:
            _registrar_incidencia(puesto_id, None, None, 'cancelacion', 'prueba de correspondencia')

        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al guardar el informe')


@bp.route('/api/pick-to-light/correspondencia/informe', methods=['GET'])
@requiere_pin_admin
def api_ptl_obtener_informe():
    """Ultimo informe guardado de esta placa, o None si nunca se hizo la prueba."""
    try:
        device_id = (request.args.get('device_id') or '').strip().lower()[:64]
        informe = _correspondencia_cargar().get(device_id) if device_id else None
        return jsonify({'success': True, 'informe': informe})
    except Exception as e:
        return error_interno(e, 'Error al obtener el informe')


# ==================== INCIDENCIAS (trazabilidad) ====================

INCIDENCIA_TIPOS = {'rfid_incorrecto', 'rfid_bypass', 'rfid_timeout',
                    'canal_cruzado', 'micro_sin_respuesta', 'cancelacion'}


@bp.route('/api/pick-to-light/incidencia', methods=['POST'])
def api_pick_to_light_incidencia():
    """El operario reporta un bypass o un timeout de RFID durante el trabajo.

    Sin pin de admin a propósito: la manda la pantalla de engastado, no
    Admin. El tipo va restringido a los conocidos para no llenar la tabla de
    basura si algo en el JS manda cualquier cosa.
    """
    try:
        datos = request.get_json(silent=True) or {}
        puesto_id = (datos.get('puesto_id') or '').strip()[:24]
        tipo = (datos.get('tipo') or '').strip()[:30]
        if tipo not in INCIDENCIA_TIPOS:
            return jsonify({'success': False, 'message': 'Tipo de incidencia no reconocido'}), 400

        actual = _estado_cargar().get(puesto_id) or {}
        _registrar_incidencia(puesto_id, actual.get('led'), actual.get('terminal'), tipo,
                              (datos.get('detalle') or '')[:200] or None)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al registrar la incidencia')


@bp.route('/api/pick-to-light/incidencias', methods=['GET'])
@requiere_pin_admin
def api_pick_to_light_incidencias():
    """Historial de incidencias, lo más reciente primero."""
    try:
        puesto_id = (request.args.get('puesto_id') or '').strip()[:24]
        try:
            limite = min(200, max(1, int(request.args.get('limit') or 50)))
        except (TypeError, ValueError):
            limite = 50

        sql = """
            SELECT id, puesto_id, canal, terminal_codigo, tipo, detalle, created_at
            FROM pick_to_light_incidencias
        """
        parametros = {'limite': limite}
        if puesto_id:
            sql += " WHERE puesto_id = :puesto_id"
            parametros['puesto_id'] = puesto_id
        sql += " ORDER BY id DESC LIMIT :limite"

        filas = db.session.execute(text(sql), parametros).fetchall()
        incidencias = [{'id': f[0], 'puesto_id': f[1], 'canal': f[2], 'terminal': f[3],
                        'tipo': f[4], 'detalle': f[5], 'fecha': f[6]} for f in filas]
        return jsonify({'success': True, 'incidencias': incidencias})
    except Exception as e:
        return error_interno(e, 'Error al consultar las incidencias')


# ==================== LO QUE MANDA LA PLACA ====================

@bp.route('/api/esp32/rfid/gaveta', methods=['POST'])
def api_esp32_rfid_gaveta():
    """Aviso de la placa: una gaveta se ha sacado o se ha devuelto.

    'resultado' lo decide la propia placa, que es quien tiene el dato al
    instante: ok (la correcta), equivocada, corregida, devuelta, sin_objetivo
    o arranque.
    """
    try:
        from app.routes.sistema import (_esp32_device_id, _rfid_devices_actualizar,
                                        _rfid_registrar_dispositivo)
        datos = request.get_json(silent=True) or {}
        device_id = _esp32_device_id(datos.get('device_id'))
        if not device_id:
            return jsonify({'success': False, 'message': 'Falta device_id'}), 400

        resultado = (datos.get('resultado') or '').strip()[:20]
        try:
            led = int(datos.get('led') or 0)
        except (TypeError, ValueError):
            led = 0
        fuera = bool(datos.get('fuera'))

        # El aviso vale tambien de latido, y de paso deja escrito cuantas
        # gavetas tiene la placa para poder verlo en Admin sin ir al puesto.
        _rfid_registrar_dispositivo(device_id)
        try:
            n_gavetas = int(datos.get('gavetas') or 0)
        except (TypeError, ValueError):
            n_gavetas = 0
        try:
            n_expansores = int(datos.get('expansores') or 0)
        except (TypeError, ValueError):
            n_expansores = 0
        # 'http' dice si la placa consiguio abrir su puerto 80. Una placa que
        # detecta los expansores pero no puede escuchar se ve igual de sana
        # desde Admin, y el unico sintoma es un ConnectionRefusedError al
        # empujarle una orden: guardarlo evita diagnosticar a ciegas.
        puerto_abierto = datos.get('http')
        en_prueba = datos.get('en_prueba')
        if n_gavetas or n_expansores or puerto_abierto is not None or en_prueba is not None:
            def _touch(devs):
                dev = devs.setdefault(device_id, {})
                if n_gavetas:
                    dev['gavetas'] = n_gavetas
                if n_expansores:
                    dev['expansores'] = n_expansores
                if puerto_abierto is not None:
                    dev['ptl_http'] = bool(puerto_abierto)
                if en_prueba is not None:
                    dev['en_prueba'] = bool(en_prueba)
                return devs
            _rfid_devices_actualizar(_touch)

        puesto_id = _puesto_de_la_placa(device_id)
        if not puesto_id:
            # Un lector sin puesto asignado no tiene a quien avisar; el latido
            # de arriba ya se ha guardado, que es lo que necesita Admin.
            return jsonify({'success': True})

        def _aplicar_aviso(estado):
            actual = estado.get(puesto_id) or {}
            intrusas = set(actual.get('intrusas') or [])
            if resultado == 'ok' and led and led == actual.get('led'):
                actual['recogida'] = True
                actual['devuelta'] = False
                actual['error_led'] = None
            elif resultado == 'devuelta' and led and led == actual.get('led'):
                actual['devuelta'] = True
            elif resultado == 'equivocada':
                intrusas.add(led)
            elif resultado == 'corregida':
                intrusas.discard(led)
            actual['intrusas'] = sorted(intrusas)
            actual['error_led'] = actual['intrusas'][0] if actual['intrusas'] else None

            eventos = (actual.get('eventos') or [])
            eventos.append({'led': led, 'fuera': fuera, 'resultado': resultado})
            actual['eventos'] = eventos[-MAX_EVENTOS_PUESTO:]
            estado[puesto_id] = actual
            return estado
        _estado_actualizar(_aplicar_aviso)

        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al registrar el aviso de gaveta')
