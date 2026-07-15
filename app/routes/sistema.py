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

@bp.route('/api/exportar/config', methods=['POST'])
@requiere_pin_admin
def api_exportar_config():
    """Exporta configuración pura (puestos, máquinas, etc.) en ZIP."""
    try:
        manager = ConfigManager(db)
        contenido, nombre = manager.exportar(incluir_produccion=False)
        
        return send_file(
            io.BytesIO(contenido),
            mimetype='application/zip',
            as_attachment=True,
            download_name=nombre
        )
    except Exception as e:
        return error_interno(e, 'Error al exportar configuración', clave='error')


@bp.route('/api/exportar/completo', methods=['POST'])
@requiere_pin_admin
def api_exportar_completo():
    """Exporta configuración + datos de producción (órdenes, bonos, etc.) en ZIP."""
    try:
        manager = ConfigManager(db)
        contenido, nombre = manager.exportar(incluir_produccion=True)
        
        return send_file(
            io.BytesIO(contenido),
            mimetype='application/zip',
            as_attachment=True,
            download_name=nombre
        )
    except Exception as e:
        return error_interno(e, 'Error al exportar datos completos', clave='error')


@bp.route('/api/importar/config', methods=['POST'])
@requiere_pin_admin
def api_importar_config():
    """
    Importa configuración desde un ZIP.
    
    Parámetros POST:
      - file: archivo ZIP
      - modo: 'merge' (actualiza existentes) o 'replace' (borra y recrea)
      - incluir_produccion: 'true' o 'false' para incluir datos de producción
    """
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No se proporcionó archivo'}), 400
        
        archivo = request.files['file']
        if not archivo or not archivo.filename.endswith('.zip'):
            return jsonify({'success': False, 'error': 'El archivo debe ser un ZIP'}), 400
        
        # Leer parámetros
        modo = request.form.get('modo', 'merge')
        merge = (modo == 'merge')
        incluir_produccion = request.form.get('incluir_produccion', 'false').lower() == 'true'
        
        # Leer contenido del ZIP
        contenido = archivo.read()
        
        # Importar
        manager = ConfigManager(db)
        resultado = manager.importar(
            contenido,
            merge=merge,
            incluir_produccion=incluir_produccion
        )
        
        return jsonify(resultado)
    
    except Exception as e:
        return error_interno(e, 'Error al importar configuración', clave='error')
