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
import socket
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
        return error_interno(e, 'Error al comprobar actualizaciones')


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
        return error_interno(e, 'Error al actualizar el sistema')


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
            with open(ip_file, 'w', encoding='utf-8') as f:
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
            with open(ip_file, encoding='utf-8') as f:
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
        with open(_esp32_devices_file(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _esp32_save_devices(devs):
    with open(_esp32_devices_file(), 'w', encoding='utf-8') as f:
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
        with open(path, encoding='utf-8') as f:
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
    with open(path, 'w', encoding='utf-8') as f:
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
        # Quien manda trabajo es el navegador de un PC de puesto: se aprovecha
        # para anotar su IP en la tabla de red (ver _pc_registrar).
        _pc_registrar(request.remote_addr)
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
        with open(_esp32_eventos_file(), encoding='utf-8') as f:
            eventos = json.load(f)
    except Exception:
        eventos = []
    eventos.append(evento)
    with open(_esp32_eventos_file(), 'w', encoding='utf-8') as f:
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
                with open(_esp32_confirmaciones_file(), encoding='utf-8') as f:
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
            with open(_esp32_confirmaciones_file(), 'w', encoding='utf-8') as f:
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
            with open(_esp32_eventos_file(), encoding='utf-8') as f:
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
            with open(_esp32_tags_file(), encoding='utf-8') as f:
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
                with open(_esp32_confirmaciones_file(), encoding='utf-8') as f:
                    confirmacion = json.load(f).get(_esp32_conf_key(carro, clave))
            except Exception:
                confirmacion = None

        return jsonify({'success': True, 'display': display, 'viva': viva,
                        'confirmacion': confirmacion})
    except Exception as e:
        return error_interno(e)


# ==================== IP ESTATICA POR PLACA ESP32 ====================
#
# La red de planta esta aislada (sin internet) y NO tiene DHCP:
#
#   PC servidor .................. 192.168.50.1   (fija)
#   TL-WR802N (punto de acceso) .. 192.168.50.5   (fija, hace de gateway/DNS)
#   Placas ESP32 ................. 192.168.50.2-254 (menos las dos de arriba)
#
# Cada placa lleva por tanto su IP grabada en el propio firmware
# (wlan.ifconfig() ANTES de wlan.connect(), ver esp32/boot.py y
# esp32/micropython/main_wifi.py). Aqui se lleva el registro de que IP tiene
# cada placa -- en la BD, indexada por device_id (la MAC del chip, el mismo
# identificador que la placa usa en /api/esp32/*) -- para no repetir ninguna
# y poder reflashear sin recordarlas de memoria.
#
# La mascara y la puerta de enlace son fijas para toda la instalacion, no se
# configuran por placa.

IP_MASCARA = '255.255.255.0'
IP_GATEWAY = '192.168.50.5'      # TL-WR802N: puerta de enlace y DNS
IP_DNS = '192.168.50.5'
IP_PREFIJO = '192.168.50.'
IP_ULTIMO_MIN = 2                # .0 es la red y .1 el PC servidor
IP_ULTIMO_MAX = 254              # .255 es el broadcast
# IPs que ya tiene alguien fijo en esta red y que ninguna placa puede usar.
IP_RESERVADAS = {
    '192.168.50.1': 'PC servidor',
    IP_GATEWAY: 'punto de acceso TL-WR802N',
}
# Tipos de equipo que aparecen en la tabla de IPs. Los dos primeros son las
# placas que se flashean desde aqui; 'pc' son los ordenadores de puesto, que se
# configuran a mano en Windows y solo se anotan para no pisarles la direccion.
IP_TIPOS = {'display': 'Pantalla de carro', 'rfid': 'Lector RFID', 'pc': 'PC de puesto'}

# Bloque del ultimo octeto por tipo. NO cambia nada de rendimiento -- dentro de
# una misma subred da igual el numero -- pero se ve de un vistazo que es cada
# equipo y hace mucho mas dificil que un PC configurado a mano pise a una placa.
# No es una camisa de fuerza: una IP fuera de su bloque se acepta y solo se
# marca como tal, para no invalidar lo que ya estuviera puesto.
IP_BLOQUES = {
    'pc':      (10, 49),
    'display': (100, 149),
    'rfid':    (150, 199),
}


def _ip_bloque_de(tipo):
    return IP_BLOQUES.get(tipo if tipo in IP_BLOQUES else 'display')


def _ip_en_su_bloque(ip, tipo):
    """True si la IP cae en el bloque recomendado para ese tipo de equipo."""
    ini, fin = _ip_bloque_de(tipo)
    try:
        ultimo = int(str(ip).rsplit('.', 1)[-1])
    except ValueError:
        return False
    return ini <= ultimo <= fin


# ── PCs de puesto ────────────────────────────────────────────────────────
#
# No se flashean: su IP se pone a mano en Windows (la red no tiene DHCP). Pero
# comparten rango con las placas, asi que si no se anotan es cuestion de tiempo
# que alguien le de a una placa la IP de un PC.
#
# Detectarlos es gratis: el servidor ya ve la direccion de origen de cada
# peticion del navegador (request.remote_addr). El NOMBRE no se puede deducir
# de forma fiable -- en esta red no hay DNS que resolver a la inversa -- asi
# que ese lo pone el admin a mano.

def _pcs_vistos_file():
    base = current_app.config.get('DATA_DIR') or os.path.join(os.path.dirname(current_app.root_path), 'data')
    return os.path.join(base, 'pcs_vistos.json')


def _pcs_vistos_cargar():
    try:
        with open(_pcs_vistos_file(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _pcs_vistos_guardar(pcs):
    with open(_pcs_vistos_file(), 'w', encoding='utf-8') as f:
        json.dump(pcs, f)


# Cada cuanto se refresca el last_seen de un PC. Los endpoints por los que se
# le detecta los sondea el navegador cada 750 ms: sin este freno se estaria
# reescribiendo el fichero constantemente y sin ninguna ganancia.
_PC_REFRESCO_S = 30

# Cuanto se recuerda un PC que ya no aparece. Al cambiarle la IP a un PC, la
# vieja se quedaba en la lista para siempre ensuciandola con un equipo que ya
# no existe. Se olvida sola pasado este tiempo -- y si el PC sigue vivo vuelve
# a salir en cuanto su navegador hable con el servidor, asi que no se pierde
# nada. Tres dias: aguanta un fin de semana largo con el taller parado.
_PC_OLVIDO_DIAS = 3


def _pc_antiguedad_segundos(info, ahora=None):
    """Segundos desde que se vio ese PC, o None si no se sabe."""
    try:
        return ((ahora or datetime.now())
                - datetime.fromisoformat(info.get('last_seen', ''))).total_seconds()
    except Exception:
        return None


def _pcs_vistos_activos():
    """PCs vistos hace poco. Los caducados ni se enseñan ni cuentan."""
    ahora = datetime.now()
    limite = _PC_OLVIDO_DIAS * 86400
    vivos = {}
    for ip, info in _pcs_vistos_cargar().items():
        edad = _pc_antiguedad_segundos(info, ahora)
        if edad is None or edad <= limite:
            vivos[ip] = info
    return vivos


def _pc_registrar(ip):
    """Anota que se ha visto un PC en esa IP. Silencioso y con freno."""
    ip = (ip or '').strip()
    if not ip or not ip.startswith(IP_PREFIJO) or ip in IP_RESERVADAS:
        return
    try:
        pcs = _pcs_vistos_cargar()
        ahora = datetime.now()
        anterior = pcs.get(ip, {}).get('last_seen', '')
        if anterior:
            try:
                if (ahora - datetime.fromisoformat(anterior)).total_seconds() < _PC_REFRESCO_S:
                    return
            except ValueError:
                pass
        # Se aprovecha la escritura (como mucho una cada 30 s) para tirar los
        # caducados: asi el fichero se limpia solo sin tarea de mantenimiento.
        limite = _PC_OLVIDO_DIAS * 86400
        pcs = {k: v for k, v in pcs.items()
               if (_pc_antiguedad_segundos(v, ahora) or 0) <= limite}
        pcs[ip] = {'last_seen': ahora.isoformat()}
        _pcs_vistos_guardar(pcs)
    except Exception:
        pass   # detectar PCs es un extra: nunca puede tumbar la peticion real


def _pc_olvidar(ip):
    """Borra la anotacion de un PC detectado. True si habia algo que borrar."""
    ip = (ip or '').strip()
    pcs = _pcs_vistos_cargar()
    if ip not in pcs:
        return False
    del pcs[ip]
    _pcs_vistos_guardar(pcs)
    return True


def _ip_estatica_normalizar(ip):
    return str(ip or '').strip()


def _ip_estatica_error(ip):
    """Devuelve el motivo por el que 'ip' no vale como IP de placa, o None.

    Solo comprueba la IP en si (rango y reservas). El choque con otra placa
    depende de lo que haya en la BD y se mira aparte, en
    _ip_estatica_ocupada_por_otra.
    """
    ip = _ip_estatica_normalizar(ip)
    if not ip:
        return 'La IP estática es obligatoria'
    if not re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', ip):
        return f'"{ip}" no es una dirección IPv4 válida'
    if not ip.startswith(IP_PREFIJO):
        return (f'La IP debe estar en la red de planta {IP_PREFIJO}0/24 '
                f'(entre {IP_PREFIJO}{IP_ULTIMO_MIN} y {IP_PREFIJO}{IP_ULTIMO_MAX})')
    # Las reservadas se miran ANTES del rango: .1 tambien queda fuera del
    # rango util, pero "es la del PC servidor" le dice al operario por que
    # no puede usarla, que es la informacion que necesita.
    if ip in IP_RESERVADAS:
        return f'{ip} está reservada para el {IP_RESERVADAS[ip]}'
    ultimo = ip[len(IP_PREFIJO):]
    if not ultimo.isdigit() or not (IP_ULTIMO_MIN <= int(ultimo) <= IP_ULTIMO_MAX):
        return (f'La IP debe estar entre {IP_PREFIJO}{IP_ULTIMO_MIN} y '
                f'{IP_PREFIJO}{IP_ULTIMO_MAX}')
    return None


def _ips_estaticas_todas():
    """Todas las asignaciones guardadas, ordenadas por el ultimo octeto."""
    with db.engine.connect() as conn:
        filas = conn.execute(text(
            'SELECT device_id, tipo, nombre, ip, updated_at FROM esp32_ips'
        )).fetchall()
    salida = [{'device_id': f[0], 'tipo': f[1], 'nombre': f[2] or '',
               'ip': f[3], 'updated_at': f[4] or ''} for f in filas]
    return sorted(salida, key=lambda f: int(str(f['ip']).rsplit('.', 1)[-1] or 0))


def _ip_estatica_de(device_id):
    """IP asignada a una placa ('' si no tiene ninguna)."""
    with db.engine.connect() as conn:
        fila = conn.execute(
            text('SELECT ip FROM esp32_ips WHERE device_id = :d'),
            {'d': _esp32_device_id(device_id)}
        ).fetchone()
    return fila[0] if fila else ''


# Clave con la que se reserva una IP cuando NO se pudo leer la MAC de la
# placa al flashearla. Sin esto la IP quedaba sin registrar y el sistema se la
# volvia a ofrecer a la siguiente placa -- que es como acabaron dos placas con
# la misma direccion. Se reconcilia sola: en cuanto una placa de verdad se
# queda con esa IP, la reserva desaparece (ver _ip_estatica_guardar).
_IP_PENDIENTE_PREFIJO = 'pend'


def _ip_pendiente_id(ip):
    return _esp32_device_id(_IP_PENDIENTE_PREFIJO + str(ip).replace('.', ''))


def _es_ip_pendiente(device_id):
    return str(device_id or '').startswith(_IP_PENDIENTE_PREFIJO)


def _ips_en_uso_por_placas():
    """IPs que las placas dicen estar usando ahora mismo.

    No basta con mirar la BD: una placa flasheada cuando no se pudo leer su
    MAC no tiene fila, pero SI esta ocupando una IP y hay que respetarla.
    """
    ips = set()
    for origen in (_esp32_load_devices(), _rfid_load_devices()):
        for d in origen.values():
            ip = (d.get('ip') or '').strip()
            if ip:
                ips.add(ip)
    return ips


def _ips_cogidas():
    """Todo lo que no se puede volver a repartir.

    Union de tres fuentes: las reservadas de la instalacion, las asignadas en
    la BD y las que los equipos estan REPORTANDO. Mirar solo la BD fue el
    fallo que dejo dos placas en la misma IP.
    """
    return ({f['ip'] for f in _ips_estaticas_todas()}
            | set(IP_RESERVADAS)
            | _ips_en_uso_por_placas())


def _ip_estatica_libre_sugerida(tipo='display'):
    """Primera IP libre DEL BLOQUE de ese tipo ('' si no queda ninguna).

    Si el bloque se llena se sigue por el resto del rango: quedarse sin poder
    dar de alta una placa seria mucho peor que romper la convencion.
    """
    usadas = _ips_cogidas()
    ini, fin = _ip_bloque_de(tipo)
    for tramo in (range(ini, fin + 1),
                  range(IP_ULTIMO_MIN, IP_ULTIMO_MAX + 1)):
        for n in tramo:
            ip = f'{IP_PREFIJO}{n}'
            if ip not in usadas:
                return ip
    return ''


def _ip_estatica_ocupada_por_otra(device_id, ip):
    """device_id de OTRA placa que ya tiene esa IP, o '' si está libre.

    Reasignarle a una placa la IP que ya tenía (reflasheo) no es un choque.
    """
    with db.engine.connect() as conn:
        fila = conn.execute(
            text('SELECT device_id FROM esp32_ips WHERE ip = :ip'),
            {'ip': _ip_estatica_normalizar(ip)}
        ).fetchone()
    if not fila or fila[0] == _esp32_device_id(device_id):
        return ''
    # Una reserva "a ciegas" (IP grabada en una placa cuya MAC no se pudo
    # leer) no es un choque: es justo esta placa apareciendo por fin. Se
    # absorbe, no se rechaza -- si no, la reserva impediria arreglar el
    # problema que ella misma existe para señalar.
    if _es_ip_pendiente(fila[0]):
        return ''
    return fila[0]


def _ip_estatica_guardar(device_id, ip, tipo='display', nombre=''):
    """Asigna una IP a una placa. Devuelve (ok, mensaje).

    Valida el rango/reservas y que ninguna OTRA placa la tenga ya. Reasignar
    la misma IP a la misma placa es válido (reflasheo), no un duplicado.
    """
    dev_id = _esp32_device_id(device_id)
    if not dev_id:
        return False, 'Falta el identificador de la placa'
    ip = _ip_estatica_normalizar(ip)
    error = _ip_estatica_error(ip)
    if error:
        return False, error

    otra = _ip_estatica_ocupada_por_otra(dev_id, ip)
    if otra:
        return False, f'{ip} ya está asignada a la placa {otra[-4:]} ({otra})'

    with db.engine.connect() as conn:
        tipo = tipo if tipo in IP_TIPOS else 'display'
        # La reserva a ciegas de esta IP se retira ANTES de insertar: el UNIQUE
        # sobre ip saltaria si siguiera ahi, y entonces la placa de verdad no
        # podria quedarse con la direccion que ya tiene grabada.
        if not _es_ip_pendiente(dev_id):
            conn.execute(text('DELETE FROM esp32_ips WHERE device_id = :p'),
                         {'p': _ip_pendiente_id(ip)})
        try:
            conn.execute(text("""
                INSERT INTO esp32_ips (device_id, tipo, nombre, ip, updated_at)
                VALUES (:d, :t, :n, :ip, datetime('now'))
                ON CONFLICT(device_id) DO UPDATE SET
                    tipo = excluded.tipo,
                    nombre = COALESCE(NULLIF(excluded.nombre, ''), esp32_ips.nombre),
                    ip = excluded.ip,
                    updated_at = datetime('now')
            """), {'d': dev_id, 't': tipo, 'n': str(nombre or '')[:60], 'ip': ip})
            conn.commit()
        except IntegrityError:
            # El UNIQUE de la IP salta si dos flasheos coinciden en el tiempo
            # y los dos pasaron la comprobacion de arriba.
            conn.rollback()
            return False, f'{ip} acaba de asignarse a otra placa, elige otra'
    return True, f'IP {ip} asignada a la placa {dev_id[-4:]}'


def _ip_estatica_reservar_sin_placa(ip, tipo='display'):
    """Reserva una IP que YA se ha grabado en una placa cuya MAC no se pudo
    leer. Que no sepamos de quien es no la hace estar libre: sin esta reserva
    el sistema se la volveria a ofrecer a la siguiente placa."""
    return _ip_estatica_guardar(_ip_pendiente_id(ip), ip, tipo=tipo,
                                nombre='(sin identificar al flashear)')


def _leer_device_id_usb(mpremote, puerto=None):
    """Pregunta a la placa su device_id (MAC) por USB, con el mismo cálculo
    que usa el firmware (binascii.hexlify(machine.unique_id())).

    Sirve para guardar la IP contra el identificador real de la placa en el
    momento de flashearla, sin esperar a que arranque y se registre sola.
    Devuelve '' si la placa no contesta (p.ej. sin MicroPython todavía).
    """
    try:
        r = _mpremote_insistiendo(
            mpremote, 'exec',
            'import machine,binascii;'
            'print(binascii.hexlify(machine.unique_id()).decode())',
            puerto=puerto)
    except Exception:
        return ''
    if r.returncode != 0:
        return ''
    # La ultima linea es lo que imprimio el print(); antes puede venir ruido
    # del propio arranque de la placa.
    lineas = [ln.strip() for ln in (r.stdout or '').splitlines() if ln.strip()]
    return _esp32_device_id(lineas[-1]) if lineas else ''


@bp.route('/api/esp32/ips', methods=['GET'])
@requiere_pin_admin
def api_esp32_ips():
    """Listado de placas con IP fija asignada + parámetros de red (Admin).

    Incluye las placas detectadas por WiFi que aún no tienen IP asignada,
    para poder dársela desde la misma vista.
    """
    try:
        asignadas = {f['device_id']: f for f in _ips_estaticas_todas()}
        detectadas = {}
        for did, d in _esp32_load_devices().items():
            detectadas[did] = ('display', d.get('nombre', ''), d.get('ip', ''))
        for did, d in _rfid_load_devices().items():
            detectadas.setdefault(did, ('rfid', d.get('nombre', ''), d.get('ip', '')))

        placas = []
        for did, fila in asignadas.items():
            tipo, nombre, ip_vista = detectadas.get(did, (fila['tipo'], '', ''))
            placas.append({
                'device_id': did,
                'tipo': fila['tipo'] or tipo,
                'tipo_label': IP_TIPOS.get(fila['tipo'] or tipo, fila['tipo'] or tipo),
                'nombre': nombre or fila['nombre'] or '',
                'ip': fila['ip'],
                'ip_vista': ip_vista,        # la que reporta la placa al latir
                'coincide': bool(ip_vista) and ip_vista == fila['ip'],
                'detectada': did in detectadas,
                'updated_at': fila['updated_at'],
            })
        # PCs de puesto detectados por su IP de origen. Su "device_id" es la
        # propia IP (no tienen MAC que preguntar), asi que el admin les pone
        # nombre y quedan igual que una placa a efectos de no repetir IPs.
        pcs_vistos = _pcs_vistos_activos()
        for ip_pc, info in pcs_vistos.items():
            did_pc = _esp32_device_id('pc' + ip_pc.replace('.', ''))
            if did_pc in asignadas:
                continue
            detectadas[did_pc] = ('pc', '', ip_pc)

        for did, (tipo, nombre, ip_vista) in sorted(detectadas.items()):
            if did in asignadas:
                continue
            fila = {
                'device_id': did,
                'tipo': tipo,
                'tipo_label': IP_TIPOS.get(tipo, tipo),
                'nombre': nombre,
                'ip': '',
                'ip_vista': ip_vista,
                'coincide': False,
                'detectada': True,
                'updated_at': '',
            }
            # Un PC detectado no tiene IP que "liberar" (no se le asigna nada
            # desde aqui), pero SI se puede olvidar: es el unico modo de sacar
            # de la lista el que se quedo con una IP que ya no usa.
            if tipo == 'pc':
                info = pcs_vistos.get(ip_vista, {})
                edad = _pc_antiguedad_segundos(info)
                fila['olvidable'] = True
                fila['updated_at'] = info.get('last_seen', '')
                fila['visto_hace_min'] = int(edad // 60) if edad is not None else None
            placas.append(fila)

        # Colision: dos placas distintas diciendo tener la misma IP. En una red
        # sin DHCP nadie lo impide, y el sintoma es desconcertante -- el PC va
        # cambiando a que MAC apunta esa IP, asi que las placas parpadean entre
        # "en linea" y "sin señal" y las conexiones se van a la equivocada.
        # Vale la pena gritarlo aqui en vez de dejar que lo sufra el taller.
        vistas = {}
        for p in placas:
            if p['ip_vista']:
                vistas.setdefault(p['ip_vista'], []).append(p['device_id'])
        colisiones = [{'ip': ip, 'placas': ids} for ip, ids in sorted(vistas.items())
                      if len(ids) > 1]
        for p in placas:
            p['colision'] = bool(p['ip_vista']) and len(vistas.get(p['ip_vista'], [])) > 1
            p['pendiente'] = _es_ip_pendiente(p['device_id'])
            # Fuera de bloque no es un error, solo una convencion rota: se
            # marca para poder ordenarlo cuando toque, no para bloquear nada.
            ip_ref = p['ip'] or p['ip_vista']
            p['fuera_de_bloque'] = bool(ip_ref) and not _ip_en_su_bloque(ip_ref, p['tipo'])

        return jsonify({
            'success': True,
            'placas': placas,
            'colisiones': colisiones,
            'sugerida': _ip_estatica_libre_sugerida(),
            'sugeridas': {t: _ip_estatica_libre_sugerida(t) for t in IP_BLOQUES},
            'bloques': {t: {'desde': f'{IP_PREFIJO}{ini}', 'hasta': f'{IP_PREFIJO}{fin}',
                            'label': IP_TIPOS.get(t, t)}
                        for t, (ini, fin) in IP_BLOQUES.items()},
            'red': {
                'mascara': IP_MASCARA,
                'gateway': IP_GATEWAY,
                'dns': IP_DNS,
                'rango': f'{IP_PREFIJO}{IP_ULTIMO_MIN} – {IP_PREFIJO}{IP_ULTIMO_MAX}',
                'reservadas': IP_RESERVADAS,
            },
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/ips', methods=['POST'])
@requiere_pin_admin
def api_esp32_ips_asignar():
    """Asigna (o cambia) la IP fija de un equipo (Admin).

    Solo toca el registro. Una placa no se entera hasta que se le vuelve a
    flashear por USB con esta IP dentro; un PC de puesto hay que cambiarlo a
    mano en Windows. Anotarlo aqui sirve para que nadie reparta esa direccion
    dos veces.
    """
    try:
        data = request.get_json(silent=True) or {}
        ok, mensaje = _ip_estatica_guardar(
            data.get('device_id'), data.get('ip'),
            tipo=str(data.get('tipo') or 'display'),
            nombre=str(data.get('nombre') or ''))
        if not ok:
            return jsonify({'success': False, 'message': mensaje}), 400
        return jsonify({'success': True, 'message': mensaje + '. Reflashea la placa por USB para que la use.'})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/ips/<device_id>', methods=['DELETE'])
@requiere_pin_admin
def api_esp32_ips_liberar(device_id):
    """Libera la IP de una placa (queda disponible para otra)."""
    try:
        with db.engine.connect() as conn:
            conn.execute(text('DELETE FROM esp32_ips WHERE device_id = :d'),
                         {'d': _esp32_device_id(device_id)})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


def _origenes_de_la_app():
    """Origenes por los que se entra a esta app (esquema + host + puerto).

    Se listan todos los que pueden aparecer en la barra del navegador de un
    PC de puesto: el que ha usado quien pide el fichero, y el de la IP de
    planta del servidor. Sobra con que esten de mas -- la politica es una
    lista y un origen que nadie use no molesta -- pero faltar uno significa
    que ese PC concreto seguiria viendo el aviso.
    """
    origenes = []

    # El que ha usado quien esta pidiendo el fichero ahora mismo.
    actual = (request.host_url or '').rstrip('/')
    if actual:
        origenes.append(actual)

    # El de la red de planta. Si el admin baja el fichero desde el propio
    # servidor, el de arriba seria 'localhost' y NO serviria en los puestos.
    try:
        import socket
        puerto = request.host.split(':')[-1] if ':' in request.host else '5001'
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))     # no envia nada: solo elige interfaz
            ip_local = s.getsockname()[0]
        finally:
            s.close()
        lan = f'http://{ip_local}:{puerto}'
        if lan not in origenes:
            origenes.append(lan)
    except Exception:
        pass

    return origenes


@bp.route('/api/red/pc-puesto.reg', methods=['GET'])
@requiere_pin_admin
def api_red_pc_puesto_reg():
    """Fichero .reg que quita el aviso "No es seguro" en un PC de puesto.

    El aviso lo pone el NAVEGADOR, no la app: marca como insegura cualquier
    direccion que no sea https, salvo localhost. Da igual que la red este
    aislada. Y una pagina web no puede tocar la configuracion del equipo que
    la abre -- justo esa frontera es lo que hace seguro un navegador -- asi
    que esto no se puede aplicar solo: hay que ejecutarlo una vez en cada PC.

    Lo que se genera aqui es el fichero ya relleno con los origenes correctos,
    para que en el PC de puesto solo haya que abrirlo y aceptar.

    ?ambito=usuario (por defecto) escribe en HKEY_CURRENT_USER: un doble clic
    basta, sin permisos de administrador. Es lo que se quiere en un PC de
    puesto, donde solo se usa una cuenta de Windows.

    ?ambito=equipo escribe en HKEY_LOCAL_MACHINE, para TODAS las cuentas del
    PC. Eso SI necesita administrador, y un doble clic normal falla con "error
    de acceso al registro": hay que importarlo desde una consola elevada
    (reg import fichero.reg) o usar _scripts_utiles/configurar_pc_puesto.ps1.
    """
    try:
        ambito = (request.args.get('ambito') or 'usuario').strip().lower()
        equipo = ambito == 'equipo'
        raiz = 'HKEY_LOCAL_MACHINE' if equipo else 'HKEY_CURRENT_USER'

        origenes = _origenes_de_la_app()
        lineas = [
            'Windows Registry Editor Version 5.00',
            '',
            '; COJOsw - marcar el servidor como origen de confianza',
            '; Generado por el propio servidor: los origenes de abajo son los',
            '; que se estan usando de verdad para entrar a la aplicacion.',
            ';',
            '; Que hace: le dice a Chrome y a Edge que traten estas direcciones',
            '; como seguras. Con eso desaparece el aviso "No es seguro" y la app',
            '; vuelve a poder instalarse ("Instalar aplicacion"), que sobre http',
            '; el navegador no lo permite.',
            ';',
        ]
        if equipo:
            lineas += [
                '; AMBITO: TODO EL EQUIPO (HKEY_LOCAL_MACHINE).',
                '; Necesita permisos de administrador. Un doble clic normal NO',
                '; basta: falla con "error de acceso al registro". Importalo',
                '; desde una consola abierta como administrador:',
                ';',
                ';     reg import "COJOsw-pc-de-puesto-equipo.reg"',
                ';',
            ]
        else:
            lineas += [
                '; AMBITO: el usuario de Windows que lo ejecute (HKEY_CURRENT_USER).',
                '; No hace falta ser administrador.',
                ';',
            ]
        lineas += [
            '; Despues hay que CERRAR EL NAVEGADOR DEL TODO (todas las',
            '; ventanas) antes de volver a abrirlo.',
            '',
        ]

        for producto in (r'SOFTWARE\Policies\Google\Chrome',
                         r'SOFTWARE\Policies\Microsoft\Edge'):
            lineas.append(
                f'[{raiz}\\{producto}\\OverrideSecurityRestrictionsOnInsecureOrigin]')
            for i, origen in enumerate(origenes, start=1):
                lineas.append(f'"{i}"="{origen}"')
            lineas.append('')

        # El Bloc de notas y regedit esperan CRLF; sin esto el fichero se ve
        # en una sola linea y regedit puede rechazarlo.
        contenido = '\r\n'.join(lineas)
        nombre = ('COJOsw-pc-de-puesto-equipo.reg' if equipo
                  else 'COJOsw-pc-de-puesto.reg')
        return current_app.response_class(
            contenido.encode('utf-8-sig'),   # regedit quiere BOM
            mimetype='application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except Exception as e:
        return error_interno(e)


@bp.route('/api/red/pc-puesto.bat', methods=['GET'])
@requiere_pin_admin
def api_red_pc_puesto_bat():
    """Instalador que se AUTOELEVA y deja el aviso quitado para TODO el PC.

    El .reg de usuario solo arregla la cuenta que lo ejecuta, y desde una
    cuenta sin permisos no hay forma de elevarlo: los .reg no tienen "Ejecutar
    como administrador" en el menu del boton derecho, asi que un operario se
    queda atascado.

    Un .bat si puede pedir permisos el solo (UAC): se ejecuta desde la cuenta
    normal, Windows pide la contraseña de administrador una vez, y escribe la
    politica en HKEY_LOCAL_MACHINE, que vale para todas las cuentas del equipo.
    """
    try:
        origenes = _origenes_de_la_app()

        lineas = [
            '@echo off',
            'setlocal',
            'title COJOsw - Quitar el aviso "No es seguro"',
            '',
            'REM Generado por el propio servidor COJOsw: los origenes de abajo',
            'REM son los que se usan de verdad para entrar a la aplicacion.',
            'REM',
            'REM Escribe la politica en HKEY_LOCAL_MACHINE (todo el equipo), asi',
            'REM que vale para TODAS las cuentas de Windows de este PC.',
            '',
            'REM -- Pedir permisos de administrador si no se tienen ------------',
            'REM net session solo funciona con permisos elevados: es la forma',
            'REM clasica de saber si ya los tenemos.',
            'net session >nul 2>&1',
            'if %errorlevel% neq 0 (',
            '    echo.',
            '    echo  Hacen falta permisos de administrador.',
            '    echo  Windows va a pedirlos ahora...',
            '    echo.',
            '    powershell -NoProfile -Command "Start-Process -FilePath \'%~f0\' -Verb RunAs"',
            '    exit /b',
            ')',
            '',
            'echo ================================================================',
            'echo  COJOsw - marcando el servidor como origen de confianza',
            'echo ================================================================',
            'echo.',
        ]

        claves = [
            ('Google Chrome',
             r'HKLM\SOFTWARE\Policies\Google\Chrome\OverrideSecurityRestrictionsOnInsecureOrigin'),
            ('Microsoft Edge',
             r'HKLM\SOFTWARE\Policies\Microsoft\Edge\OverrideSecurityRestrictionsOnInsecureOrigin'),
        ]
        for etiqueta, clave in claves:
            lineas.append(f'echo  {etiqueta}:')
            for i, origen in enumerate(origenes, start=1):
                lineas.append(f'echo    {origen}')
                lineas.append(
                    f'reg add "{clave}" /v {i} /t REG_SZ /d "{origen}" /f >nul')
            lineas.append('echo.')

        lineas += [
            'echo ================================================================',
            'echo  Listo.',
            'echo.',
            'echo  AHORA: cierra el navegador DEL TODO (todas las ventanas)',
            'echo  y vuelve a abrirlo. Con una sola ventana abierta no se aplica.',
            'echo.',
            'echo  Para comprobarlo: edge://policy  o  chrome://policy',
            'echo ================================================================',
            'echo.',
            'pause',
        ]

        contenido = '\r\n'.join(lineas) + '\r\n'
        return current_app.response_class(
            # cp1252: un .bat con acentos en UTF-8 sale con caracteres raros
            # en la consola de Windows, que usa una tabla de codigos antigua.
            contenido.encode('cp1252', errors='replace'),
            mimetype='application/octet-stream',
            headers={'Content-Disposition':
                     'attachment; filename=COJOsw-quitar-aviso-todo-el-PC.bat'},
        )
    except Exception as e:
        return error_interno(e)


@bp.route('/api/red/pcs/<ip>', methods=['DELETE'])
@requiere_pin_admin
def api_red_pc_olvidar(ip):
    """Olvida un PC detectado por su IP (Admin -> Red y placas).

    Solo borra la anotación de "se ha visto un PC aquí": no toca la identidad
    del equipo (a qué puesto o módulo está dedicado, ver pc_equipos) ni la IP
    de ninguna placa. Si el PC sigue vivo volverá a aparecer solo en cuanto su
    navegador hable con el servidor, así que borrarlo nunca rompe nada.
    """
    try:
        if _pc_olvidar(ip):
            return jsonify({'success': True, 'message': f'PC {ip} olvidado'})
        return jsonify({'success': False, 'message': f'No hay ningún PC anotado en {ip}'}), 404
    except Exception as e:
        return error_interno(e)


# ==================== MPREMOTE: REINTENTOS ====================
#
# "could not enter raw repl" no suele ser un fallo de cable: mpremote tiene
# que INTERRUMPIR el programa que la placa esta ejecutando para entrar en la
# consola, y una placa ya configurada esta casi siempre a mitad de algo que
# bloquea -- boot.py tarda ~12s conectando el WiFi, y luego main.py hace una
# comprobacion OTA cada minuto (OTA_CHECK_INTERVAL_MS). Durante esas llamadas
# de red no atiende el Ctrl-C, y mpremote se rinde.
#
# La respuesta correcta es insistir: los huecos entre llamadas bloqueantes son
# cortos pero llegan. Un solo reintento a 1.5s cae dentro de la MISMA llamada
# que fallo; escalonando hasta ~10s se pilla el hueco casi siempre.

# Errores que merecen otro intento (la placa esta ocupada o el puerto todavia
# no esta libre). Cualquier otro fallo se devuelve tal cual: reintentar un
# "fichero no encontrado" solo hace perder tiempo.
_MPREMOTE_TRANSITORIOS = (
    'could not enter raw repl',
    'failed to access',
    'resource busy',
    'device or resource busy',
    'timed out',
)

# Esperas entre intentos (segundos). El lector RFID es el caso peor: su bucle
# hace una comprobacion OTA cada 60s y, con el servidor inalcanzable, se queda
# hasta 15s dentro de una lectura de socket donde el Ctrl-C no entra. Con esta
# escalera se cubre esa ventana en vez de morir dentro de ella.
_MPREMOTE_ESPERAS = (0.5, 1.5, 3.0, 5.0, 8.0, 8.0, 8.0)


def _es_error_transitorio(r):
    salida = ((r.stderr or '') + (r.stdout or '')).lower()
    return any(pista in salida for pista in _MPREMOTE_TRANSITORIOS)


def _interrumpir_placa(puerto):
    """Deja la placa parada en el REPL, sin llegar a ejecutar boot.py/main.py.

    Esperar a que una placa ocupada atienda el Ctrl-C es una carrera que se
    puede perder: el lector RFID pasa ratos dentro de lecturas de socket
    bloqueadas donde no lo atiende. Aqui se le da la vuelta -- se resetea por
    DTR/RTS (el mismo circuito de auto-reset que usa esptool) y se le manda
    Ctrl-C sin parar durante la ventana de arranque, para pillarla ANTES de
    que boot.py se meta en el WiFi.

    Es MEJOR ESFUERZO: si no hay pyserial, si la placa no lleva cableado el
    circuito de auto-reset o si el puerto no se deja abrir, devuelve False y
    se sigue con los reintentos normales.
    """
    try:
        import serial
    except ImportError:
        return False
    try:
        with serial.Serial(puerto, 115200, timeout=0.1) as s:
            # El reset por hardware va aparte: no todos los puentes USB-serie
            # ni todos los drivers dejan tocar DTR/RTS. Si no se puede, el
            # Ctrl-C de abajo sigue mereciendo la pena -- es la mitad portable
            # de la maniobra y basta cuando la placa esta en un time.sleep().
            try:
                s.dtr = False   # IO0 alto: arranque normal, NO modo descarga
                s.rts = True    # EN a masa: la placa entra en reset
                time.sleep(0.15)
                s.rts = False   # se suelta EN: la placa arranca
            except Exception:
                pass
            # Ctrl-C sin parar mientras arranca: interrumpe boot.py y, si se
            # cuela, tambien el main.py que venga detras.
            fin = time.monotonic() + 3.0
            while time.monotonic() < fin:
                s.write(b'\x03')
                s.flush()
                time.sleep(0.05)
        time.sleep(0.4)         # que el SO libere el puerto antes de mpremote
        return True
    except Exception:
        return False


def _mpremote_insistiendo(mpremote, *args, puerto=None):
    """Ejecuta mpremote reintentando mientras la placa este ocupada.

    Con el puerto a mano, ante el primer fallo transitorio se resetea la placa
    y se la para en el REPL (_interrumpir_placa) antes de reintentar: esperar
    a que se libere sola puede no llegar nunca; resetearla, si.

    Devuelve el CompletedProcess del ultimo intento (el que haya ido bien, o
    el ultimo fallo si se agotaron los reintentos).
    """
    r = mpremote(*args)
    for espera in _MPREMOTE_ESPERAS:
        if r.returncode == 0 or not _es_error_transitorio(r):
            return r
        if puerto:
            _interrumpir_placa(puerto)
        time.sleep(espera)
        r = mpremote(*args)
    return r


def _consejo_placa_ocupada(err):
    """Pista accionable para los fallos que no se arreglan reintentando."""
    if 'could not enter raw repl' not in (err or '').lower():
        return ''
    return (' — La placa no deja entrar a la consola ni reseteándola. Comprueba que ningún '
            'otro programa tenga el puerto abierto (Thonny, un monitor serie). Si sigue igual, '
            'su firmware actual la tiene demasiado ocupada para atender: ve a "Diagnóstico y '
            'preparación" → "Borrar y grabar MicroPython", que la deja limpia y sin nada '
            'ejecutándose, y vuelve a subir aquí.')


# ==================== HOST DEL SERVIDOR EN LAS PLACAS ====================
#
# A donde llaman las placas. No es por placa: es UNA direccion para toda la
# instalacion (el PC servidor, 192.168.50.1 en la red de planta), asi que se
# guarda como ajuste global y no en la tabla de IPs.
#
# Se INYECTA en el servidor, no se deja fijo en el repo, y en los DOS sitios
# donde se produce firmware:
#
#   - Al flashear por USB: HOST_IP en app.py (pantalla) y BACKEND_HOST en
#     backend_config.py (lector).
#   - Al servir el OTA: los mismos ficheros se sirven inyectados, y el
#     manifiesto se calcula sobre el contenido ya inyectado para que el
#     sha256 cuadre.
#
# Lo segundo no es un extra: sin ello el primer OTA sobrescribiria el host
# con el literal del repo y dejaria la placa llamando a un sitio que no
# existe -- justo el fallo que motivo todo esto.

# Puerto en el que las placas buscan el backend (PORT en main_wifi.py y
# BACKEND_PORT en backend_config.py). Aqui solo se usa para los mensajes del
# admin; el que manda sigue siendo el de esos ficheros.
PUERTO_SERVIDOR_PLACAS = 5001


def _servidor_file():
    return os.path.join(current_app.config['DATA_DIR'], 'servidor_backend.json')


def _servidor_host_guardado():
    """Host configurado para las placas ('' si no se ha fijado ninguno)."""
    try:
        with open(_servidor_file(), encoding='utf-8') as f:
            return str(json.load(f).get('host', '')).strip()
    except Exception:
        return ''


def _servidor_host_guardar(host):
    with open(_servidor_file(), 'w', encoding='utf-8') as f:
        json.dump({'host': host}, f)


def _servidor_host_detectado():
    """IP de ESTE equipo en la red de planta, o '' si no se puede deducir.

    Solo acierta cuando la app corre en el propio PC servidor (run.bat), que
    es justo el caso en el que se flashean placas. Prioriza una IP de la red
    de planta: un portatil puede tener varias interfaces (WiFi corporativa,
    VPN, Docker...) y la buena es la de 192.168.50.0/24.
    """
    candidatas = []
    # Socket UDP "conectado" al punto de acceso: no manda ningun paquete,
    # solo hace que el SO elija la interfaz con la que llegaria hasta el.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.3)
            s.connect((IP_GATEWAY, 9))
            candidatas.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidatas.append(info[4][0])
    except Exception:
        pass

    for ip in candidatas:
        if ip.startswith(IP_PREFIJO):
            return ip
    for ip in candidatas:
        if ip and not ip.startswith('127.') and ip != '0.0.0.0':
            return ip
    return ''


def _servidor_host_sugerido():
    """Lo que se propone en el formulario: lo guardado, o lo detectado."""
    return _servidor_host_guardado() or _servidor_host_detectado()


def _servidor_host_error(host):
    """Motivo por el que 'host' no vale como destino de las placas, o None.

    Se admite tambien un nombre DNS (p.ej. el PythonAnywhere de respaldo),
    asi que no se exige que sea una IP; lo que se rechaza es lo que no puede
    ser ninguna de las dos cosas.
    """
    host = str(host or '').strip()
    if not host:
        return 'La IP del servidor es obligatoria'
    if len(host) > 100:
        return 'La IP del servidor es demasiado larga'
    if not re.fullmatch(r'[A-Za-z0-9.\-]+', host):
        return f'"{host}" no es una IP ni un nombre de servidor válido'
    if re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', host):
        if any(int(o) > 255 for o in host.split('.')):
            return f'"{host}" no es una dirección IPv4 válida'
    return None


def _inyectar_host(contenido, variable, host):
    """Sustituye 'variable = ...' por el host configurado.

    Devuelve el contenido tal cual si no hay host configurado: mejor dejar
    el literal del repo que grabar una cadena vacia y que la placa no llame
    a ningun sitio.
    """
    if not host:
        return contenido
    return re.sub(r'^%s\s*=.*$' % re.escape(variable),
                  '%s = %r' % (variable, host), contenido, count=1, flags=re.M)


# Que variable lleva el host en cada fichero de firmware. Los que no salen
# aqui se sirven tal cual.
_HOST_POR_FICHERO = {
    'app.py': 'HOST_IP',                    # pantalla de carro (main_wifi.py)
    'backend_config.py': 'BACKEND_HOST',    # lector RFID
}


def _firmware_bytes(nombre, ruta):
    """Bytes de un fichero de firmware tal y como se le entregan a la placa.

    Punto unico por el que pasan el OTA (manifiesto y descarga) y nadie mas:
    si el manifiesto hashease el fichero del disco y la descarga sirviese el
    inyectado, la placa rechazaria el fichero por sha256 y no actualizaria
    nunca.
    """
    with open(ruta, 'rb') as f:
        data = f.read()
    variable = _HOST_POR_FICHERO.get(nombre)
    host = _servidor_host_guardado()
    if not variable or not host:
        return data
    try:
        return _inyectar_host(data.decode('utf-8'), variable, host).encode('utf-8')
    except UnicodeDecodeError:
        return data


@bp.route('/api/esp32/servidor', methods=['GET'])
@requiere_pin_admin
def api_esp32_servidor_get():
    """Host al que llaman las placas: el guardado, el detectado y el que se propone."""
    try:
        return jsonify({'success': True,
                        'host': _servidor_host_guardado(),
                        'detectado': _servidor_host_detectado(),
                        'sugerido': _servidor_host_sugerido()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/servidor', methods=['POST'])
@requiere_pin_admin
def api_esp32_servidor_set():
    """Fija el host al que llaman las placas.

    Afecta a las que se flasheen por USB a partir de ahora y a lo que se
    sirve por OTA; las ya desplegadas siguen con el que tengan grabado hasta
    que se actualicen.
    """
    try:
        data = request.get_json(silent=True) or {}
        host = str(data.get('host', '')).strip()
        error = _servidor_host_error(host)
        if error:
            return jsonify({'success': False, 'message': error}), 400
        _servidor_host_guardar(host)
        return jsonify({'success': True, 'host': host})
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
                'ip_estatica': _ip_estatica_de(did),
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
        # Se incluye el chip del puente USB-serie (deducido del VID) para poder
        # decir que driver falta cuando una placa no aparece como puerto COM.
        puertos = []
        for p in list_ports.comports():
            vid = f'{p.vid:04X}' if p.vid is not None else ''
            conocido = _USB_SERIE_CONOCIDOS.get(vid, {})
            puertos.append({
                'puerto': p.device,
                'descripcion': p.description or '',
                'vid': vid,
                'chip': conocido.get('chip', ''),
            })
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

    Usa mpremote contra el puerto indicado. Parchea SSID, PASSWORD y la IP
    fija de esta pantalla antes de subir (sin tocar el fichero del repo).
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
        if not ssid:
            return jsonify({'success': False,
                            'message': 'El SSID es obligatorio: el fichero del repo lleva un '
                                       'placeholder (YOUR_SSID), no unas credenciales reales.'}), 400
        # OJO: los dos re.sub van SIEMPRE, tambien con la contraseña vacia
        # (red abierta). El fichero del repo lleva placeholders a proposito
        # (YOUR_SSID / YOUR_PASSWORD), asi que saltarse el parcheo grabaria
        # esos literales en la placa y no conectaria nunca.
        contenido = re.sub(r'^SSID\s*=.*$', 'SSID     = %r' % ssid, contenido, count=1, flags=re.M)
        contenido = re.sub(r'^PASSWORD\s*=.*$', 'PASSWORD = %r' % password, contenido, count=1, flags=re.M)

        # IP fija de ESTA pantalla: la red de planta no tiene DHCP, asi que
        # sin ella la pantalla no llega al servidor. Se valida antes de tocar
        # nada (rango, reservas y que no la tenga ya otra placa) para no dejar
        # media placa flasheada con una IP que luego se rechaza.
        ip_estatica = _ip_estatica_normalizar(data.get('ip_estatica'))
        if not ip_estatica:
            return jsonify({'success': False,
                            'message': 'La IP estática es obligatoria: la red de planta no tiene DHCP. '
                                       'Mira las libres en Admin → IPs de placas.'}), 400
        error_ip = _ip_estatica_error(ip_estatica)
        if error_ip:
            return jsonify({'success': False, 'message': error_ip}), 400
        contenido = re.sub(r'^STATIC_IP\s*=.*$', 'STATIC_IP   = %r' % ip_estatica,
                           contenido, count=1, flags=re.M)

        # A donde llama la pantalla. Sin esto se grabaria el literal del repo,
        # que puede ser de otra red y deja la pantalla conectada pero muda
        # (no se registra en el admin porque su poll no llega a ningun sitio).
        host_srv = str(data.get('host_servidor', '')).strip() or _servidor_host_sugerido()
        error_host = _servidor_host_error(host_srv)
        if error_host:
            return jsonify({'success': False, 'message': error_host}), 400
        contenido = _inyectar_host(contenido, 'HOST_IP', host_srv)
        # Se recuerda para el proximo flasheo y para lo que se sirva por OTA.
        _servidor_host_guardar(host_srv)

        # Copia temporal (posiblemente parcheada) que es la que se sube
        base = current_app.config.get('DATA_DIR') or os.path.join(proyecto, 'data')
        tmp_fw = os.path.join(base, '_fw_upload_tmp.py')
        with open(tmp_fw, 'w', encoding='utf-8') as f:
            f.write(contenido)

        # Los .py del lector son pequenos: 20 s bastan para cada copia. Si el
        # firmware anterior no suelta el REPL, _mpremote_insistiendo reinicia
        # y reintenta en vez de dejar la pantalla web bloqueada 90 s por paso.
        def mpremote(*args, timeout=20):
            return subprocess.run(
                [sys.executable, '-m', 'mpremote', 'connect', puerto] + list(args),
            capture_output=True, text=True, timeout=timeout)

        # Primer contacto: es el que falla. La placa viene ejecutando su
        # firmware y puede estar dentro de una llamada bloqueante, asi que se
        # la resetea y se la para en el REPL antes de pedirle nada.
        _interrumpir_placa(puerto)

        # El device_id (MAC) se lee ANTES de copiar nada: es el identificador
        # con el que se anota la IP y con el que la pantalla se registrara
        # luego sola. Con el en la mano se comprueba ya que la IP no sea de
        # otra placa, para no dejar la flash a medias por un choque evitable.
        # La anotacion en si se guarda al final, cuando el flasheo ha ido bien.
        dev_id = _leer_device_id_usb(mpremote, puerto)
        otra = _ip_estatica_ocupada_por_otra(dev_id, ip_estatica) if dev_id else ''
        if otra:
            try:
                os.remove(tmp_fw)
            except OSError:
                pass
            return jsonify({'success': False,
                            'message': f'{ip_estatica} ya está asignada a la placa '
                                       f'{otra[-4:]} ({otra}). Elige otra en Admin → IPs de placas.'}), 400

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
                    r = _mpremote_insistiendo(mpremote, 'cp', os.path.join(lib_dir, nombre), ':' + nombre,
                                                       puerto=puerto)
                    if r.returncode != 0:
                        err = (r.stderr or r.stdout or '').strip()
                        return jsonify({'success': False,
                                        'message': (f'Error al copiar {nombre}: ' + err)[-400:]
                                                   + _consejo_placa_ocupada(err)})
                    libs.append(nombre)

            r = _mpremote_insistiendo(mpremote, 'cp', tmp_fw, ':app.py', puerto=puerto)
            if r.returncode != 0:
                err = (r.stderr or r.stdout or '').strip()
                if 'No module named' in err:
                    return jsonify({'success': False, 'message': 'mpremote no está instalado en este servidor. Ejecuta: pip install mpremote  (o actualiza dependencias)'})
                return jsonify({'success': False,
                                'message': (('Error al copiar: ' + err)[-400:] or 'Error al copiar (¿puerto ocupado por otro programa?)')
                                           + _consejo_placa_ocupada(err)})

            # La copia de seguridad del rollback (launcher.py) se deja
            # apuntando a ESTE mismo app.py. Si no, app_prev.py conserva el
            # firmware anterior al flasheo y un rollback desharia lo que se
            # acaba de subir (incluido el WiFi recien configurado).
            r = _mpremote_insistiendo(mpremote, 'cp', tmp_fw, ':app_prev.py', puerto=puerto)
            if r.returncode != 0:
                err = (r.stderr or r.stdout or '').strip()
                return jsonify({'success': False,
                                'message': ('Error al copiar la copia de seguridad: ' + err)[-400:]
                                           + _consejo_placa_ocupada(err)})

            # Lanzador estable con autorrecuperacion (main.py). Solo se instala
            # por USB; el OTA por WiFi actualiza app.py, no este.
            launcher = os.path.join(proyecto, 'esp32', 'micropython', 'launcher.py')
            if os.path.exists(launcher):
                r = _mpremote_insistiendo(mpremote, 'cp', launcher, ':main.py', puerto=puerto)
                if r.returncode != 0:
                    err = (r.stderr or r.stdout or '').strip()
                    return jsonify({'success': False,
                                    'message': ('Error al copiar launcher: ' + err)[-400:]
                                               + _consejo_placa_ocupada(err)})

            # Contador de arranques fallidos a cero: si la pantalla venia de un
            # app.py que no arrancaba, ese contador heredado dispararia un
            # rollback en el primer arranque tras el flasheo.
            # Igual que el reset, esta escritura final puede perder el puerto
            # cuando la placa anterior sigue ocupada. No debe retener la
            # respuesta HTTP: el firmware nuevo deja el contador a cero al
            # alcanzar su bucle principal.
            try:
                mpremote('exec', "open('boot_fails.txt','w').write('0')", timeout=10)
            except subprocess.TimeoutExpired:
                pass

            # Al reiniciar, la placa corta el USB antes de que mpremote pueda
            # cerrar limpiamente la sesion. Los ficheros ya se copiaron y el
            # reset SI se envio; no convertir ese corte esperado en un error
            # HTTP que deja el navegador esperando o muestra un falso fallo.
            try:
                mpremote('reset', timeout=10)
            except subprocess.TimeoutExpired:
                pass
        finally:
            try:
                os.remove(tmp_fw)
            except OSError:
                pass

        cambios = ' (WiFi actualizado)' if (ssid or password) else ''
        extra = f' Módulos: {", ".join(libs)}.' if libs else ''
        red = (f' IP fija {ip_estatica} (máscara {IP_MASCARA}, puerta de enlace {IP_GATEWAY}), '
               f'apuntando al servidor {host_srv}:{PUERTO_SERVIDOR_PLACAS}.')
        # Ya grabada en la placa: se anota para que no se le dé a otra.
        if dev_id:
            ok_ip, msg_ip = _ip_estatica_guardar(dev_id, ip_estatica, tipo='display')
            if not ok_ip:
                red += f' AVISO: la IP no se pudo anotar en la app ({msg_ip}).'
        else:
            # La IP ya esta grabada en la placa: se reserva aunque no sepamos
            # de quien es, o el sistema se la ofreceria a la siguiente.
            _ip_estatica_reservar_sin_placa(ip_estatica, tipo='display')
            red += (' AVISO: no se pudo leer el identificador de la pantalla. La IP queda reservada '
                    'para que no se le dé a otra placa, y se asignará sola en cuanto la pantalla '
                    'aparezca en Admin → IPs de placas.')
        return jsonify({'success': True,
                        'message': f'Firmware subido por {puerto} y pantalla reiniciada{cambios}.{extra}{red}'})
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
    """Lista [{name, sha256, size}] de los ficheros del firmware disponible.

    Se hashea el contenido YA inyectado (ver _firmware_bytes), que es el que
    la placa va a descargar y verificar.
    """
    manifest = []
    for nombre, ruta in _esp32_firmware_files():
        try:
            data = _firmware_bytes(nombre, ruta)
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
        data = _firmware_bytes(nombre, ruta)
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
    """Lista [{name, sha256, size}] de los ficheros del firmware RFID disponible.

    Igual que el de la pantalla: se hashea el contenido ya inyectado.
    """
    manifest = []
    for nombre, ruta in _rfid_firmware_files():
        try:
            data = _firmware_bytes(nombre, ruta)
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
        data = _firmware_bytes(nombre, ruta)
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
        with open(_rfid_devices_file(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _rfid_save_devices(devs):
    with open(_rfid_devices_file(), 'w', encoding='utf-8') as f:
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
            # Un lector puede estar asignado a un PUESTO de engastado o
            # directamente a un MODULO (mangueras/manguitos, que no tienen
            # puestos). En el desplegable ambos casos son una sola lista: los
            # modulos viajan con el id 'modulo:<slug>'.
            modulo = d.get('modulo', '')
            out.append({
                'id': did,
                'nombre': d.get('nombre', ''),
                'puesto_id': f'modulo:{modulo}' if modulo else d.get('puesto_id', ''),
                'puesto_nombre': d.get('puesto_nombre', ''),
                'ip': d.get('ip', ''),
                'ip_estatica': _ip_estatica_de(did),
                'last_seen': d.get('last_seen', ''),
                'online': online,
                'fw': d.get('fw', ''),
                'ota_pedido': bool(d.get('ota_pedido')),
                # Gavetas del pick-to-light que la placa dice tener (0 = no
                # lleva tira de LEDs). Lo manda ella en /api/esp32/rfid/gaveta,
                # asi que verlo aqui evita ir al puesto a contar cajones.
                'gavetas': int(d.get('gavetas') or 0),
            })
        try:
            puestos = [{'id': p['id'], 'nombre': f"🔧 Engastado — {p['nombre']}"}
                      for p in PuestoRepository(db).obtener_todos_puestos()]
        except Exception:
            puestos = []
        # Mangueras y manguitos no tienen puestos: el lector se asigna al
        # modulo entero (ver app/routes/puestos.py:_pc_identidad).
        puestos += [
            {'id': 'modulo:mangueras', 'nombre': '🌊 Mangueras (módulo completo)'},
            {'id': 'modulo:manguitos', 'nombre': '🔩 Manguitos (módulo completo)'},
        ]
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
            from app.routes.puestos import MODULOS_SIN_PUESTO, MODULOS_APP_LABEL
            destino = (data.get('puesto_id') or '').strip()
            if destino.startswith('modulo:'):
                # Lector de un modulo sin puestos (mangueras/manguitos)
                slug = destino.split(':', 1)[1]
                if slug not in MODULOS_SIN_PUESTO:
                    return jsonify({'success': False, 'message': 'Módulo no válido'}), 400
                dev['modulo'] = slug
                dev['puesto_id'] = ''
                dev['puesto_nombre'] = MODULOS_APP_LABEL.get(slug, slug)
            elif destino:
                puesto = PuestoRepository(db).obtener_puesto(destino)
                if not puesto:
                    return jsonify({'success': False, 'message': 'Puesto no encontrado'}), 404
                dev['modulo'] = ''
                dev['puesto_id'] = destino
                dev['puesto_nombre'] = puesto['nombre']
            else:
                dev['modulo'] = ''
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
    de una vez: http_client.py, ota_update.py, wifi_config.py (con el WiFi, la
    IP fija y la contraseña de WebREPL que se rellenen aquí), lib/mfrc522.py,
    boot.py, backend_config.py y main.py.

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
        perfil = str(data.get('perfil', 'devkit')).strip().lower()
        if perfil not in ('devkit', 'gen4_pn532'):
            return jsonify({'success': False, 'message': 'Perfil de lector no válido'}), 400
        orientacion = str(data.get('orientacion', '180')).strip()
        if orientacion not in ('0', '180'):
            return jsonify({'success': False, 'message': 'Orientación de pantalla no válida'}), 400
        entorno = str(data.get('entorno', 'produccion')).strip().lower()
        if entorno not in ('laboratorio', 'produccion'):
            return jsonify({'success': False, 'message': 'Entorno de instalación no válido'}), 400

        ssid = str(data.get('ssid', '')).strip()
        # La contraseña WiFi puede ir vacia (red abierta, sin cifrado):
        # network.WLAN.connect(ssid, "") en MicroPython conecta igual a una
        # red sin clave, asi que aqui NO se exige que tenga contenido.
        password = str(data.get('password', ''))
        # WebREPL (consola remota por WiFi, puerto 8266): opcional y apagado
        # por defecto. Ya no se pide en el formulario -- nadie lo usaba y
        # dejaba un servicio abierto en cada placa. Se sigue admitiendo por
        # si se llama a la API con una contrasena a proposito.
        webrepl_password = str(data.get('webrepl_password', ''))
        if not ssid:
            return jsonify({'success': False,
                            'message': 'El SSID es obligatorio (deja la contraseña WiFi vacía '
                                       'si la red no tiene; se graba en la placa, no se guarda '
                                       'en el servidor).'}), 400

        if entorno == 'laboratorio':
            # Router Movistar: DHCP y salida a internet para llegar a PA. No
            # guardar este host como ajuste global: pertenece a la nave.
            ip_estatica = ''
            host_srv = 'viktor85.pythonanywhere.com'
            puerto_placa = 443
            usar_ssl = True
        else:
            # Nave: red aislada sin DHCP y servidor local configurado a mano.
            ip_estatica = _ip_estatica_normalizar(data.get('ip_estatica'))
            if not ip_estatica:
                return jsonify({'success': False,
                                'message': 'La IP estática es obligatoria: la red de planta no tiene DHCP. '
                                           'Mira las libres en Admin → IPs de placas.'}), 400
            error_ip = _ip_estatica_error(ip_estatica)
            if error_ip:
                return jsonify({'success': False, 'message': error_ip}), 400
            host_srv = str(data.get('host_servidor', '')).strip() or _servidor_host_sugerido()
            error_host = _servidor_host_error(host_srv)
            if error_host:
                return jsonify({'success': False, 'message': error_host}), 400
            puerto_placa = PUERTO_SERVIDOR_PLACAS
            usar_ssl = False

        proyecto = os.path.dirname(current_app.root_path)
        base = os.path.join(proyecto, 'esp32')
        gen4_dir = os.path.join(base, 'micropython')
        cfg_path = os.path.join(base, 'wifi_config.py')
        app_gen4_path = os.path.join(gen4_dir, 'lector_puesto.py')
        if perfil == 'devkit' and not os.path.exists(cfg_path):
            return jsonify({'success': False, 'message': 'No se encuentra esp32/wifi_config.py'})
        if perfil == 'gen4_pn532' and not os.path.exists(app_gen4_path):
            return jsonify({'success': False, 'message': 'No se encuentra esp32/micropython/lector_puesto.py'})

        datadir = current_app.config.get('DATA_DIR') or os.path.join(proyecto, 'data')
        tmp_cfg = os.path.join(datadir, '_rfid_wifi_config_tmp.py')
        tmp_gen4_app = os.path.join(datadir, '_rfid_gen4_app_tmp.py')
        if perfil == 'devkit':
            with open(cfg_path, encoding='utf-8') as f:
                cfg_contenido = f.read()
            cfg_contenido = re.sub(r'^SSID\s*=.*$', 'SSID = %r' % ssid, cfg_contenido, count=1, flags=re.M)
            cfg_contenido = re.sub(r'^PASSWORD\s*=.*$', 'PASSWORD = %r' % password, cfg_contenido, count=1, flags=re.M)
            cfg_contenido = re.sub(r'^WEBREPL_PASSWORD\s*=.*$', 'WEBREPL_PASSWORD = %r' % webrepl_password,
                                   cfg_contenido, count=1, flags=re.M)
            cfg_contenido = re.sub(r'^STATIC_IP\s*=.*$', 'STATIC_IP = %r' % ip_estatica,
                                   cfg_contenido, count=1, flags=re.M)
            with open(tmp_cfg, 'w', encoding='utf-8') as f:
                f.write(cfg_contenido)
        else:
            with open(app_gen4_path, encoding='utf-8') as f:
                gen4_contenido = f.read()
            gen4_contenido = re.sub(r'^SSID\s*=.*$', 'SSID = %r' % ssid, gen4_contenido, count=1, flags=re.M)
            gen4_contenido = re.sub(r'^PASSWORD\s*=.*$', 'PASSWORD = %r' % password, gen4_contenido, count=1, flags=re.M)
            gen4_contenido = re.sub(r'^STATIC_IP\s*=.*$', 'STATIC_IP = %r' % ip_estatica,
                                    gen4_contenido, count=1, flags=re.M)
            gen4_contenido = _inyectar_host(gen4_contenido, 'HOST_IP', host_srv)
            gen4_contenido = re.sub(r'^PORT\s*=.*$', 'PORT = %d' % puerto_placa,
                                    gen4_contenido, count=1, flags=re.M)
            gen4_contenido = re.sub(r'^USE_SSL\s*=.*$', 'USE_SSL = %s' % usar_ssl,
                                    gen4_contenido, count=1, flags=re.M)
            gen4_contenido = re.sub(r'^DISPLAY_ROTATION\s*=.*$',
                                    'DISPLAY_ROTATION = %s' % orientacion,
                                    gen4_contenido, count=1, flags=re.M)
            with open(tmp_gen4_app, 'w', encoding='utf-8') as f:
                f.write(gen4_contenido)

        # backend_config.py con el host inyectado. Se sube este, no el del
        # repo: si no, la placa arrancaria llamando a la direccion de ejemplo.
        # (El OTA sirve este mismo fichero ya inyectado, ver _firmware_bytes,
        # asi que una actualizacion posterior no lo revierte.)
        bc_path = os.path.join(base, 'backend_config.py')
        if not os.path.exists(bc_path):
            return jsonify({'success': False, 'message': 'No se encuentra esp32/backend_config.py'})
        with open(bc_path, encoding='utf-8') as f:
            bc_contenido = _inyectar_host(f.read(), 'BACKEND_HOST', host_srv)
        bc_contenido = re.sub(r'^BACKEND_PORT\s*=.*$', 'BACKEND_PORT = %d' % puerto_placa,
                              bc_contenido, count=1, flags=re.M)
        bc_contenido = re.sub(r'^BACKEND_USE_SSL\s*=.*$', 'BACKEND_USE_SSL = %s' % usar_ssl,
                              bc_contenido, count=1, flags=re.M)
        tmp_bc = os.path.join(datadir, '_rfid_backend_config_tmp.py')
        with open(tmp_bc, 'w', encoding='utf-8') as f:
            f.write(bc_contenido)
        # Se recuerda para el proximo flasheo y para lo que se sirva por OTA.
        if entorno == 'produccion':
            _servidor_host_guardar(host_srv)

        # Los .py del lector son pequenos: 20 s bastan para cada copia. Si el
        # firmware anterior no suelta el REPL, _mpremote_insistiendo reinicia
        # y reintenta en vez de dejar la pantalla web bloqueada 90 s por paso.
        def mpremote(*args, timeout=20):
            return subprocess.run(
                # _interrumpir_placa deja la placa en raw REPL. Sin "resume",
                # mpremote hace un soft reset al abrir cada comando, relanza
                # boot.py y la gen4 vuelve a bloquear en WiFi antes de copiar
                # el primer fichero.
                [sys.executable, '-m', 'mpremote', 'connect', puerto, 'resume'] + list(args),
                capture_output=True, text=True, timeout=timeout)

        # Primer contacto: es el que falla. El lector pasa ratos dentro de
        # lecturas de socket bloqueadas (comprobacion OTA cada minuto) donde
        # no atiende el Ctrl-C, asi que se le resetea y se le para en el REPL
        # antes de pedirle nada.
        _interrumpir_placa(puerto)

        # device_id (MAC) de la placa: con el se anota la IP y con el se
        # registra ella sola despues, asi que se lee ANTES de escribir nada y
        # se comprueba ya que la IP no sea de otra placa. La anotacion se
        # guarda al final, cuando el flasheo ha ido bien.
        dev_id = _leer_device_id_usb(mpremote, puerto)
        otra = _ip_estatica_ocupada_por_otra(dev_id, ip_estatica) if dev_id and ip_estatica else ''
        if otra:
            for tmp in (tmp_cfg, tmp_bc, tmp_gen4_app):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            return jsonify({'success': False,
                            'message': f'{ip_estatica} ya está asignada a la placa '
                                       f'{otra[-4:]} ({otra}). Elige otra en Admin → IPs de placas.'}), 400

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
            if perfil == 'gen4_pn532':
                pasos = [
                    ('pn532_i2c.py', os.path.join(gen4_dir, 'lib', 'pn532_i2c.py'), 'pn532_i2c.py'),
                    ('gavetas.py', os.path.join(base, 'lib', 'gavetas.py'), 'gavetas.py'),
                    ('mcp23017.py', os.path.join(base, 'lib', 'mcp23017.py'), 'mcp23017.py'),
                    ('http_client.py', os.path.join(base, 'http_client.py'), 'http_client.py'),
                    ('backend_config.py', tmp_bc, 'backend_config.py'),
                    ('boot.py', os.path.join(gen4_dir, 'boot.py'), 'boot.py'),
                    ('launcher.py', os.path.join(gen4_dir, 'launcher.py'), 'main.py'),
                    ('app.py', tmp_gen4_app, 'app.py'),
                    ('app_prev.py (copia de seguridad)', tmp_gen4_app, 'app_prev.py'),
                ]
            else:
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
            if perfil == 'devkit' and os.path.isdir(lib_dir):
                for nombre in sorted(os.listdir(lib_dir)):
                    if nombre.endswith('.py'):
                        pasos.append((nombre, os.path.join(lib_dir, nombre), nombre))
            if perfil == 'devkit':
                pasos.append(('boot.py', os.path.join(base, 'boot.py'), 'boot.py'))
                pasos.append(('backend_config.py', tmp_bc, 'backend_config.py'))
                pasos.append(('main.py', os.path.join(base, 'main.py'), 'main.py'))
            # La copia de seguridad del rollback se deja apuntando a ESTE
            # mismo main.py. Si no, main_prev.py conserva el firmware que
            # hubiera antes del flasheo (posiblemente incompatible con la
            # wifi_config.py/backend_config.py que se acaban de subir) y un
            # rollback restauraria algo que no arranca.
                pasos.append(('main_prev.py (copia de seguridad)',
                              os.path.join(base, 'main.py'), 'main_prev.py'))

            for etiqueta, origen, destino in pasos:
                if not os.path.exists(origen):
                    return jsonify({'success': False, 'message': f'No se encuentra {etiqueta} en el repo'})

            if perfil == 'gen4_pn532':
                # La interfaz USB nativa del S3 de la gen4 puede devolver
                # ClearCommError al cerrar y reabrir COM entre dos copias.
                # Un unico mpremote "resume" conserva el raw REPL que se
                # recupero arriba y copia todos los ficheros sin reabrir COM.
                comando = [sys.executable, '-m', 'mpremote', 'connect', puerto, 'resume']
                for _etiqueta, origen, destino in pasos:
                    comando += ['cp', origen, ':' + destino, '+']
                comando += ['exec', "open('boot_fails.txt','w').write('0')"]
                r = subprocess.run(comando, capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    err = (r.stderr or r.stdout or '').strip()
                    if 'No module named' in err:
                        return jsonify({'success': False,
                                        'message': 'mpremote no está instalado en este servidor. Ejecuta: pip install mpremote'})
                    return jsonify({'success': False,
                                    'message': _resumen_error('firmware gen4', err) + _consejo_placa_ocupada(err)})
            else:
                for etiqueta, origen, destino in pasos:
                    r = _mpremote_insistiendo(mpremote, 'cp', origen, ':' + destino, puerto=puerto)

                    if r.returncode != 0:
                        err = (r.stderr or r.stdout or '').strip()
                        if 'No module named' in err:
                            return jsonify({'success': False,
                                            'message': 'mpremote no está instalado en este servidor. Ejecuta: pip install mpremote'})
                        return jsonify({'success': False,
                                        'message': _resumen_error(etiqueta, err) + _consejo_placa_ocupada(err)})

                    time.sleep(0.3)  # dar tiempo a la placa antes del siguiente cp

                # Dejar el contador de arranques fallidos a cero: si la placa
                # venia de un firmware que no arrancaba, ese contador puede
                # estar a punto de disparar un rollback que desharia este
                # flasheo en el primer arranque.
                try:
                    mpremote('exec', "open('boot_fails.txt','w').write('0')", timeout=10)
                except subprocess.TimeoutExpired:
                    pass

            # Al reiniciar, la placa corta el USB antes de que mpremote pueda
            # cerrar limpiamente la sesion. Los ficheros ya se copiaron y el
            # reset SI se envio; no convertir ese corte esperado en un error
            # HTTP que deja el navegador esperando o muestra un falso fallo.
            try:
                mpremote('reset', timeout=10)
            except (subprocess.TimeoutExpired, Exception):
                pass
        finally:
            for tmp in (tmp_cfg, tmp_bc, tmp_gen4_app):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

        red = ('Laboratorio: DHCP, apuntando a PythonAnywhere por HTTPS. '
             if entorno == 'laboratorio' else
             f'IP fija {ip_estatica} (máscara {IP_MASCARA}, puerta de enlace {IP_GATEWAY}), '
             f'apuntando al servidor {host_srv}:{PUERTO_SERVIDOR_PLACAS}. ')
        # Ya grabada en la placa: se anota para que no se le dé a otra.
        if dev_id and ip_estatica:
            ok_ip, msg_ip = _ip_estatica_guardar(dev_id, ip_estatica, tipo='rfid')
            if not ok_ip:
                red += f'AVISO: la IP no se pudo anotar en la app ({msg_ip}). '
        elif ip_estatica:
            _ip_estatica_reservar_sin_placa(ip_estatica, tipo='rfid')
            red += ('AVISO: no se pudo leer el identificador del lector. La IP queda reservada para '
                    'que no se le dé a otra placa, y se asignará sola en cuanto el lector aparezca '
                    'en Admin → IPs de placas. ')
        return jsonify({'success': True,
                        'message': f'Lector configurado y firmware subido por {puerto}. {red}'
                                              + ('El perfil gen4+PN532 queda registrado al conectarse al WiFi.'
                                                  ' Las actualizaciones de su firmware se cargan por USB.'
                                                  if perfil == 'gen4_pn532' else
                                                  'A partir de ahora se actualiza solo por WiFi cuando publiques una '
                                                  'nueva FW_VERSION en esp32/main.py.')})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False,
                        'message': 'Timeout: comprueba que la placa está conectada a ese puerto y que '
                                   'ningún otro programa (monitor serie, mpremote...) lo está usando.'})
    except Exception as e:
        return error_interno(e)


# ==================== GRABAR MICROPYTHON EN PLACA NUEVA (esptool) ====================
#
# Los /api/esp32/*/flash_usb de arriba usan mpremote, que habla el protocolo
# REPL de MicroPython: solo funcionan si la placa YA tiene MicroPython. Una
# placa recien sacada de la caja no responde a mpremote, y hasta ahora habia
# que bajar a flash_esp32.ps1 a mano. Esto cubre ese primer paso con esptool:
# borra la flash y graba el firmware de MicroPython. A partir de ahi ya valen
# los flash_usb existentes.
#
# El .bin NO se descarga aqui: se busca en disco (repo o subido desde el
# navegador) para que el PC del taller no dependa de tener internet.

# Direccion de escritura del firmware segun el chip. MicroPython para ESP32
# clasico va en 0x1000 (antes esta el bootloader); los S3/C3/S2 llevan el
# bootloader dentro del propio .bin y van en 0x0. Equivocarse aqui deja la
# placa sin arrancar, asi que no hay un valor por defecto "generico".
_OFFSET_POR_CHIP = {
    'esp32':   '0x1000',
    'esp32s2': '0x1000',
    'esp32s3': '0x0',
    'esp32c3': '0x0',
    'esp32c6': '0x0',
}

# VID USB -> chip puente serie. Sirve para decir al usuario que driver le
# falta cuando Windows no le da puerto COM a la placa.
_USB_SERIE_CONOCIDOS = {
    '1A86': {'chip': 'CH340/CH341', 'driver': 'ch340',  'fabricante': 'WCH'},
    '10C4': {'chip': 'CP210x',      'driver': 'cp210x', 'fabricante': 'Silicon Labs'},
    '0403': {'chip': 'FTDI FT232',  'driver': 'ftdi',   'fabricante': 'FTDI'},
    '303A': {'chip': 'USB nativo del ESP32-S2/S3', 'driver': None, 'fabricante': 'Espressif'},
}


def _dirs_firmware():
    """Carpetas donde se buscan los .bin de MicroPython, por prioridad.

    - esp32/firmware/ y la raiz del repo: firmwares versionados con el codigo.
    - DATA_DIR/firmware/: los subidos desde el navegador en esta instalacion
      (no van al repo; cada taller sube los que necesite).
    """
    proyecto = os.path.dirname(current_app.root_path)
    return [
        os.path.join(proyecto, 'esp32', 'firmware'),
        proyecto,
        os.path.join(current_app.config['DATA_DIR'], 'firmware'),
    ]


def _chip_desde_nombre(nombre):
    """Deduce el chip del nombre del .bin de micropython.org.

    'ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin' -> 'esp32s3'
    'ESP32_GENERIC-20260406-v1.28.0.bin'               -> 'esp32'
    Devuelve None si no se reconoce (entonces lo elige el usuario a mano).

    Es solo el plan B de _chip_desde_binario: el nombre lo pone quien descarga
    el fichero y puede llegar renombrado.
    """
    n = nombre.upper()
    for sufijo, chip in (('_S3', 'esp32s3'), ('_S2', 'esp32s2'),
                         ('_C3', 'esp32c3'), ('_C6', 'esp32c6')):
        if f'ESP32{sufijo}' in n or f'ESP32_GENERIC{sufijo}' in n:
            return chip
    if 'ESP32' in n:
        return 'esp32'
    return None


# chip_id que Espressif graba en la cabecera de la imagen -> chip nuestro.
_CHIP_ID_IMAGEN = {
    0x0000: 'esp32',
    0x0002: 'esp32s2',
    0x0005: 'esp32c3',
    0x0009: 'esp32s3',
    0x000D: 'esp32c6',
}

# Los dos binarios versionados corresponden a las dos placas que se usan hoy.
# Los ficheros subidos por Admin siguen admitiendose sin etiqueta para no
# bloquear una futura ampliacion de hardware.
_MODELO_FIRMWARE = {
    'ESP32_GENERIC-20260406-v1.28.0.bin': 'Lector RFID - ESP32 DevKit + RC522',
    'ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin': 'Pantalla gen4-ESP32-24',
}


def _chip_desde_binario(ruta):
    """Lee el chip real de la cabecera del .bin, o None si no se puede.

    Una imagen ESP empieza por el byte magico 0xE9 y lleva el chip_id en los
    bytes 12-13 (little endian) de la cabecera extendida. Esto es la fuente
    de verdad: el nombre del fichero puede venir renombrado, pero la cabecera
    no miente, y grabar el firmware de otro chip deja la placa sin arrancar.
    """
    try:
        with open(ruta, 'rb') as f:
            cabecera = f.read(16)
        if len(cabecera) < 14 or cabecera[0] != 0xE9:
            return None
        chip_id = int.from_bytes(cabecera[12:14], 'little')
        return _CHIP_ID_IMAGEN.get(chip_id)
    except OSError:
        return None


def _listar_firmwares():
    """Los .bin encontrados, sin duplicar nombres (gana la primera carpeta)."""
    vistos = {}
    for carpeta in _dirs_firmware():
        if not os.path.isdir(carpeta):
            continue
        try:
            nombres = sorted(os.listdir(carpeta))
        except OSError:
            continue
        for nombre in nombres:
            if not nombre.lower().endswith('.bin') or nombre in vistos:
                continue
            ruta = os.path.join(carpeta, nombre)
            if not os.path.isfile(ruta):
                continue
            # La cabecera manda; el nombre solo si el fichero no es legible
            # como imagen ESP (p.ej. un .bin de otra cosa).
            chip = _chip_desde_binario(ruta) or _chip_desde_nombre(nombre)
            vistos[nombre] = {
                'nombre': nombre,
                'modelo': _MODELO_FIRMWARE.get(nombre, ''),
                'tamano_mb': round(os.path.getsize(ruta) / (1024 * 1024), 2),
                'chip': chip,
                'offset': _OFFSET_POR_CHIP.get(chip or '', ''),
            }
    return list(vistos.values())


def _ruta_firmware_segura(nombre):
    """Ruta del .bin por nombre, garantizada dentro de una carpeta conocida.

    Se compara la ruta ya resuelta contra cada carpeta permitida, de modo que
    un nombre con '..' o separadores no pueda apuntar fuera.
    """
    nombre = (nombre or '').strip()
    if not nombre or not nombre.lower().endswith('.bin'):
        return None
    for carpeta in _dirs_firmware():
        base = os.path.abspath(carpeta)
        ruta = os.path.abspath(os.path.join(base, nombre))
        if os.path.commonpath([ruta, base]) == base and os.path.isfile(ruta):
            return ruta
    return None


@bp.route('/api/esp32/firmwares', methods=['GET'])
@requiere_pin_admin
def api_esp32_firmwares():
    """Firmwares de MicroPython disponibles en este servidor."""
    try:
        return jsonify({'success': True, 'firmwares': _listar_firmwares()})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/firmwares', methods=['POST'])
@requiere_pin_admin
def api_esp32_firmware_subir():
    """Sube un .bin de MicroPython a DATA_DIR/firmware/.

    Evita tener que copiar ficheros a mano por el explorador: se descarga de
    micropython.org en cualquier PC con internet y se sube aqui una sola vez.
    """
    try:
        if 'firmware' not in request.files:
            return jsonify({'success': False, 'message': 'No se envió ningún archivo'}), 400
        archivo = request.files['firmware']
        nombre = secure_filename(archivo.filename or '')
        if not nombre:
            return jsonify({'success': False, 'message': 'Nombre de archivo vacío'}), 400
        if not nombre.lower().endswith('.bin'):
            return jsonify({'success': False, 'message': 'El firmware debe ser un fichero .bin'}), 400

        destino_dir = os.path.join(current_app.config['DATA_DIR'], 'firmware')
        os.makedirs(destino_dir, exist_ok=True)
        destino = os.path.join(destino_dir, nombre)
        archivo.save(destino)

        # Un firmware de MicroPython ronda 1-2 MB; algo de 2 KB es casi seguro
        # una pagina de error HTML guardada por error desde el navegador.
        tam = os.path.getsize(destino)
        if tam < 64 * 1024:
            os.remove(destino)
            return jsonify({'success': False,
                            'message': f'El fichero solo ocupa {tam} bytes: no parece un firmware '
                                       'de MicroPython (deberían ser 1-2 MB). ¿Descargaste el .bin correcto?'}), 400

        return jsonify({'success': True,
                        'message': f'Firmware {nombre} subido ({round(tam / (1024 * 1024), 2)} MB).',
                        'firmwares': _listar_firmwares()})
    except Exception as e:
        return error_interno(e, 'Error al subir el firmware')


@bp.route('/api/esp32/grabar_micropython', methods=['POST'])
@requiere_pin_admin
def api_esp32_grabar_micropython():
    """Borra la flash y graba MicroPython en una placa nueva (esptool).

    Es el paso previo a /api/esp32/flash_usb y /api/esp32/rfid/flash_usb, que
    necesitan que la placa ya hable MicroPython.

    OJO: borra por completo lo que hubiera en la placa (en las pantallas 4D
    Systems, eso incluye el firmware original de fábrica).
    """
    try:
        data = request.get_json(force=True) or {}
        puerto = str(data.get('puerto', '')).strip()
        if not puerto or not re.fullmatch(r'[A-Za-z0-9/._:-]+', puerto):
            return jsonify({'success': False, 'message': 'Puerto no válido'}), 400

        firmware = str(data.get('firmware', '')).strip()
        ruta_fw = _ruta_firmware_segura(firmware)
        if not ruta_fw:
            return jsonify({'success': False,
                            'message': 'Firmware no encontrado. Súbelo primero desde esta misma pantalla.'}), 400

        # El chip real sale de la cabecera del .bin. Si se puede leer, manda
        # sobre lo que pida el cliente: grabar el firmware de otro chip (o en
        # el offset de otro chip) deja la placa sin arrancar, y recuperarla
        # exige volver a esto mismo con el fichero correcto.
        chip_binario = _chip_desde_binario(ruta_fw)
        chip_pedido = str(data.get('chip', '')).strip().lower()

        if chip_binario and chip_pedido and chip_pedido != chip_binario:
            return jsonify({'success': False,
                            'message': f'El firmware "{firmware}" es para {chip_binario}, pero se ha '
                                       f'pedido grabarlo como {chip_pedido}. Grabarlo así dejaría la '
                                       f'placa sin arrancar, así que no se hace.'}), 400

        chip = chip_binario or chip_pedido or _chip_desde_nombre(firmware)
        if chip not in _OFFSET_POR_CHIP:
            return jsonify({'success': False,
                            'message': f'No se reconoce el chip del firmware "{firmware}" (ni por su '
                                       f'cabecera ni por su nombre). ¿Es un firmware de MicroPython? '
                                       f'Chips soportados: {", ".join(sorted(_OFFSET_POR_CHIP))}.'}), 400
        offset = _OFFSET_POR_CHIP[chip]

        def esptool(*args, timeout=180):
            # Comandos con guion bajo (erase_flash / write_flash): esptool 5
            # los mantiene como alias y esptool 4 solo entiende estos, asi
            # que funciona con las dos versiones.
            return subprocess.run(
                [sys.executable, '-m', 'esptool', '--chip', chip, '--port', puerto] + list(args),
                capture_output=True, text=True, timeout=timeout)

        r = esptool('erase_flash')
        if r.returncode != 0:
            err = (r.stderr or r.stdout or '').strip()
            if 'No module named' in err:
                return jsonify({'success': False,
                                'message': 'esptool no está instalado en este servidor. '
                                           'Ejecuta: pip install -r requirements.txt'})
            return jsonify({'success': False,
                            'message': ('Error al borrar la flash: ' + err)[-500:]})

        r = esptool('--baud', '460800', 'write_flash', '-z', offset, ruta_fw, timeout=300)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or '').strip()
            return jsonify({'success': False,
                            'message': ('Error al grabar el firmware: ' + err)[-500:]})

        return jsonify({
            'success': True,
            'message': (f'MicroPython grabado en {puerto} ({chip}, offset {offset}). '
                        'La placa reenumera el puerto USB: espera unos segundos, vuelve a '
                        'buscar puertos y ya puedes subirle el firmware de la aplicación.'),
            'chip': chip,
            'offset': offset,
            'firmware': firmware,
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False,
                        'message': 'Timeout grabando la placa. Comprueba que está en el puerto indicado, '
                                   'que ningún otro programa lo está usando y que el cable USB es de datos '
                                   '(algunos cables baratos solo llevan corriente).'})
    except Exception as e:
        return error_interno(e)


# ==================== DRIVERS USB-SERIE (puerto COM no reconocido) ====================
#
# Cuando Windows no le asigna puerto COM a la placa, casi siempre falta el
# driver del puente USB-serie (CH340 en los DevKit baratos, CP210x en los
# oficiales). Aqui se detecta que chip hay y si Windows lo ha reconocido, y
# se puede lanzar el instalador. El instalador NO se descarga: se busca en
# DATA_DIR/drivers/, para que funcione en un taller sin internet.

def _dir_drivers():
    return os.path.join(current_app.config['DATA_DIR'], 'drivers')


# Como se llama cada instalador y de donde sacarlo si no esta.
_DRIVERS = {
    'ch340': {
        'nombre': 'CH340 / CH341 (WCH)',
        'patrones': ('ch341ser', 'ch340'),
        'url': 'https://www.wch-ic.com/downloads/CH341SER_EXE.html',
    },
    'cp210x': {
        'nombre': 'CP210x (Silicon Labs)',
        'patrones': ('cp210x', 'cp210'),
        'url': 'https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers',
    },
    'ftdi': {
        'nombre': 'FTDI VCP',
        'patrones': ('ftdi', 'cdm'),
        'url': 'https://ftdichip.com/drivers/vcp-drivers/',
    },
}


def _instalador_local(clave):
    """Ruta del instalador de ese driver en DATA_DIR/drivers/, o None."""
    carpeta = _dir_drivers()
    if not os.path.isdir(carpeta):
        return None
    patrones = _DRIVERS.get(clave, {}).get('patrones', ())
    try:
        nombres = sorted(os.listdir(carpeta))
    except OSError:
        return None
    for nombre in nombres:
        if not nombre.lower().endswith(('.exe', '.msi')):
            continue
        if any(p in nombre.lower() for p in patrones):
            ruta = os.path.join(carpeta, nombre)
            if os.path.isfile(ruta):
                return ruta
    return None


def _dispositivos_usb_windows():
    """Dispositivos USB-serie vistos por Windows, con su estado.

    Usa Get-PnpDevice, que a diferencia de list_ports tambien lista los que
    NO tienen driver -- justo el caso que interesa aqui. Fuera de Windows
    devuelve lista vacia.
    """
    if not sys.platform.startswith('win'):
        return []
    ps = (
        "Get-PnpDevice -PresentOnly | "
        "Where-Object { $_.InstanceId -like 'USB*' } | "
        "Select-Object Status,Class,FriendlyName,InstanceId | ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or not r.stdout.strip():
            return []
        datos = json.loads(r.stdout)
    except Exception:
        return []
    if isinstance(datos, dict):
        datos = [datos]
    return datos if isinstance(datos, list) else []


@bp.route('/api/esp32/drivers/estado', methods=['GET'])
@requiere_pin_admin
def api_esp32_drivers_estado():
    """Que puentes USB-serie ve Windows, si les falta driver y si hay instalador.

    Pensado para el caso "he enchufado la placa y no aparece ningún puerto COM".
    """
    try:
        if not sys.platform.startswith('win'):
            return jsonify({
                'success': True, 'windows': False, 'dispositivos': [],
                'drivers': [{'clave': k, 'nombre': v['nombre'], 'url': v['url'],
                             'instalador': None} for k, v in _DRIVERS.items()],
                'aviso': 'Este servidor no es Windows: la instalación de drivers '
                         'solo aplica al PC local que ejecuta la aplicación.',
            })

        dispositivos = []
        for d in _dispositivos_usb_windows():
            instance = str(d.get('InstanceId') or '')
            m = re.search(r'VID_([0-9A-Fa-f]{4})', instance)
            vid = (m.group(1).upper() if m else '')
            conocido = _USB_SERIE_CONOCIDOS.get(vid)
            estado = str(d.get('Status') or '')
            # Un puente serie con driver correcto queda en la clase 'Ports';
            # si Windows no lo reconoce se queda en Status 'Error' o Class vacia.
            necesita_driver = bool(conocido) and (estado.upper() == 'ERROR'
                                                  or str(d.get('Class') or '') not in ('Ports', 'USB'))
            if conocido or necesita_driver:
                dispositivos.append({
                    'nombre': d.get('FriendlyName') or '(sin nombre)',
                    'estado': estado,
                    'clase': d.get('Class') or '',
                    'vid': vid,
                    'chip': (conocido or {}).get('chip', 'desconocido'),
                    'driver': (conocido or {}).get('driver'),
                    'necesita_driver': necesita_driver,
                })

        drivers = []
        for clave, info in _DRIVERS.items():
            ruta = _instalador_local(clave)
            drivers.append({
                'clave': clave,
                'nombre': info['nombre'],
                'url': info['url'],
                'instalador': os.path.basename(ruta) if ruta else None,
            })

        return jsonify({'success': True, 'windows': True,
                        'dispositivos': dispositivos, 'drivers': drivers})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/drivers/instalar', methods=['POST'])
@requiere_pin_admin
def api_esp32_driver_instalar():
    """Lanza el instalador del driver indicado, pidiendo elevación a Windows.

    El servidor corre como usuario normal, asi que el instalador se lanza con
    'Start-Process -Verb RunAs': Windows muestra el aviso de UAC en el PC y
    alguien tiene que aceptarlo fisicamente. No es desatendido a proposito.
    """
    try:
        if not sys.platform.startswith('win'):
            return jsonify({'success': False,
                            'message': 'Solo se puede instalar drivers desde el PC Windows '
                                       'que ejecuta la aplicación.'}), 400

        data = request.get_json(silent=True) or {}
        clave = str(data.get('driver', '')).strip().lower()
        if clave not in _DRIVERS:
            return jsonify({'success': False, 'message': 'Driver desconocido'}), 400

        ruta = _instalador_local(clave)
        if not ruta:
            info = _DRIVERS[clave]
            return jsonify({'success': False,
                            'message': f'No hay instalador de {info["nombre"]} en el servidor. '
                                       f'Descárgalo de {info["url"]} y súbelo desde esta pantalla.'}), 404

        # El instalador solo puede salir de nuestra carpeta de drivers.
        base = os.path.abspath(_dir_drivers())
        if os.path.commonpath([os.path.abspath(ruta), base]) != base:
            return jsonify({'success': False, 'message': 'Ruta de instalador no válida'}), 400

        r = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command',
             'Start-Process -FilePath $env:CCR_DRIVER_EXE -Verb RunAs'],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'CCR_DRIVER_EXE': os.path.abspath(ruta)})
        if r.returncode != 0:
            err = (r.stderr or r.stdout or '').strip()
            return jsonify({'success': False,
                            'message': ('No se pudo lanzar el instalador (¿se canceló el aviso de '
                                        'Windows?): ' + err)[-400:]})

        return jsonify({'success': True,
                        'message': f'Instalador {os.path.basename(ruta)} lanzado. Acepta el aviso de '
                                   'Windows en el PC y sigue los pasos; al terminar, desenchufa y '
                                   'vuelve a enchufar la placa y busca puertos otra vez.'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False,
                        'message': 'Timeout al lanzar el instalador (¿hay un aviso de Windows '
                                   'esperando respuesta en el PC?).'})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/drivers/subir', methods=['POST'])
@requiere_pin_admin
def api_esp32_driver_subir():
    """Sube el instalador de un driver a DATA_DIR/drivers/."""
    try:
        if 'driver' not in request.files:
            return jsonify({'success': False, 'message': 'No se envió ningún archivo'}), 400
        archivo = request.files['driver']
        nombre = secure_filename(archivo.filename or '')
        if not nombre:
            return jsonify({'success': False, 'message': 'Nombre de archivo vacío'}), 400
        if not nombre.lower().endswith(('.exe', '.msi')):
            return jsonify({'success': False,
                            'message': 'El instalador debe ser un .exe o .msi. Si lo has descargado '
                                       'como .zip, descomprímelo antes.'}), 400

        # El nombre debe encajar con algun driver conocido: asi el boton de
        # instalar lo encuentra despues, y no se acumulan .exe sueltos.
        if not any(any(p in nombre.lower() for p in info['patrones'])
                   for info in _DRIVERS.values()):
            esperados = ', '.join(sorted({p for i in _DRIVERS.values() for p in i['patrones']}))
            return jsonify({'success': False,
                            'message': f'No se reconoce "{nombre}" como instalador de un driver '
                                       f'soportado. El nombre debe contener uno de: {esperados}.'}), 400

        destino_dir = _dir_drivers()
        os.makedirs(destino_dir, exist_ok=True)
        archivo.save(os.path.join(destino_dir, nombre))
        return jsonify({'success': True, 'message': f'Instalador {nombre} subido.'})
    except Exception as e:
        return error_interno(e, 'Error al subir el instalador')


# ==================== CREDENCIALES WIFI DE LAS PLACAS ====================
#
# SSID y clave de la red a la que se conectan las placas (hoy el TL-WR802N de
# planta). Se guardan una vez y precargan los formularios de "Subir por USB",
# para no reescribirlas en cada placa.
#
# Aqui hubo tambien un control del "hosted network" de Windows (netsh) para
# levantar un hotspot desde el propio PC. Se ha quitado: la planta usa un
# punto de acceso fisico, ese mecanismo esta obsoleto en Windows moderno y
# dependia del driver del adaptador, asi que era codigo que solo podia dar
# problemas. Si algun dia hiciera falta, se activa el Hotspot movil de Windows
# a mano y basta con guardar aqui el mismo SSID/clave.

def _hotspot_file():
    return os.path.join(current_app.config['DATA_DIR'], 'wifi_hotspot.json')


def _hotspot_cargar():
    try:
        with open(_hotspot_file(), encoding='utf-8') as f:
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
        with open(_hotspot_file(), 'w', encoding='utf-8') as f:
            json.dump({'ssid': ssid, 'password': password}, f)
        return jsonify({'success': True})
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
