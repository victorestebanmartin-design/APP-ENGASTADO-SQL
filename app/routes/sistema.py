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

        # Actualizar dependencias si es necesario
        pip_output = ''
        if req_cambia:
            pip_exe = os.path.join(base_dir, 'venv', 'Scripts', 'pip.exe')
            if not os.path.exists(pip_exe):
                pip_exe = os.path.join(base_dir, 'venv', 'bin', 'pip')
            r_pip = subprocess.run(
                [pip_exe, 'install', '-r', os.path.join(base_dir, 'requirements.txt'), '-q'],
                capture_output=True, text=True, timeout=120
            )
            pip_output = ' | Dependencias actualizadas.' if r_pip.returncode == 0 else ' | ⚠️ Error al actualizar dependencias.'

        # Commit nuevo tras el pull
        r_new = git(['log', '-1', '--format=%h — %s (%cr)'])
        commit_nuevo = r_new.stdout.strip()

        # Programar reinicio: esperar 2s para que Flask envíe la respuesta primero
        import threading
        def _reiniciar():
            import time, os
            time.sleep(2)
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
        from datetime import datetime
        ahora = datetime.now()
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


@bp.route('/api/esp32/push', methods=['POST', 'OPTIONS'])
def api_esp32_push():
    """Recibe datos de trabajo desde el navegador y los almacena para que el ESP32 los recoja."""
    if request.method == 'OPTIONS':
        resp = current_app.make_response('')
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp
    try:
        data = request.get_json(force=True) or {}
        push_file = os.path.join(os.path.dirname(current_app.root_path), 'data', 'esp32_current.json')
        from datetime import datetime
        payload = {'data': data, 'ts': datetime.now().isoformat()}
        with open(push_file, 'w') as f:
            json.dump(payload, f)
        resp = current_app.make_response(jsonify({'ok': True}))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        return error_interno(e)


@bp.route('/api/esp32/current', methods=['GET'])
def api_esp32_current():
    """Devuelve los últimos datos de trabajo enviados al ESP32 (TTL 5 min)."""
    try:
        push_file = os.path.join(os.path.dirname(current_app.root_path), 'data', 'esp32_current.json')
        if not os.path.exists(push_file):
            return jsonify({'data': None})
        with open(push_file) as f:
            payload = json.load(f)
        # Expirar tras 5 minutos
        from datetime import datetime
        ts = datetime.fromisoformat(payload.get('ts', '2000-01-01'))
        if (datetime.now() - ts).total_seconds() > 300:
            return jsonify({'data': None})
        return jsonify({'data': payload['data'], 'ts': payload['ts']})
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
