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
from datetime import datetime

from flask import request, jsonify, current_app
from sqlalchemy import text

from app.auth import requiere_pin_admin
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
    try:
        with open(_estado_file(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _estado_guardar(estado):
    with open(_estado_file(), 'w', encoding='utf-8') as f:
        json.dump(estado, f)


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
    try:
        with open(_test_file(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _test_guardar(datos):
    with open(_test_file(), 'w', encoding='utf-8') as f:
        json.dump(datos, f)


def _test_encolar(device_id, comando):
    """Aparca un comando para que la placa lo recoja en su sondeo.

    Devuelve el numero de secuencia con el que preguntar por el resultado. El
    resultado anterior se borra: si no, el panel leeria el de la prueba de
    antes y diria que ya esta hecha.
    """
    todo = _test_cargar()
    entrada = todo.get(device_id) or {}
    seq = int(entrada.get('seq') or 0) + 1
    todo[device_id] = {'cmd': comando, 'seq': seq}
    _test_guardar(todo)
    return seq


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


def _gaveta_del_terminal(terminal):
    row = db.session.execute(
        text("SELECT gaveta, led FROM terminales_gavetas WHERE terminal_codigo = :codigo"),
        {'codigo': terminal}
    ).fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def _gavetas_asignadas_del_puesto(puesto_id):
    """{led: {'terminal':..., 'gaveta':...}} de las maquinas de este puesto.

    Un mismo numero de LED en dos puestos distintos son dos cajones fisicos
    distintos (cada placa tiene su propia numeracion 1..N), asi que esto
    nunca mezcla terminales de otros puestos.
    """
    if not puesto_id:
        return {}
    filas = db.session.execute(text("""
        SELECT tg.led, tg.terminal_codigo, tg.gaveta
        FROM terminales_gavetas tg
        JOIN maquinas_terminales mt ON mt.terminal_codigo = tg.terminal_codigo AND mt.activo = 1
        JOIN maquinas m ON m.id = mt.maquina_id
        WHERE m.puesto_id = :puesto_id AND tg.led IS NOT NULL
    """), {'puesto_id': puesto_id}).fetchall()
    return {fila[0]: {'terminal': fila[1], 'gaveta': fila[2]} for fila in filas}


def _gavetas_validas_del_puesto(puesto_id):
    """LEDs con un terminal de verdad detras, entre los de las maquinas de este puesto.

    Un expansor MCP23017 trae 16 canales aunque solo se haya cableado un
    microinterruptor: los que faltan quedan flotando con el pull-up interno y
    leen "abierto" todo el rato. Sin esta lista la placa los confundiria con
    gavetas robadas. Con ella, cualquier canal que no sea el numero de LED de
    algun terminal de este puesto es ruido del expansor y se ignora.
    """
    return sorted(_gavetas_asignadas_del_puesto(puesto_id).keys())


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

        gaveta, led = _gaveta_del_terminal(terminal)
        if not led:
            return jsonify({'success': True, 'activo': False, 'gaveta': gaveta,
                            'motivo': 'El terminal %s no tiene gaveta con luz' % terminal})

        device_id, ip = _placa_del_puesto(puesto_id)
        if not device_id:
            return jsonify({'success': True, 'activo': False, 'gaveta': gaveta, 'led': led,
                            'motivo': 'Este puesto no tiene lector asignado en Admin'})

        validas = _gavetas_validas_del_puesto(puesto_id)
        ok, motivo = _enviar_a_placa(ip, {'led': led, 'terminal': terminal, 'validas': validas})

        # Se apunta la peticion aunque la placa no conteste: asi el sondeo del
        # navegador sabe que ya no espera nada de un terminal anterior.
        estado = _estado_cargar()
        estado[puesto_id] = {'led': led, 'terminal': terminal, 'gaveta': gaveta,
                             'recogida': False, 'devuelta': False, 'validas': validas,
                             'error_led': None, 'intrusas': [], 'eventos': []}
        _estado_guardar(estado)

        remoto = not ok and _backend_pythonanywhere()
        return jsonify({'success': True, 'activo': ok or remoto, 'led': led, 'gaveta': gaveta,
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

        estado = _estado_cargar()
        if puesto_id in estado:
            del estado[puesto_id]
            _estado_guardar(estado)

        return jsonify({'success': True, 'activo': ok})
    except Exception as e:
        return error_interno(e, 'Error al apagar las gavetas')


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

        estado_todo = _estado_cargar()
        if puesto_id:
            try:
                led_reportado = int(request.args.get('led') or 0)
            except (TypeError, ValueError):
                led_reportado = 0
            if led_reportado:
                actual = estado_todo.get(puesto_id) or {}
                if led_reportado == actual.get('led'):
                    cambiado = False
                    if request.args.get('recogida') == '1' and not actual.get('recogida'):
                        actual['recogida'] = True
                        actual['error_led'] = None
                        cambiado = True
                    puesta = request.args.get('puesta') == '1'
                    if bool(actual.get('devuelta')) != puesta:
                        actual['devuelta'] = puesta
                        cambiado = True
                    # La placa manda la lista ENTERA de gavetas abiertas que no
                    # tocan, no un cambio suelto: asi el estado no se queda con
                    # una intrusa fantasma si se perdio el aviso de que la
                    # devolvieron.
                    intrusas = _parsear_intrusas(request.args.get('intrusas'))
                    if list(actual.get('intrusas') or []) != intrusas:
                        actual['intrusas'] = intrusas
                        actual['error_led'] = intrusas[0] if intrusas else None
                        cambiado = True
                    if cambiado:
                        estado_todo[puesto_id] = actual
                        _estado_guardar(estado_todo)

        estado = estado_todo.get(puesto_id) if puesto_id else None
        led = (estado or {}).get('led')
        return jsonify({'success': True,
                        'apagar': not bool(led),
                        'led': led,
                        'terminal': (estado or {}).get('terminal') or '',
                        'validas': (estado or {}).get('validas') or []})
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
            estado = _estado_cargar()
            if apagar:
                estado.pop(puesto_id, None)
            else:
                estado[puesto_id] = {'led': led, 'terminal': '',
                                     'gaveta': 'Prueba LED %d' % led,
                                     'recogida': False, 'error_led': None, 'eventos': []}
            _estado_guardar(estado)
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
    """Mapa de cobertura del puesto de un lector: que canal tiene gaveta detras.

    Solo la parte ESTATICA (que terminal/etiqueta corresponde a cada canal):
    el estado en vivo (abierta/cerrada, error de expansor) lo trae ya el
    sondeo de /test/micros existente, que el panel cruza con esto en el
    navegador para no duplicar trafico hacia la placa.
    """
    try:
        from app.routes.sistema import _rfid_load_devices
        device_id = (request.args.get('device_id') or '').strip().lower()[:64]
        dev = (_rfid_load_devices() or {}).get(device_id) if device_id else None
        if not dev:
            return jsonify({'success': False, 'message': 'Lector no encontrado'}), 404

        puesto_id = dev.get('puesto_id') or ''
        total = int(dev.get('gavetas') or 0)
        asignados = _gavetas_asignadas_del_puesto(puesto_id) if puesto_id else {}
        canales = [{'canal': canal,
                    'terminal': (asignados.get(canal) or {}).get('terminal'),
                    'gaveta': (asignados.get(canal) or {}).get('gaveta')}
                  for canal in range(1, total + 1)]

        return jsonify({'success': True, 'device_id': device_id,
                        'puesto_id': puesto_id, 'puesto_nombre': dev.get('puesto_nombre') or '',
                        'total_gavetas': total, 'canales': canales})
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
    try:
        with open(_correspondencia_file(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _correspondencia_guardar(datos):
    with open(_correspondencia_file(), 'w', encoding='utf-8') as f:
        json.dump(datos, f)


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


# ==================== LO QUE MANDA LA PLACA ====================

@bp.route('/api/esp32/rfid/gaveta', methods=['POST'])
def api_esp32_rfid_gaveta():
    """Aviso de la placa: una gaveta se ha sacado o se ha devuelto.

    'resultado' lo decide la propia placa, que es quien tiene el dato al
    instante: ok (la correcta), equivocada, corregida, devuelta, sin_objetivo
    o arranque.
    """
    try:
        from app.routes.sistema import (_esp32_device_id, _rfid_load_devices,
                                        _rfid_save_devices, _rfid_registrar_dispositivo)
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
        # 'http' dice si la placa consiguio abrir su puerto 80. Una placa que
        # detecta los expansores pero no puede escuchar se ve igual de sana
        # desde Admin, y el unico sintoma es un ConnectionRefusedError al
        # empujarle una orden: guardarlo evita diagnosticar a ciegas.
        puerto_abierto = datos.get('http')
        if n_gavetas or puerto_abierto is not None:
            devs = _rfid_load_devices()
            dev = devs.setdefault(device_id, {})
            if n_gavetas:
                dev['gavetas'] = n_gavetas
            if puerto_abierto is not None:
                dev['ptl_http'] = bool(puerto_abierto)
            _rfid_save_devices(devs)

        puesto_id = _puesto_de_la_placa(device_id)
        if not puesto_id:
            # Un lector sin puesto asignado no tiene a quien avisar; el latido
            # de arriba ya se ha guardado, que es lo que necesita Admin.
            return jsonify({'success': True})

        estado = _estado_cargar()
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
        _estado_guardar(estado)

        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al registrar el aviso de gaveta')
