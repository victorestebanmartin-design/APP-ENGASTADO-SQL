"""
Salud, actualización del sistema (OTA), estadísticas y hook de deploy.
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
from app.config_manager import ConfigManager


# ==================== SALUD DEL SISTEMA ====================

@bp.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Verificar conexión a DB
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT sqlite_version()"))
            version = result.fetchone()[0]
        
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'sqlite_version': version
        })
    except Exception as e:
        # No exponer el detalle del error; queda en el log con su referencia
        import uuid
        error_id = uuid.uuid4().hex[:8]
        current_app.logger.exception(f"[{error_id}] Health check fallido: {e}")
        return jsonify({
            'status': 'error',
            'error': f'Base de datos no disponible (ref: {error_id})'
        }), 500

def _encontrar_git():
    """
    Busca el ejecutable de git en el PATH y en las rutas de instalación
    habituales de Windows (Git for Windows, GitHub Desktop, etc.).
    Devuelve la ruta completa al ejecutable o None si no se encuentra.
    """
    import shutil
    import glob

    # 1. Intentar desde el PATH del sistema
    git_path = shutil.which('git')
    if git_path:
        return git_path

    # 2. Rutas de instalación estándar de Git for Windows
    rutas_fijas = [
        r'C:\Program Files\Git\cmd\git.exe',
        r'C:\Program Files\Git\bin\git.exe',
        r'C:\Program Files (x86)\Git\cmd\git.exe',
        r'C:\Program Files (x86)\Git\bin\git.exe',
    ]
    for ruta in rutas_fijas:
        if os.path.isfile(ruta):
            return ruta

    # 3. Git empaquetado con GitHub Desktop (versión varía)
    appdata_local = os.environ.get('LOCALAPPDATA', '')
    if appdata_local:
        patrones = [
            os.path.join(appdata_local, 'GitHubDesktop', 'app-*', 'resources', 'app', 'git', 'cmd', 'git.exe'),
            os.path.join(appdata_local, 'GitHubDesktop', 'app-*', 'resources', 'app', 'git', 'mingw64', 'bin', 'git.exe'),
        ]
        for patron in patrones:
            coincidencias = sorted(glob.glob(patron), reverse=True)  # versión más nueva primero
            if coincidencias:
                return coincidencias[0]

    # 4. Scoop
    userprofile = os.environ.get('USERPROFILE', '')
    if userprofile:
        scoop_git = os.path.join(userprofile, 'scoop', 'apps', 'git', 'current', 'cmd', 'git.exe')
        if os.path.isfile(scoop_git):
            return scoop_git

    return None


@bp.route('/api/comprobar_actualizaciones', methods=['GET'])
@requiere_pin_admin
def api_comprobar_actualizaciones():
    """
    Comprueba si hay commits nuevos en GitHub comparando con el HEAD local.
    """
    try:
        base_dir = os.path.dirname(current_app.root_path)
        git_exe = _encontrar_git()
        if not git_exe:
            return jsonify({'success': False, 'message': 'Git no está instalado. Descárgalo desde https://git-scm.com/download/win'})

        def git(args):
            return subprocess.run(
                [git_exe] + args,
                cwd=base_dir,
                capture_output=True, text=True, timeout=15
            )

        # Obtener commit local actual
        r_local = git(['rev-parse', '--short', 'HEAD'])
        if r_local.returncode != 0:
            return jsonify({'success': False, 'message': 'No es un repositorio git o git no está instalado'})
        commit_local = r_local.stdout.strip()

        # Fetch silencioso para actualizar refs remotas
        git(['fetch', 'origin', 'main', '--quiet'])

        # Commit remoto tras el fetch
        r_remoto = git(['rev-parse', '--short', 'origin/main'])
        commit_remoto = r_remoto.stdout.strip() if r_remoto.returncode == 0 else None

        hay_actualizaciones = (commit_remoto and commit_remoto != commit_local)

        # Mensaje del último commit remoto
        r_msg = git(['log', 'origin/main', '-1', '--format=%s (%cr)'])
        mensaje_ultimo = r_msg.stdout.strip() if r_msg.returncode == 0 else ''

        # Listar commits pendientes de bajar
        r_pendientes = git(['log', f'HEAD..origin/main', '--oneline'])
        commits_pendientes = [l.strip() for l in r_pendientes.stdout.strip().splitlines() if l.strip()]

        return jsonify({
            'success': True,
            'hay_actualizaciones': hay_actualizaciones,
            'commit_local': commit_local,
            'commit_remoto': commit_remoto or commit_local,
            'mensaje_ultimo_commit': mensaje_ultimo,
            'commits_pendientes': commits_pendientes,
            'num_commits_pendientes': len(commits_pendientes)
        })

    except FileNotFoundError:
        return jsonify({'success': False, 'message': 'Git no está instalado. Instálalo desde https://git-scm.com/download/win'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'message': 'Timeout al conectar con GitHub. Comprueba la conexión.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@bp.route('/api/actualizar_sistema', methods=['POST'])
@requiere_pin_admin
def api_actualizar_sistema():
    """
    Ejecuta git pull origin main y actualiza dependencias si requirements.txt cambió.
    El servidor debe reiniciarse manualmente para aplicar cambios de Python.
    """
    try:
        base_dir = os.path.dirname(current_app.root_path)
        git_exe = _encontrar_git()
        if not git_exe:
            return jsonify({'success': False, 'message': 'Git no está instalado. Descárgalo desde https://git-scm.com/download/win'})

        def git(args):
            return subprocess.run(
                [git_exe] + args,
                cwd=base_dir,
                capture_output=True, text=True, timeout=30
            )

        # Verificar que hay cambios antes de pull
        r_fetch = git(['fetch', 'origin', 'main', '--quiet'])
        r_diff = git(['diff', '--quiet', 'HEAD', 'origin/main'])
        if r_diff.returncode == 0:
            return jsonify({'success': True, 'actualizado': False, 'message': 'Ya tienes la versión más reciente.'})

        # Comprobar si requirements.txt va a cambiar
        r_req = git(['diff', 'HEAD', 'origin/main', '--name-only'])
        ficheros_cambian = r_req.stdout.strip().splitlines()
        req_cambia = 'requirements.txt' in ficheros_cambian

        # Aplicar pull
        r_pull = git(['pull', 'origin', 'main'])
        if r_pull.returncode != 0:
            return jsonify({'success': False, 'message': f'Error en git pull: {r_pull.stderr.strip()}'})

        # Actualizar dependencias si es necesario. El pip del venv del proyecto
        # solo existe en instalaciones locales; en PythonAnywhere (venv externo)
        # se usa el pip del interprete que ejecuta la app. Un fallo aqui NO debe
        # abortar la actualizacion: el pull ya esta aplicado.
        pip_output = ''
        if req_cambia:
            pip_cmd = None
            for cand in (os.path.join(base_dir, 'venv', 'Scripts', 'pip.exe'),
                         os.path.join(base_dir, 'venv', 'bin', 'pip')):
                if os.path.exists(cand):
                    pip_cmd = [cand]
                    break
            if pip_cmd is None:
                pip_cmd = [sys.executable, '-m', 'pip']
            try:
                r_pip = subprocess.run(
                    pip_cmd + ['install', '-r', os.path.join(base_dir, 'requirements.txt'), '-q'],
                    capture_output=True, text=True, timeout=300
                )
                pip_output = (' | Dependencias actualizadas.' if r_pip.returncode == 0
                              else ' | ⚠️ Dependencias NO actualizadas (ejecuta a mano: pip install -r requirements.txt).')
            except Exception:
                pip_output = ' | ⚠️ Dependencias NO actualizadas (ejecuta a mano: pip install -r requirements.txt).'

        # Commit nuevo tras el pull
        r_new = git(['log', '-1', '--format=%h — %s (%cr)'])
        commit_nuevo = r_new.stdout.strip()

        # Programar reinicio: esperar 2s para que Flask envíe la respuesta primero.
        # En PythonAnywhere el reinicio se hace tocando el fichero WSGI de
        # /var/www (equivale al boton Reload de la pestaña Web); matar el
        # proceso alli NO recarga el codigo. En local, run.bat detecta el
        # codigo de salida 42 y relanza el servidor.
        import glob as _glob
        wsgi_pa = _glob.glob('/var/www/*_wsgi.py')
        import threading
        def _reiniciar():
            import time, os
            time.sleep(2)
            if wsgi_pa:
                for w in wsgi_pa:
                    try:
                        os.utime(w, None)
                    except Exception:
                        pass
            else:
                os._exit(42)  # Código 42 → run.bat lo detecta y relanza el servidor
        threading.Thread(target=_reiniciar, daemon=True).start()

        return jsonify({
            'success': True,
            'actualizado': True,
            'message': f'Sistema actualizado.{pip_output} Versión: {commit_nuevo} — Reiniciando servidor...',
            'ficheros_actualizados': ficheros_cambian,
            'reiniciando': True
        })

    except FileNotFoundError:
        return jsonify({'success': False, 'message': 'Git no está instalado. Instálalo desde https://git-scm.com/download/win'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'message': 'Timeout durante la actualización.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@bp.route('/api/stats', methods=['GET'])
@requiere_pin_admin
def api_stats():
    """Estadísticas generales del sistema"""
    try:
        proyecto_repo = ProyectoRepository(db)
        orden_repo = OrdenRepository(db)
        bono_repo = BonoRepository(db)
        carro_repo = CarroRepository(db)
        
        proyectos = proyecto_repo.obtener_todos_proyectos()
        ordenes_stats = orden_repo.obtener_estadisticas_por_estado()
        bonos = bono_repo.obtener_todos_bonos()
        carros = carro_repo.obtener_todos_carros()
        
        return jsonify({
            'success': True,
            'stats': {
                'proyectos': {
                    'total': len(proyectos),
                    'activos': len([p for p in proyectos if p['estado'] == 'activo'])
                },
                'ordenes': ordenes_stats,
                'bonos': {
                    'total': len(bonos),
                    'activos': len([b for b in bonos if b['estado'] == 'activo'])
                },
                'carros': {
                    'total': len(carros),
                    'disponibles': len([c for c in carros if c['estado'] == 'disponible'])
                }
            }
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/display', methods=['GET'])
def api_display():
    """Panel ESP32 — público pero limitado en datos (no expone información sensible)."""
    try:
        # Guardar IP del ESP32 para que el JS pueda hacer push directo
        esp32_ip = request.args.get('esp32_ip')
        if esp32_ip:
            ip_file = os.path.join(os.path.dirname(current_app.root_path), 'data', 'esp32_ip.txt')
            with open(ip_file, 'w') as f:
                f.write(esp32_ip.strip())

        orden_repo = OrdenRepository(db)
        stats = orden_repo.obtener_estadisticas_por_estado()
        from datetime import datetime, timezone, timedelta
        ahora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=2)))
        return jsonify({
            'p': stats.get('pendiente', 0),
            'e': stats.get('en_proceso', 0),
            't': stats.get('terminada',  0),
            'hora':  ahora.strftime('%H:%M'),
            'fecha': ahora.strftime('%d/%m'),
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/ip', methods=['GET'])
def api_esp32_ip():
    """Devuelve la última IP registrada del ESP32 (con CORS para app local)."""
    try:
        ip_file = os.path.join(os.path.dirname(current_app.root_path), 'data', 'esp32_ip.txt')
        ip = None
        if os.path.exists(ip_file):
            with open(ip_file) as f:
                ip = f.read().strip() or None
        from flask import make_response
        resp = make_response(jsonify({'ip': ip}))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        return error_interno(e)


def _esp32_file(carro=None):
    """Ruta del fichero de datos ESP32: global o el canal de un carro concreto."""
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    if carro:
        slug = re.sub(r'[^A-Za-z0-9_-]', '_', str(carro))[:24]
        return os.path.join(base, 'esp32_current_%s.json' % slug)
    return os.path.join(base, 'esp32_current.json')


def _esp32_devices_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'esp32_devices.json')


def _esp32_load_devices():
    try:
        with open(_esp32_devices_file()) as f:
            return json.load(f)
    except Exception:
        return {}


def _esp32_save_devices(devs):
    with open(_esp32_devices_file(), 'w') as f:
        json.dump(devs, f)


def _esp32_device_id(raw):
    return re.sub(r'[^A-Za-z0-9]', '', str(raw or ''))[:32]


ESP32_TTL_S = 3600           # los datos de un operario expiran a los 60 min
ESP32_MAX_OPS = 8            # operarios simultaneos maximos por canal


def _esp32_op_key(data):
    """Clave de la entrada dentro del canal de un carro.

    Se indexa por PUESTO: cada puesto tiene su botón en la pantalla del carro y
    nunca hay dos operarios en el mismo puesto, así que el puesto identifica sin
    ambigüedad. Los pushes antiguos (sin puesto) siguen entrando por operario.
    """
    return str(data.get('puesto_id') or data.get('operario') or '').strip()[:24]


def _esp32_ts_viva(ts_str):
    from datetime import datetime as _dt, timezone
    try:
        ts = _dt.fromisoformat(ts_str or '2000-01-01')
    except Exception:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (_dt.now(timezone.utc) - ts).total_seconds() <= ESP32_TTL_S


def _esp32_load_ops(path):
    """Lee un canal y devuelve su dict {operario: {'data':..., 'ts':...}}.

    Soporta el formato antiguo de un solo escritor ({'data':..., 'ts':...}).
    Descarta entradas expiradas o con 'clear'.
    """
    try:
        with open(path) as f:
            payload = json.load(f)
    except Exception:
        return {}
    if isinstance(payload.get('ops'), dict):
        ops = payload['ops']
    elif isinstance(payload.get('data'), dict):
        ops = {_esp32_op_key(payload['data']): {'data': payload['data'], 'ts': payload.get('ts', '')}}
    else:
        return {}
    return {k: v for k, v in ops.items()
            if isinstance(v, dict) and isinstance(v.get('data'), dict)
            and not v['data'].get('clear') and _esp32_ts_viva(v.get('ts'))}


def _esp32_write_channel(path, data, ts):
    """Aplica un push (o clear) de UN operario sobre el canal, sin pisar al resto."""
    ops = _esp32_load_ops(path)
    op = _esp32_op_key(data)
    if data.get('clear'):
        ops.pop(op, None)
    else:
        ops[op] = {'data': data, 'ts': ts}
        # Limite de seguridad: si hay demasiados, caen los mas antiguos
        while len(ops) > ESP32_MAX_OPS:
            ops.pop(min(ops, key=lambda k: ops[k].get('ts', '')))
    with open(path, 'w') as f:
        json.dump({'ops': ops}, f)


@bp.route('/api/esp32/push', methods=['POST', 'OPTIONS'])
def api_esp32_push():
    """Recibe datos de trabajo desde el navegador y los almacena para que el ESP32 los recoja.

    Si el payload trae 'carro', se escribe ademas en el canal de ese carro:
    las pantallas con CARRO_ASIGNADO solo leen su canal y no ven otros carros.
    Cada operario ('operario' en el payload) tiene su propia entrada dentro del
    canal: dos operarios trabajando el mismo carro no se pisan, y la pantalla
    puede rotar entre ellos con su pulsador.
    """
    if request.method == 'OPTIONS':
        resp = current_app.make_response('')
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp
    try:
        data = request.get_json(force=True) or {}
        from datetime import datetime
        ts = datetime.now().isoformat()
        _esp32_write_channel(_esp32_file(), data, ts)
        if data.get('carro'):
            _esp32_write_channel(_esp32_file(data['carro']), data, ts)
        resp = current_app.make_response(jsonify({'ok': True}))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/current', methods=['GET'])
def api_esp32_current():
    """Devuelve los últimos datos de trabajo enviados al ESP32 (TTL 60 min).

    Con ?id=<device_id> la pantalla queda registrada (aparece en Admin →
    Display Carro) y, si tiene carro asignado desde Admin, lee su canal.
    Con ?carro=X fuerza el canal de ese carro (config manual en la pantalla).

    Respuesta: 'ops' es la lista de operarios activos del canal (ordenada por
    nombre), cada uno con sus paquetes; 'data'/'ts' repiten el push mas
    reciente por compatibilidad con firmware antiguo.
    """
    try:
        carro = request.args.get('carro')
        dev_id = _esp32_device_id(request.args.get('id'))
        if dev_id:
            devs = _esp32_load_devices()
            dev = devs.setdefault(dev_id, {})
            dev['ip'] = request.args.get('esp32_ip') or dev.get('ip', '')
            dev['last_seen'] = datetime.now().isoformat()
            _esp32_save_devices(devs)
            # La asignacion del Admin manda sobre la config local de la pantalla
            if dev.get('carro'):
                carro = dev['carro']

        extra = {'carro_asignado': carro or ''}
        ops_dict = _esp32_load_ops(_esp32_file(carro))
        if not ops_dict:
            return jsonify({'data': None, 'ops': [], **extra})
        ops = [{'operario': k, 'data': v['data'], 'ts': v.get('ts', '')}
               for k, v in sorted(ops_dict.items())]
        ultimo = max(ops, key=lambda o: o['ts'])
        return jsonify({'data': ultimo['data'], 'ts': ultimo['ts'], 'ops': ops, **extra})
    except Exception as e:
        return error_interno(e)


def _esp32_eventos_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'esp32_eventos.json')


def _esp32_confirmaciones_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'esp32_confirmaciones.json')


def _esp32_conf_key(carro, puesto):
    """Las confirmaciones se guardan por (carro, puesto)."""
    return '%s|%s' % (str(carro or '').strip()[:24], str(puesto or '').strip()[:24])


@bp.route('/api/esp32/evento', methods=['GET'])
def api_esp32_evento():
    """Recibe un evento de los pulsadores de la pantalla ESP32.

    tipo=confirmacion: el operario ha pulsado el botón de su puesto en el carro
    y luego OK. El parámetro 'fase' dice qué confirmó:
      - fase=recoger  -> tiene en la mano los paquetes del lote
      - fase=devolver -> los ha dejado de vuelta en el carro
    tipo=confirmacion_manual: mismo efecto, pero pulsado desde el PC (la
    pantalla del carro no responde); queda registrado como manual.

    Se registra en esp32_eventos.json (histórico) y la última confirmación de
    cada (carro, puesto) en esp32_confirmaciones.json, que es lo que consulta
    el frontend vía /api/esp32/estado-carro.

    Es GET (no POST) porque el firmware de la pantalla solo sabe hacer GET.
    """
    try:
        evento = {
            'tipo': (request.args.get('tipo') or '').strip()[:24],
            'fase': (request.args.get('fase') or 'recoger').strip()[:12],
            'device_id': _esp32_device_id(request.args.get('id')),
            'carro': (request.args.get('carro') or '').strip()[:24],
            'puesto': (request.args.get('puesto') or '').strip()[:24],
            'operario': (request.args.get('operario') or '').strip()[:24],
            'lote': (request.args.get('lote') or '').strip()[:32],
            'grupo': (request.args.get('grupo') or '').strip()[:8],
            'ts': datetime.now().isoformat(),
        }
        if not evento['tipo']:
            return jsonify({'success': False, 'message': 'tipo es obligatorio'}), 400
        try:
            with open(_esp32_eventos_file()) as f:
                eventos = json.load(f)
        except Exception:
            eventos = []
        eventos.append(evento)
        with open(_esp32_eventos_file(), 'w') as f:
            json.dump(eventos[-100:], f, ensure_ascii=False)
        current_app.logger.info('Evento ESP32: %s', evento)

        # Confirmación: guardar la última por (carro, puesto)
        if evento['tipo'] in ('confirmacion', 'confirmacion_manual'):
            try:
                with open(_esp32_confirmaciones_file()) as f:
                    confs = json.load(f)
            except Exception:
                confs = {}
            # Clave por puesto; si el push no traía puesto se cae al operario
            clave = _esp32_conf_key(evento['carro'], evento['puesto'] or evento['operario'])
            confs[clave] = {
                'lote': evento['lote'], 'grupo': evento['grupo'],
                'fase': evento['fase'], 'tipo': evento['tipo'],
                'operario': evento['operario'], 'ts': evento['ts'],
            }
            with open(_esp32_confirmaciones_file(), 'w') as f:
                json.dump(confs, f, ensure_ascii=False)

        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/estado-carro', methods=['GET'])
def api_esp32_estado_carro():
    """Estado de la pantalla de un carro, para la confirmación física.

    Params: carro (obligatorio), puesto (recomendado; se acepta operario por
    compatibilidad con pushes antiguos).
    Devuelve:
      - display: True si hay alguna pantalla ESP32 asignada a ese carro en Admin
      - viva:    True si esa pantalla ha hecho poll en los últimos 90s
      - confirmacion: última confirmación de (carro, puesto)
        {lote, grupo, fase, tipo, operario, ts} o None si no hay ninguna.

    El frontend bloquea el botón solo si display=True, y lo desbloquea cuando
    confirmacion.lote y confirmacion.fase coinciden con lo que está pidiendo.
    """
    try:
        carro = (request.args.get('carro') or '').strip()
        if not carro:
            return jsonify({'success': False, 'message': 'carro es obligatorio'}), 400
        clave = (request.args.get('puesto') or request.args.get('operario') or '').strip()

        display, viva = False, False
        for dev in _esp32_load_devices().values():
            if str(dev.get('carro') or '') != carro:
                continue
            display = True
            try:
                ultimo = datetime.fromisoformat(dev.get('last_seen') or '2000-01-01')
                if (datetime.now() - ultimo).total_seconds() <= 90:
                    viva = True
            except Exception:
                pass

        confirmacion = None
        if clave:
            try:
                with open(_esp32_confirmaciones_file()) as f:
                    confirmacion = json.load(f).get(_esp32_conf_key(carro, clave))
            except Exception:
                confirmacion = None

        return jsonify({'success': True, 'display': display, 'viva': viva,
                        'confirmacion': confirmacion})
    except Exception as e:
        return error_interno(e)


# ==================== ADMIN: DISPLAY CARRO ====================

@bp.route('/api/esp32/devices', methods=['GET'])
@requiere_pin_admin
def api_esp32_devices():
    """Lista las pantallas ESP32 detectadas y los carros existentes (Admin)."""
    try:
        devs = _esp32_load_devices()
        ahora = datetime.now()
        out = []
        for did, d in sorted(devs.items()):
            online = False
            try:
                online = (ahora - datetime.fromisoformat(d.get('last_seen', ''))).total_seconds() < 15
            except Exception:
                pass
            out.append({
                'id': did,
                'nombre': d.get('nombre', ''),
                'carro': d.get('carro', ''),
                'ip': d.get('ip', ''),
                'last_seen': d.get('last_seen', ''),
                'online': online,
            })
        try:
            carros = [c.get('numero') for c in CarroRepository(db).obtener_todos_carros()]
        except Exception:
            carros = []
        return jsonify({'devices': out, 'carros': carros})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/puertos', methods=['GET'])
@requiere_pin_admin
def api_esp32_puertos():
    """Puertos serie (USB) detectados en el equipo que ejecuta ESTE servidor.

    Solo tiene sentido en la app local (run.bat) con la pantalla conectada
    por USB; en PythonAnywhere la lista siempre estará vacía.
    """
    try:
        try:
            from serial.tools import list_ports
        except ImportError:
            return jsonify({'puertos': [], 'aviso': 'pyserial no está instalado en este servidor (pip install pyserial mpremote)'})
        puertos = [{'puerto': p.device, 'descripcion': p.description or ''} for p in list_ports.comports()]
        # SSID actual del firmware, para prellenar el formulario
        fw = os.path.join(os.path.dirname(current_app.root_path), 'esp32', 'micropython', 'main_wifi.py')
        ssid = ''
        try:
            with open(fw, encoding='utf-8') as f:
                m = re.search(r'^SSID\s*=\s*["\'](.*)["\']', f.read(), re.M)
                if m:
                    ssid = m.group(1)
        except Exception:
            pass
        return jsonify({'puertos': puertos, 'ssid_actual': ssid})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/flash_usb', methods=['POST'])
@requiere_pin_admin
def api_esp32_flash_usb():
    """Sube esp32/micropython/main_wifi.py como main.py a la pantalla por USB.

    Usa mpremote contra el puerto indicado. Opcionalmente parchea SSID y
    PASSWORD del WiFi antes de subir (sin tocar el fichero del repo).
    Solo funciona en el servidor local con la pantalla conectada por USB.
    """
    try:
        data = request.get_json(force=True) or {}
        puerto = str(data.get('puerto', '')).strip()
        if not puerto or not re.fullmatch(r'[A-Za-z0-9/._:-]+', puerto):
            return jsonify({'success': False, 'message': 'Puerto no válido'}), 400

        proyecto = os.path.dirname(current_app.root_path)
        fw = os.path.join(proyecto, 'esp32', 'micropython', 'main_wifi.py')
        if not os.path.exists(fw):
            return jsonify({'success': False, 'message': 'No se encuentra esp32/micropython/main_wifi.py'})

        with open(fw, encoding='utf-8') as f:
            contenido = f.read()
        ssid = str(data.get('ssid', '')).strip()
        password = str(data.get('password', ''))
        if ssid:
            contenido = re.sub(r'^SSID\s*=.*$', 'SSID     = %r' % ssid, contenido, count=1, flags=re.M)
        if password:
            contenido = re.sub(r'^PASSWORD\s*=.*$', 'PASSWORD = %r' % password, contenido, count=1, flags=re.M)

        # Copia temporal (posiblemente parcheada) que es la que se sube
        base = current_app.config.get('DATA_DIR') or os.path.join(proyecto, 'data')
        tmp_fw = os.path.join(base, '_fw_upload_tmp.py')
        with open(tmp_fw, 'w', encoding='utf-8') as f:
            f.write(contenido)

        def mpremote(*args):
            return subprocess.run(
                [sys.executable, '-m', 'mpremote', 'connect', puerto] + list(args),
                capture_output=True, text=True, timeout=90)

        try:
            r = mpremote('cp', tmp_fw, ':main.py')
            if r.returncode != 0:
                err = (r.stderr or r.stdout or '').strip()
                if 'No module named' in err:
                    return jsonify({'success': False, 'message': 'mpremote no está instalado en este servidor. Ejecuta: pip install mpremote  (o actualiza dependencias)'})
                return jsonify({'success': False, 'message': ('Error al copiar: ' + err)[-400:] or 'Error al copiar (¿puerto ocupado por otro programa?)'})
            mpremote('reset')  # el reset puede "fallar" al reconectar aunque funcione: no comprobar
        finally:
            try:
                os.remove(tmp_fw)
            except OSError:
                pass

        cambios = ' (WiFi actualizado)' if (ssid or password) else ''
        return jsonify({'success': True, 'message': f'Firmware subido por {puerto} y pantalla reiniciada{cambios}.'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'message': 'Timeout: comprueba que la pantalla está conectada a ese puerto y que ningún otro programa (monitor serie, mpremote...) lo está usando.'})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/devices/<device_id>', methods=['POST', 'DELETE'])
@requiere_pin_admin
def api_esp32_device_update(device_id):
    """Asigna nombre/carro a una pantalla, o la olvida (DELETE)."""
    try:
        dev_id = _esp32_device_id(device_id)
        devs = _esp32_load_devices()
        if request.method == 'DELETE':
            devs.pop(dev_id, None)
            _esp32_save_devices(devs)
            return jsonify({'ok': True})
        if dev_id not in devs:
            return jsonify({'error': 'Pantalla no encontrada'}), 404
        data = request.get_json(force=True) or {}
        if 'nombre' in data:
            devs[dev_id]['nombre'] = str(data['nombre'])[:30]
        if 'carro' in data:
            devs[dev_id]['carro'] = str(data['carro'])[:24].strip()
        _esp32_save_devices(devs)
        return jsonify({'ok': True, 'device': devs[dev_id]})
    except Exception as e:
        return error_interno(e)


# ==================== DEPLOY HOOK ====================

def _deploy_token():
    """Lee el token: primero env var DEPLOY_SECRET, luego fichero .deploy_token junto a la app."""
    token = os.environ.get('DEPLOY_SECRET', '')
    if not token:
        # current_app.root_path es la carpeta 'app/', su padre es la raíz del proyecto
        project_dir = os.path.dirname(current_app.root_path)
        token_file = os.path.join(project_dir, '.deploy_token')
        if os.path.exists(token_file):
            with open(token_file, encoding='utf-8') as f:
                token = f.read().strip()
    return token

@bp.route('/api/internal/deploy-pull', methods=['POST'])
def deploy_pull():
    """Endpoint interno para hacer git pull desde el script de deploy local."""
    token = request.headers.get('X-Deploy-Token', '')
    expected = _deploy_token()
    # Comparación en tiempo constante y respuesta sin detalles internos
    if not expected or not hmac.compare_digest(token.encode('utf-8'), expected.encode('utf-8')):
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    project_dir = os.path.dirname(current_app.root_path)
    git = '/usr/bin/git'
    try:
        # fetch + reset --hard: siempre sincroniza con GitHub sin conflictos
        subprocess.run([git, 'fetch', 'origin', 'main'],
                       capture_output=True, text=True, cwd=project_dir, timeout=30)
        result = subprocess.run(
            [git, 'reset', '--hard', 'origin/main'],
            capture_output=True, text=True, cwd=project_dir, timeout=30
        )
        # En PythonAnywhere, recargar la web app tocando el WSGI (como el
        # boton Reload); sin esto el codigo nuevo no entra en funcionamiento.
        if result.returncode == 0:
            import glob as _glob
            for w in _glob.glob('/var/www/*_wsgi.py'):
                try:
                    os.utime(w, None)
                except Exception:
                    pass
        return jsonify({
            'success': result.returncode == 0,
            'stdout': result.stdout.strip(),
            'stderr': result.stderr.strip(),
            'returncode': result.returncode
        })
    except Exception as e:
        return error_interno(e, 'Error al sincronizar con GitHub', clave='error')


# ==================== EXPORTAR / IMPORTAR CONFIGURACIÓN ====================

def _config_manager():
    """Crea una instancia de ConfigManager con las rutas del proyecto."""
    base_dir = os.path.dirname(current_app.root_path)
    return ConfigManager(db, base_dir)


@bp.route('/api/exportar/db', methods=['POST'])
@requiere_pin_admin
def api_exportar_db():
    """Exporta solo la BD (sin Excel) como ZIP descargable."""
    try:
        contenido, nombre = _config_manager().exportar_db()
        return send_file(io.BytesIO(contenido), mimetype='application/zip',
                         as_attachment=True, download_name=nombre)
    except Exception as e:
        return error_interno(e, 'Error al exportar BD', clave='error')


@bp.route('/api/exportar/completo', methods=['POST'])
@requiere_pin_admin
def api_exportar_completo():
    """Exporta BD + todos los Excel de data/cortes/ como ZIP."""
    try:
        contenido, nombre = _config_manager().exportar_completo()
        return send_file(io.BytesIO(contenido), mimetype='application/zip',
                         as_attachment=True, download_name=nombre)
    except Exception as e:
        return error_interno(e, 'Error al exportar completo', clave='error')


@bp.route('/api/importar/db', methods=['POST'])
@requiere_pin_admin
def api_importar_db():
    """Importa una BD (y opcionalmente Excel) desde un ZIP. Reemplaza la BD actual."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No se proporcionó archivo'}), 400
    archivo = request.files['file']
    if not archivo or not archivo.filename.lower().endswith('.zip'):
        return jsonify({'success': False, 'error': 'El archivo debe ser un ZIP'}), 400
    incluir_excels = request.form.get('incluir_excels', 'true').lower() == 'true'
    try:
        resultado = _config_manager().importar_db(archivo.read(), incluir_excels=incluir_excels)
        return jsonify({'success': resultado['éxito'],
                        'mensaje': resultado['mensaje'],
                        'tablas':  resultado.get('tablas', {}),
                        'excels':  resultado.get('excels', 0)})
    except Exception as e:
        return error_interno(e, 'Error al importar BD', clave='error')


@bp.route('/api/backups', methods=['GET'])
@requiere_pin_admin
def api_listar_backups():
    """Lista los backups disponibles en data/."""
    try:
        backups = _config_manager().listar_backups()
        return jsonify({'success': True, 'backups': backups})
    except Exception as e:
        return error_interno(e, 'Error al listar backups', clave='error')


@bp.route('/api/backups/restaurar', methods=['POST'])
@requiere_pin_admin
def api_restaurar_backup():
    """Restaura la BD desde un backup local en data/."""
    nombre = (request.json or {}).get('nombre', '')
    if not nombre:
        return jsonify({'success': False, 'error': 'Nombre de backup requerido'}), 400
    try:
        resultado = _config_manager().restaurar_backup(nombre)
        return jsonify({'success': resultado['éxito'], 'mensaje': resultado['mensaje']})
    except Exception as e:
        return error_interno(e, 'Error al restaurar backup', clave='error')
