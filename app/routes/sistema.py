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
    gate_operario_activo,
    fijar_gate_operario,
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
    habituales de Windows (Git for Windows, GitHub Desktop, etc.) y de
    Linux (PythonAnywhere y similares, donde el proceso web puede correr
    con un PATH mínimo que no incluye /usr/bin).
    Devuelve la ruta completa al ejecutable o None si no se encuentra.
    """
    import shutil
    import glob

    # 1. Intentar desde el PATH del sistema
    git_path = shutil.which('git')
    if git_path:
        return git_path

    # 2. Rutas estándar: Linux (PythonAnywhere) y Git for Windows
    rutas_fijas = [
        '/usr/bin/git',
        '/usr/local/bin/git',
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


@bp.route('/api/sistema/gate_operario', methods=['GET'])
@requiere_pin_admin
def api_gate_operario_get():
    """Estado del gate de login global (Admin -> Sistema)."""
    try:
        return jsonify({'success': True, 'activo': gate_operario_activo()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/sistema/gate_operario', methods=['POST'])
@requiere_pin_admin
def api_gate_operario_set():
    """Activa/desactiva el gate de login global en caliente (sin reiniciar
    el servidor). Ver app/auth.py:requiere_operario."""
    try:
        data = request.get_json(silent=True) or {}
        fijar_gate_operario(bool(data.get('activo')))
        return jsonify({'success': True, 'activo': gate_operario_activo()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/descargar_instalador', methods=['GET'])
@requiere_pin_admin
def api_descargar_instalador():
    """Descarga DESCARGAR_E_INSTALAR.bat para instalar la app en un PC local
    (clona el repo, crea el venv, instala dependencias e inicializa la BD).
    Pensado para el PC que va a llevar el USB de una placa ESP32 (pantalla o
    lector RFID): PythonAnywhere no tiene puerto USB, asi que el flasheo
    siempre necesita un servidor local.

    El fichero se guarda en el repo con saltos de linea LF (normalizados por
    .gitattributes); un `git clone` en Windows los convierte solo a CRLF,
    pero una descarga directa como esta no pasa por ese filtro. cmd.exe
    puede fallar al interpretar los bloques `if (...)` multilinea con LF
    puro y cerrar la ventana con un error de sintaxis antes de llegar a
    ningun `pause` -- por eso se convierte aqui a CRLF explicitamente.
    """
    try:
        base_dir = os.path.dirname(current_app.root_path)
        ruta = os.path.join(base_dir, 'DESCARGAR_E_INSTALAR.bat')
        if not os.path.exists(ruta):
            return jsonify({'success': False,
                            'message': 'No se encuentra DESCARGAR_E_INSTALAR.bat en el servidor'}), 404
        with open(ruta, 'rb') as f:
            contenido = f.read()
        contenido = contenido.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        resp = current_app.make_response(contenido)
        resp.headers['Content-Type'] = 'application/octet-stream'
        resp.headers['Content-Disposition'] = 'attachment; filename=DESCARGAR_E_INSTALAR.bat'
        return resp
    except Exception as e:
        return error_interno(e)


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


# Cada puesto presente en un carro caduca solo si su PC deja de dar señales.
# El navegador re-envía sus datos cada ESP32_KEEPALIVE_S mientras el operario
# sigue en el módulo; si cierra la web, se va o se le cuelga el PC, la entrada
# desaparece de la pantalla del carro en cuanto pasa el TTL (en vez de quedarse
# colgada "en curso" durante una hora).
ESP32_TTL_S = 240            # 4 min sin noticias del PC = puesto liberado
ESP32_KEEPALIVE_S = 60       # cada cuánto re-envía el navegador (informativo)
ESP32_MAX_OPS = 8            # puestos simultáneos máximos por canal


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
        ota = None
        version_srv = _esp32_firmware_version()   # para que la pantalla sepa si esta al dia
        if dev_id:
            devs = _esp32_load_devices()
            dev = devs.setdefault(dev_id, {})
            dev['ip'] = request.args.get('esp32_ip') or dev.get('ip', '')
            dev['last_seen'] = datetime.now().isoformat()
            # Version de firmware que reporta la pantalla
            fw = (request.args.get('fw') or '').strip()[:24]
            if fw:
                dev['fw'] = fw
            # Estado del lector NFC de esa pantalla: off (sin lector), ok, ko
            nfc = (request.args.get('nfc') or '').strip()[:4]
            if nfc in ('off', 'ok', 'ko'):
                dev['nfc'] = nfc
            # OTA: si Admin lo pidio y la version no coincide, ofrecer la
            # actualizacion; si ya coincide, dar por hecha y limpiar.
            if dev.get('ota_pedido'):
                if fw and version_srv and fw == version_srv:
                    dev['ota_pedido'] = False
                else:
                    ota = {'update': True, 'version': version_srv,
                           'files': _esp32_firmware_manifest()}
            _esp32_save_devices(devs)
            # La asignacion del Admin manda sobre la config local de la pantalla
            if dev.get('carro'):
                carro = dev['carro']

        extra = {'carro_asignado': carro or '', 'ota': ota, 'fw_server': version_srv}
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


def _esp32_tags_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'esp32_tags.json')


def _esp32_registrar_evento(evento):
    """Añade un evento al historial reciente (Admin -> Diagnóstico ESP32),
    capado a los últimos 100. Compartido entre /api/esp32/evento (pulsadores
    y NFC de la pantalla del carro) y la entrada RFID de puesto (ver
    api_engastado_v3_entrada en operarios.py), para que ambos tipos de
    hardware aparezcan en el mismo panel de chequeo."""
    try:
        with open(_esp32_eventos_file()) as f:
            eventos = json.load(f)
    except Exception:
        eventos = []
    eventos.append(evento)
    with open(_esp32_eventos_file(), 'w') as f:
        json.dump(eventos[-100:], f, ensure_ascii=False)


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
            'uid': re.sub(r'[^0-9A-Fa-f]', '', request.args.get('uid') or '')[:20].upper(),
            'ts': datetime.now().isoformat(),
        }
        if not evento['tipo']:
            return jsonify({'success': False, 'message': 'tipo es obligatorio'}), 400
        _esp32_registrar_evento(evento)
        current_app.logger.info('Evento ESP32: %s', evento)

        # Liberar: sacar ese puesto del carro sin esperar al TTL. Es la salida
        # de emergencia física para un puesto que se quedó colgado (PC cerrado
        # de golpe, sin red al cancelar...).
        if evento['tipo'] == 'liberar' and evento['puesto']:
            borrado = {'clear': True, 'puesto_id': evento['puesto'],
                       'operario': evento['operario']}
            _esp32_write_channel(_esp32_file(), borrado, evento['ts'])
            if evento['carro']:
                _esp32_write_channel(_esp32_file(evento['carro']), borrado, evento['ts'])
            return jsonify({'success': True})

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


@bp.route('/api/esp32/eventos', methods=['GET'])
@requiere_pin_admin
def api_esp32_eventos():
    """Historial reciente de eventos físicos de los ESP32 (Admin -> Diagnóstico).

    Alimenta el panel de chequeo: el 'online' de Display Carro/Lectores RFID
    solo dice que el dispositivo hace poll, no que sus botones o su lector NFC
    respondan de verdad. Aquí, en cambio, cada botón pulsado o tarjeta pasada
    (en el carro o en un lector de puesto) debe aparecer al momento -- si no
    aparece nada al probar, el fallo está en el hardware, no en la red.
    """
    try:
        try:
            with open(_esp32_eventos_file()) as f:
                eventos = json.load(f)
        except Exception:
            eventos = []
        try:
            limite = min(max(int(request.args.get('limite', 50)), 1), 100)
        except (TypeError, ValueError):
            limite = 50
        recientes = list(reversed(eventos))[:limite]

        displays = _esp32_load_devices()
        lectores = _rfid_load_devices()
        for ev in recientes:
            dev = displays.get(ev.get('device_id')) or lectores.get(ev.get('device_id')) or {}
            ev['dispositivo_nombre'] = dev.get('nombre') or ''

        return jsonify({'success': True, 'eventos': recientes})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/ultimo-tag', methods=['GET'])
@requiere_pin_admin
def api_esp32_ultimo_tag():
    """Última tarjeta NFC leída en un carro y no reconocida.

    Es lo que usa Admin → Puestos para dar de alta una tarjeta: pulsas
    "Capturar tag", vas al carro, la pasas por el lector y el campo se rellena.
    Devuelve también la antigüedad en segundos para que Admin descarte lecturas
    viejas y no asigne por error una tarjeta de hace una hora.
    """
    try:
        try:
            with open(_esp32_tags_file()) as f:
                tag = json.load(f)
        except Exception:
            return jsonify({'success': True, 'tag': None})
        try:
            edad = (datetime.now() - datetime.fromisoformat(tag.get('ts') or '')).total_seconds()
        except Exception:
            edad = None
        tag['edad_s'] = int(edad) if edad is not None else None
        return jsonify({'success': True, 'tag': tag})
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
        version_srv = _esp32_firmware_version()
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
                'nfc': d.get('nfc', ''),
                'fw': d.get('fw', ''),
                'ota_pedido': bool(d.get('ota_pedido')),
            })
        try:
            carros = [c.get('numero') for c in CarroRepository(db).obtener_todos_carros()]
        except Exception:
            carros = []
        return jsonify({'devices': out, 'carros': carros, 'firmware_version': version_srv})
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
            # Módulos auxiliares (driver del lector NFC, etc.) antes del main:
            # si algo falla, la pantalla no arranca con un main que importa lo
            # que no está.
            libs = []
            lib_dir = os.path.join(proyecto, 'esp32', 'micropython', 'lib')
            if os.path.isdir(lib_dir):
                for nombre in sorted(os.listdir(lib_dir)):
                    if not nombre.endswith('.py'):
                        continue
                    r = mpremote('cp', os.path.join(lib_dir, nombre), ':' + nombre)
                    if r.returncode != 0:
                        err = (r.stderr or r.stdout or '').strip()
                        return jsonify({'success': False,
                                        'message': (f'Error al copiar {nombre}: ' + err)[-400:]})
                    libs.append(nombre)

            r = mpremote('cp', tmp_fw, ':app.py')
            if r.returncode != 0:
                err = (r.stderr or r.stdout or '').strip()
                if 'No module named' in err:
                    return jsonify({'success': False, 'message': 'mpremote no está instalado en este servidor. Ejecuta: pip install mpremote  (o actualiza dependencias)'})
                return jsonify({'success': False, 'message': ('Error al copiar: ' + err)[-400:] or 'Error al copiar (¿puerto ocupado por otro programa?)'})

            # Lanzador estable con autorrecuperacion (main.py). Solo se instala
            # por USB; el OTA por WiFi actualiza app.py, no este.
            launcher = os.path.join(proyecto, 'esp32', 'micropython', 'launcher.py')
            if os.path.exists(launcher):
                r = mpremote('cp', launcher, ':main.py')
                if r.returncode != 0:
                    err = (r.stderr or r.stdout or '').strip()
                    return jsonify({'success': False,
                                    'message': ('Error al copiar launcher: ' + err)[-400:]})
            mpremote('reset')  # el reset puede "fallar" al reconectar aunque funcione: no comprobar
        finally:
            try:
                os.remove(tmp_fw)
            except OSError:
                pass

        cambios = ' (WiFi actualizado)' if (ssid or password) else ''
        extra = f' Módulos: {", ".join(libs)}.' if libs else ''
        return jsonify({'success': True, 'message': f'Firmware subido por {puerto} y pantalla reiniciada{cambios}.{extra}'})
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


# ==================== OTA FIRMWARE ESP32 (WiFi) ====================
#
# Actualiza el firmware de APLICACION (main.py + libs) por WiFi, sin USB. NO
# toca el firmware MicroPython (.bin), que sigue por USB. La pantalla ya sondea
# /api/esp32/current cada 3s; cuando Admin pide una actualizacion, la respuesta
# lleva el manifiesto y la pantalla se descarga los ficheros por
# /api/esp32/firmware/file, los verifica (sha256) y se reinicia. Preserva sus
# propias credenciales WiFi (las reinyecta en el main.py descargado).

def _esp32_firmware_files():
    """Ficheros del firmware de aplicacion: (nombre_destino, ruta_absoluta).

    'app.py' se sirve desde main_wifi.py del repo; el resto son los lib/*.py.
    El lanzador (main.py) NO entra en el OTA: se mantiene estable y solo se
    instala por USB, para que un app.py defectuoso siempre pueda revertirse.
    """
    base = os.path.join(os.path.dirname(current_app.root_path), 'esp32', 'micropython')
    files = [('app.py', os.path.join(base, 'main_wifi.py'))]
    lib_dir = os.path.join(base, 'lib')
    if os.path.isdir(lib_dir):
        for nombre in sorted(os.listdir(lib_dir)):
            if nombre.endswith('.py'):
                files.append((nombre, os.path.join(lib_dir, nombre)))
    return files


def _esp32_firmware_version():
    """Version declarada en FW_VERSION dentro de main_wifi.py ('' si no hay)."""
    base = os.path.join(os.path.dirname(current_app.root_path), 'esp32', 'micropython')
    try:
        with open(os.path.join(base, 'main_wifi.py'), encoding='utf-8') as f:
            m = re.search(r'^FW_VERSION\s*=\s*["\'](.*?)["\']', f.read(), re.M)
            return m.group(1) if m else ''
    except Exception:
        return ''


def _esp32_firmware_manifest():
    """Lista [{name, sha256, size}] de los ficheros del firmware disponible."""
    manifest = []
    for nombre, ruta in _esp32_firmware_files():
        try:
            with open(ruta, 'rb') as f:
                data = f.read()
        except Exception:
            continue
        manifest.append({'name': nombre,
                         'sha256': hashlib.sha256(data).hexdigest(),
                         'size': len(data)})
    return manifest


@bp.route('/api/esp32/firmware/version', methods=['GET'])
def api_esp32_firmware_version():
    """Version y manifiesto del firmware de aplicacion disponible en el servidor."""
    try:
        return jsonify({'version': _esp32_firmware_version(),
                        'files': _esp32_firmware_manifest()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/firmware/file', methods=['GET'])
def api_esp32_firmware_file():
    """Sirve un fichero del firmware (bytes crudos) para el OTA de la pantalla."""
    try:
        nombre = (request.args.get('name') or '').strip()
        # Whitelist estricta: el nombre debe coincidir con uno del manifiesto,
        # asi que no cabe ningun path traversal.
        rutas = {n: r for n, r in _esp32_firmware_files()}
        ruta = rutas.get(nombre)
        if not ruta or not os.path.exists(ruta):
            return jsonify({'success': False, 'message': 'Fichero no válido'}), 404
        with open(ruta, 'rb') as f:
            data = f.read()
        resp = current_app.make_response(data)
        resp.headers['Content-Type'] = 'application/octet-stream'
        resp.headers['Content-Length'] = str(len(data))
        resp.headers['X-SHA256'] = hashlib.sha256(data).hexdigest()
        return resp
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/devices/<device_id>/ota', methods=['POST'])
@requiere_pin_admin
def api_esp32_device_ota(device_id):
    """Pide a una pantalla que se actualice por WiFi en su proximo poll."""
    try:
        dev_id = _esp32_device_id(device_id)
        devs = _esp32_load_devices()
        if dev_id not in devs:
            return jsonify({'success': False, 'message': 'Pantalla no encontrada'}), 404
        devs[dev_id]['ota_pedido'] = True
        _esp32_save_devices(devs)
        return jsonify({'success': True, 'version': _esp32_firmware_version()})
    except Exception as e:
        return error_interno(e)


# ==================== OTA FIRMWARE ESP32 RFID (entrada Engastado V3) ====================
#
# Mismo patron que el OTA de la pantalla de arriba, pero para la placa
# lectora RFID de entrada (ESP32 DevKit V1 Type-C + RC522, carpeta esp32/
# sin el subdirectorio micropython/). Solo main.py y esp32/lib/*.py son
# actualizables por OTA; boot.py, ota_update.py, http_client.py y
# wifi_config.py se instalan una vez por USB y nunca se tocan por WiFi (asi
# un OTA roto nunca puede inutilizar el propio mecanismo de OTA). La placa
# comprueba esto mismo al arrancar y periodicamente (ver esp32/ota_update.py).

def _rfid_firmware_files():
    """Ficheros del firmware de la placa RFID: (nombre_destino, ruta_absoluta).

    'main.py' es el fichero que cambia normalmente; 'backend_config.py' se
    incluye para poder migrar el host del backend (p.ej. de PythonAnywhere
    al servidor local) sin pasar por USB; lib/*.py por si hiciera falta
    actualizar el driver MFRC522 tambien sin USB.
    """
    base = os.path.join(os.path.dirname(current_app.root_path), 'esp32')
    files = [
        ('main.py', os.path.join(base, 'main.py')),
        ('backend_config.py', os.path.join(base, 'backend_config.py')),
    ]
    lib_dir = os.path.join(base, 'lib')
    if os.path.isdir(lib_dir):
        for nombre in sorted(os.listdir(lib_dir)):
            if nombre.endswith('.py'):
                files.append((nombre, os.path.join(lib_dir, nombre)))
    return files


def _rfid_firmware_version():
    """Version declarada en FW_VERSION dentro de esp32/main.py ('' si no hay)."""
    base = os.path.join(os.path.dirname(current_app.root_path), 'esp32')
    try:
        with open(os.path.join(base, 'main.py'), encoding='utf-8') as f:
            m = re.search(r'^FW_VERSION\s*=\s*["\'](.*?)["\']', f.read(), re.M)
            return m.group(1) if m else ''
    except Exception:
        return ''


def _rfid_firmware_manifest():
    """Lista [{name, sha256, size}] de los ficheros del firmware RFID disponible."""
    manifest = []
    for nombre, ruta in _rfid_firmware_files():
        try:
            with open(ruta, 'rb') as f:
                data = f.read()
        except Exception:
            continue
        manifest.append({'name': nombre,
                         'sha256': hashlib.sha256(data).hexdigest(),
                         'size': len(data)})
    return manifest


@bp.route('/api/esp32/rfid/firmware/version', methods=['GET'])
def api_esp32_rfid_firmware_version():
    """Version y manifiesto del firmware disponible para la placa lectora RFID.

    La placa llama a esto periodicamente para el OTA; se aprovecha la misma
    llamada como latido de presencia (?id=&ip=&fw=) para que aparezca sola en
    Admin -> Lectores RFID, igual que hacen las pantallas del carro con
    /api/esp32/current.
    """
    try:
        dev_id = _esp32_device_id(request.args.get('id'))
        if dev_id:
            _rfid_registrar_dispositivo(dev_id, ip=request.args.get('ip'), fw=request.args.get('fw'))

            # Si Admin pidió OTA manual para este lector, se marca como
            # resuelta cuando ya reporta la versión publicada en servidor.
            fw = (request.args.get('fw') or '').strip()[:24]
            version_srv = _rfid_firmware_version()
            devs = _rfid_load_devices()
            dev = devs.get(dev_id) or {}
            if dev.get('ota_pedido') and fw and version_srv and fw == version_srv:
                dev['ota_pedido'] = False
                devs[dev_id] = dev
                _rfid_save_devices(devs)
        return jsonify({'version': _rfid_firmware_version(),
                        'files': _rfid_firmware_manifest()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/rfid/firmware/file', methods=['GET'])
def api_esp32_rfid_firmware_file():
    """Sirve un fichero del firmware RFID (bytes crudos) para el OTA de la placa."""
    try:
        nombre = (request.args.get('name') or '').strip()
        # Whitelist estricta: el nombre debe coincidir con uno del manifiesto,
        # asi que no cabe ningun path traversal.
        rutas = {n: r for n, r in _rfid_firmware_files()}
        ruta = rutas.get(nombre)
        if not ruta or not os.path.exists(ruta):
            return jsonify({'success': False, 'message': 'Fichero no válido'}), 404
        with open(ruta, 'rb') as f:
            data = f.read()
        resp = current_app.make_response(data)
        resp.headers['Content-Type'] = 'application/octet-stream'
        resp.headers['Content-Length'] = str(len(data))
        resp.headers['X-SHA256'] = hashlib.sha256(data).hexdigest()
        return resp
    except Exception as e:
        return error_interno(e)


# ==================== REGISTRO DE LECTORES RFID (asignacion a puesto) ====================
#
# Mismo patron que "Display Carro" de arriba (device_id -> carro), aqui
# device_id -> puesto. El lector se registra solo, sin paso manual: cada vez
# que consulta /api/esp32/rfid/firmware/version manda su id/ip/fw y aqui se
# guarda como latido (ver _rfid_registrar_dispositivo, mas arriba). Desde
# Admin -> Lectores RFID se le asigna un puesto; a partir de ahi, el endpoint
# de entrada (POST /api/puestos/engastado_v3/entrada, en operarios.py) usa
# esa asignacion para decirle al PC que puesto es, sin que el operario tenga
# que elegirlo a mano.

def _rfid_devices_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'esp32_rfid_devices.json')


def _rfid_load_devices():
    try:
        with open(_rfid_devices_file()) as f:
            return json.load(f)
    except Exception:
        return {}


def _rfid_save_devices(devs):
    with open(_rfid_devices_file(), 'w') as f:
        json.dump(devs, f)


def _rfid_registrar_dispositivo(dev_id, ip=None, fw=None):
    """Actualiza last_seen/ip/fw de un lector (lo crea si es la primera vez)."""
    devs = _rfid_load_devices()
    dev = devs.setdefault(dev_id, {})
    dev['last_seen'] = datetime.now().isoformat()
    if ip:
        dev['ip'] = ip
    if fw:
        dev['fw'] = fw
    _rfid_save_devices(devs)


@bp.route('/api/esp32/rfid/devices', methods=['GET'])
@requiere_pin_admin
def api_esp32_rfid_devices():
    """Lista los lectores RFID detectados y los puestos existentes (Admin)."""
    try:
        devs = _rfid_load_devices()
        ahora = datetime.now()
        version_srv = _rfid_firmware_version()
        out = []
        for did, d in sorted(devs.items()):
            online = False
            try:
                # El lector late cada OTA_CHECK_INTERVAL_MS (60s por defecto,
                # ver esp32/wifi_config.py); 90s de margen evita parpadeos.
                online = (ahora - datetime.fromisoformat(d.get('last_seen', ''))).total_seconds() < 90
            except Exception:
                pass
            out.append({
                'id': did,
                'nombre': d.get('nombre', ''),
                'puesto_id': d.get('puesto_id', ''),
                'puesto_nombre': d.get('puesto_nombre', ''),
                'ip': d.get('ip', ''),
                'last_seen': d.get('last_seen', ''),
                'online': online,
                'fw': d.get('fw', ''),
                'ota_pedido': bool(d.get('ota_pedido')),
            })
        try:
            puestos = [{'id': p['id'], 'nombre': p['nombre']}
                      for p in PuestoRepository(db).obtener_todos_puestos()]
        except Exception:
            puestos = []
        return jsonify({'success': True, 'devices': out, 'puestos': puestos,
                        'firmware_version': version_srv})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/rfid/devices/<device_id>', methods=['POST'])
@requiere_pin_admin
def api_esp32_rfid_device_update(device_id):
    """Asigna nombre y/o puesto a un lector RFID (Admin)."""
    try:
        dev_id = _esp32_device_id(device_id)
        data = request.get_json(silent=True) or {}
        devs = _rfid_load_devices()
        dev = devs.setdefault(dev_id, {})
        if 'nombre' in data:
            dev['nombre'] = (data.get('nombre') or '').strip()[:60]
        if 'puesto_id' in data:
            puesto_id = (data.get('puesto_id') or '').strip()
            if puesto_id:
                puesto = PuestoRepository(db).obtener_puesto(puesto_id)
                if not puesto:
                    return jsonify({'success': False, 'message': 'Puesto no encontrado'}), 404
                dev['puesto_id'] = puesto_id
                dev['puesto_nombre'] = puesto['nombre']
            else:
                dev['puesto_id'] = ''
                dev['puesto_nombre'] = ''
        _rfid_save_devices(devs)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/rfid/devices/<device_id>/ota', methods=['POST'])
@requiere_pin_admin
def api_esp32_rfid_device_ota(device_id):
    """Pide OTA por WiFi para un lector RFID en su próximo poll."""
    try:
        dev_id = _esp32_device_id(device_id)
        devs = _rfid_load_devices()
        if dev_id not in devs:
            return jsonify({'success': False, 'message': 'Lector no encontrado'}), 404
        devs[dev_id]['ota_pedido'] = True
        _rfid_save_devices(devs)
        return jsonify({'success': True, 'version': _rfid_firmware_version()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/rfid/devices/<device_id>', methods=['DELETE'])
@requiere_pin_admin
def api_esp32_rfid_device_delete(device_id):
    """Olvida un lector RFID (Admin). Si sigue encendido, se registra solo de nuevo."""
    try:
        dev_id = _esp32_device_id(device_id)
        devs = _rfid_load_devices()
        devs.pop(dev_id, None)
        _rfid_save_devices(devs)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/rfid/flash_usb', methods=['POST'])
@requiere_pin_admin
def api_esp32_rfid_flash_usb():
    """Configura y sube TODOS los ficheros de una placa lectora RFID por USB
    de una vez: http_client.py, ota_update.py, wifi_config.py (con el WiFi y
    la contraseña de WebREPL que se rellenen aquí), lib/mfrc522.py, boot.py,
    backend_config.py y main.py.

    Pensado para el primer flasheo de una placa nueva (o para reinstalar
    todo desde cero): a partir de ahi, main.py se actualiza solo por WiFi
    (ver esp32/ota_update.py) y no hace falta volver a tocar el USB.

    Solo funciona en el servidor LOCAL con la placa conectada por USB (usa
    el mismo /api/esp32/puertos que la pantalla del carro; en PythonAnywhere
    no hay puertos USB, asi que esto no tiene efecto ahi).
    """
    try:
        data = request.get_json(force=True) or {}
        puerto = str(data.get('puerto', '')).strip()
        if not puerto or not re.fullmatch(r'[A-Za-z0-9/._:-]+', puerto):
            return jsonify({'success': False, 'message': 'Puerto no válido'}), 400

        ssid = str(data.get('ssid', '')).strip()
        # La contraseña WiFi puede ir vacia (red abierta, sin cifrado):
        # network.WLAN.connect(ssid, "") en MicroPython conecta igual a una
        # red sin clave, asi que aqui NO se exige que tenga contenido.
        password = str(data.get('password', ''))
        webrepl_password = str(data.get('webrepl_password', ''))
        if not ssid or not webrepl_password:
            return jsonify({'success': False,
                            'message': 'SSID y contraseña WebREPL son obligatorios '
                                       '(deja la contraseña WiFi vacía si la red no tiene; '
                                       'se graban en la placa, no se guardan en el servidor).'}), 400

        proyecto = os.path.dirname(current_app.root_path)
        base = os.path.join(proyecto, 'esp32')
        cfg_path = os.path.join(base, 'wifi_config.py')
        if not os.path.exists(cfg_path):
            return jsonify({'success': False, 'message': 'No se encuentra esp32/wifi_config.py'})

        with open(cfg_path, encoding='utf-8') as f:
            cfg_contenido = f.read()
        cfg_contenido = re.sub(r'^SSID\s*=.*$', 'SSID = %r' % ssid, cfg_contenido, count=1, flags=re.M)
        cfg_contenido = re.sub(r'^PASSWORD\s*=.*$', 'PASSWORD = %r' % password, cfg_contenido, count=1, flags=re.M)
        cfg_contenido = re.sub(r'^WEBREPL_PASSWORD\s*=.*$', 'WEBREPL_PASSWORD = %r' % webrepl_password,
                               cfg_contenido, count=1, flags=re.M)

        datadir = current_app.config.get('DATA_DIR') or os.path.join(proyecto, 'data')
        tmp_cfg = os.path.join(datadir, '_rfid_wifi_config_tmp.py')
        with open(tmp_cfg, 'w', encoding='utf-8') as f:
            f.write(cfg_contenido)

        def mpremote(*args):
            return subprocess.run(
                [sys.executable, '-m', 'mpremote', 'connect', puerto] + list(args),
                capture_output=True, text=True, timeout=90)

        def _resumen_error(etiqueta, err):
            """Ultima linea no vacia del error (el mensaje de la excepcion,
            p.ej. 'mpremote.transport.TransportError: could not enter raw
            repl'), con el nombre del fichero delante. Un traceback completo
            puede superar los 400 caracteres; cortarlo por el final se comia
            el 'Error al copiar X' y dejaba solo el traceback pelado."""
            lineas = [ln for ln in err.splitlines() if ln.strip()]
            resumen = lineas[-1] if lineas else err
            return (f'Error al copiar {etiqueta}: {resumen}')[:400]

        try:
            pasos = [
                ('http_client.py', os.path.join(base, 'http_client.py'), 'http_client.py'),
                ('ota_update.py', os.path.join(base, 'ota_update.py'), 'ota_update.py'),
                ('wifi_config.py', tmp_cfg, 'wifi_config.py'),
            ]
            # Los ficheros de esp32/lib/ se suben SUELTOS a la raiz de la
            # placa (sin subcarpeta): main.py los importa de forma plana
            # (`from mfrc522 import MFRC522`) y asi coincide exactamente con
            # los nombres que ya usa el manifiesto OTA (_rfid_firmware_files).
            lib_dir = os.path.join(base, 'lib')
            if os.path.isdir(lib_dir):
                for nombre in sorted(os.listdir(lib_dir)):
                    if nombre.endswith('.py'):
                        pasos.append((nombre, os.path.join(lib_dir, nombre), nombre))
            pasos.append(('boot.py', os.path.join(base, 'boot.py'), 'boot.py'))
            pasos.append(('backend_config.py', os.path.join(base, 'backend_config.py'), 'backend_config.py'))
            pasos.append(('main.py', os.path.join(base, 'main.py'), 'main.py'))

            for etiqueta, origen, destino in pasos:
                if not os.path.exists(origen):
                    return jsonify({'success': False, 'message': f'No se encuentra {etiqueta} en el repo'})

                r = mpremote('cp', origen, ':' + destino)
                if r.returncode != 0 and 'could not enter raw repl' in (r.stderr or ''):
                    # El CP2102 a veces no esta listo justo despues de la
                    # desconexion anterior: un respiro y un solo reintento
                    # basta casi siempre (visto en placas reales).
                    time.sleep(1.5)
                    r = mpremote('cp', origen, ':' + destino)

                if r.returncode != 0:
                    err = (r.stderr or r.stdout or '').strip()
                    if 'No module named' in err:
                        return jsonify({'success': False,
                                        'message': 'mpremote no está instalado en este servidor. Ejecuta: pip install mpremote'})
                    return jsonify({'success': False, 'message': _resumen_error(etiqueta, err)})

                time.sleep(0.3)  # dar tiempo a la placa antes del siguiente cp

            mpremote('reset')  # el reset puede "fallar" al reconectar aunque funcione: no comprobar
        finally:
            try:
                os.remove(tmp_cfg)
            except OSError:
                pass

        return jsonify({'success': True,
                        'message': f'Lector configurado y firmware subido por {puerto}. '
                                   f'A partir de ahora se actualiza solo por WiFi cuando publiques una '
                                   f'nueva FW_VERSION en esp32/main.py.'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False,
                        'message': 'Timeout: comprueba que la placa está conectada a ese puerto y que '
                                   'ningún otro programa (monitor serie, mpremote...) lo está usando.'})
    except Exception as e:
        return error_interno(e)


# ==================== HOTSPOT WIFI (PC servidor) ====================
#
# Dos piezas independientes:
# 1. Credenciales guardadas (bajo riesgo, siempre util): se recuerdan una vez
#    y precargan los formularios de "Subir por USB" (Display Carro y
#    Lectores RFID), para no tener que reescribirlas en cada placa.
# 2. Control del hotspot en si (mejor esfuerzo): usa el mecanismo clasico de
#    Windows (`netsh wlan set/start/stop hostednetwork`). Esta OBSOLETO en
#    Windows moderno y depende del driver del adaptador WiFi -- puede
#    simplemente no funcionar en algunos PCs. El error de netsh se muestra
#    tal cual en el admin, sin esconderlo, y la alternativa manual (activar
#    el Hotspot movil de Windows a mano, una vez, desde Ajustes) sigue
#    funcionando igual: solo hace falta guardar aqui el mismo SSID/clave.

def _hotspot_file():
    return os.path.join(current_app.config['DATA_DIR'], 'wifi_hotspot.json')


def _hotspot_cargar():
    try:
        with open(_hotspot_file()) as f:
            return json.load(f)
    except Exception:
        return {'ssid': '', 'password': ''}


@bp.route('/api/hotspot/credenciales', methods=['GET'])
@requiere_pin_admin
def api_hotspot_credenciales_get():
    """SSID/clave guardados del hotspot (para precargar formularios de USB)."""
    try:
        return jsonify({'success': True, **_hotspot_cargar()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/hotspot/credenciales', methods=['POST'])
@requiere_pin_admin
def api_hotspot_credenciales_set():
    """Guarda SSID/clave del hotspot (no arranca nada, solo los recuerda)."""
    try:
        data = request.get_json(silent=True) or {}
        ssid = str(data.get('ssid', '')).strip()
        password = str(data.get('password', ''))
        if not ssid:
            return jsonify({'success': False, 'message': 'El SSID es obligatorio'}), 400
        with open(_hotspot_file(), 'w') as f:
            json.dump({'ssid': ssid, 'password': password}, f)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


def _netsh_hostednetwork(*args, timeout=30):
    return subprocess.run(
        ['netsh', 'wlan'] + list(args),
        capture_output=True, text=True, timeout=timeout)


@bp.route('/api/hotspot/estado', methods=['GET'])
@requiere_pin_admin
def api_hotspot_estado():
    """Estado del hotspot 'hosted network' de Windows (netsh wlan).

    Solo tiene sentido en el servidor local (run.bat); en PythonAnywhere
    netsh no existe y esto devuelve 'no soportado' sin liar nada.
    """
    try:
        try:
            r = _netsh_hostednetwork('show', 'hostednetwork')
        except FileNotFoundError:
            return jsonify({'success': True, 'soportado': False,
                            'mensaje': 'netsh no está disponible en este servidor (no es Windows local).'})
        salida = (r.stdout or '') + (r.stderr or '')
        activo = 'Estado                 : Iniciado' in salida or 'Status                 : Started' in salida
        return jsonify({'success': True, 'soportado': True, 'activo': activo, 'salida_netsh': salida.strip()})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'message': 'Timeout consultando el estado con netsh'})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/hotspot/iniciar', methods=['POST'])
@requiere_pin_admin
def api_hotspot_iniciar():
    """Configura y arranca el hotspot con las credenciales guardadas.

    Usa el mecanismo 'hosted network' de netsh (obsoleto, depende del driver
    del adaptador). Si falla, se devuelve el error de netsh tal cual: no hay
    forma fiable de "arreglarlo" desde aquí, mejor que el admin vea el motivo
    real y recurra a la alternativa manual (Hotspot móvil de Windows) si hace
    falta.
    """
    try:
        cred = _hotspot_cargar()
        if not cred.get('ssid'):
            return jsonify({'success': False,
                            'message': 'Guarda primero un SSID y contraseña en "Credenciales del hotspot"'}), 400
        try:
            r1 = _netsh_hostednetwork('set', 'hostednetwork', 'mode=allow',
                                      f"ssid={cred['ssid']}", f"key={cred['password']}")
        except FileNotFoundError:
            return jsonify({'success': False,
                            'message': 'netsh no está disponible en este servidor (no es Windows local).'})
        if r1.returncode != 0:
            return jsonify({'success': False,
                            'message': ('Error al configurar: ' + (r1.stdout or r1.stderr or '')).strip()[-400:]})
        r2 = _netsh_hostednetwork('start', 'hostednetwork')
        if r2.returncode != 0:
            salida = (r2.stdout or r2.stderr or '').strip()
            return jsonify({'success': False,
                            'message': ('Error al arrancar el hotspot: ' + salida)[-400:] +
                                       ' — Si el adaptador WiFi no soporta redes "hosted", usa el Hotspot '
                                       'móvil de Windows manualmente (Ajustes) y guarda aquí el mismo SSID/clave.'})
        return jsonify({'success': True, 'message': f"Hotspot '{cred['ssid']}' iniciado."})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'message': 'Timeout arrancando el hotspot con netsh'})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/hotspot/detener', methods=['POST'])
@requiere_pin_admin
def api_hotspot_detener():
    """Para el hotspot iniciado por /api/hotspot/iniciar."""
    try:
        try:
            r = _netsh_hostednetwork('stop', 'hostednetwork')
        except FileNotFoundError:
            return jsonify({'success': False,
                            'message': 'netsh no está disponible en este servidor (no es Windows local).'})
        if r.returncode != 0:
            return jsonify({'success': False,
                            'message': ('Error al detener: ' + (r.stdout or r.stderr or '')).strip()[-400:]})
        return jsonify({'success': True, 'message': 'Hotspot detenido.'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'message': 'Timeout deteniendo el hotspot con netsh'})
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
