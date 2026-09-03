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


def _backend_pythonanywhere():
    """True si el servidor no puede abrir conexiones a las IP privadas."""
    host = (request.host or '').split(':', 1)[0].lower()
    return host.endswith('.pythonanywhere.com')


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

        ok, motivo = _enviar_a_placa(ip, {'led': led})

        # Se apunta la peticion aunque la placa no conteste: asi el sondeo del
        # navegador sabe que ya no espera nada de un terminal anterior.
        estado = _estado_cargar()
        estado[puesto_id] = {'led': led, 'terminal': terminal, 'gaveta': gaveta,
                             'recogida': False, 'error_led': None, 'eventos': []}
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
            'error_led': actual.get('error_led'),
        })
    except Exception as e:
        return error_interno(e, 'Error al consultar las gavetas')


@bp.route('/api/esp32/rfid/gaveta/orden', methods=['GET'])
def api_pick_to_light_orden():
    """Orden pendiente para el sondeo de una placa que está tras NAT.

    En planta el servidor puede abrir una conexión directa al lector. Desde
    PythonAnywhere no puede llegar a su IP privada, así que la propia placa
    consulta esta ruta y aplica la misma orden de forma local.
    """
    try:
        device_id = (request.args.get('device_id') or '').strip().lower()[:64]
        puesto_id = _puesto_de_la_placa(device_id)
        estado = _estado_cargar().get(puesto_id) if puesto_id else None
        led = (estado or {}).get('led')
        return jsonify({'success': True,
                        'apagar': not bool(led),
                        'led': led})
    except Exception as e:
        return error_interno(e, 'Error al consultar la orden de gaveta')


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
        if n_gavetas:
            devs = _rfid_load_devices()
            dev = devs.setdefault(device_id, {})
            dev['gavetas'] = n_gavetas
            _rfid_save_devices(devs)

        puesto_id = _puesto_de_la_placa(device_id)
        if not puesto_id:
            # Un lector sin puesto asignado no tiene a quien avisar; el latido
            # de arriba ya se ha guardado, que es lo que necesita Admin.
            return jsonify({'success': True})

        estado = _estado_cargar()
        actual = estado.get(puesto_id) or {}
        if resultado == 'ok' and led and led == actual.get('led'):
            actual['recogida'] = True
            actual['error_led'] = None
        elif resultado == 'equivocada':
            actual['error_led'] = led
        elif resultado == 'corregida' and actual.get('error_led') == led:
            actual['error_led'] = None

        eventos = (actual.get('eventos') or [])
        eventos.append({'led': led, 'fuera': fuera, 'resultado': resultado})
        actual['eventos'] = eventos[-MAX_EVENTOS_PUESTO:]
        estado[puesto_id] = actual
        _estado_guardar(estado)

        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e, 'Error al registrar el aviso de gaveta')
