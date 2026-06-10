"""
Rutas principales de la aplicación Flask con SQLite
"""
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, send_file
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

try:
    from zoneinfo import ZoneInfo
    _TZ_LOCAL = ZoneInfo('Europe/Madrid')
except Exception:
    _TZ_LOCAL = None


def _ahora_iso() -> str:
    """Hora local real (Europe/Madrid) en isoformat naive.

    El servidor (PythonAnywhere) corre en UTC; sin esto las fechas se guardaban
    2 horas por detrás. Devolvemos la hora local de España para que el report
    anote la hora real.
    """
    if _TZ_LOCAL is not None:
        return datetime.now(_TZ_LOCAL).replace(tzinfo=None).isoformat()
    return datetime.now().isoformat()


def _detectar_hoja(filepath: str) -> str:
    """Devuelve 'Format' si existe en el archivo, sino la primera hoja disponible."""
    xl = pd.ExcelFile(filepath)
    return 'Format' if 'Format' in xl.sheet_names else xl.sheet_names[0]


# Blueprint principal
bp = Blueprint('main', __name__)

# Instancia global de DB
db = None

def init_routes(app):
    """Inicializar rutas con la instancia de DB"""
    global db
    db = app.extensions['db']
    app.register_blueprint(bp)


# ==================== UTILIDADES ====================

def allowed_file(filename):
    """Verificar si el archivo tiene una extensión permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def _es_error_nombre_bono_duplicado(error):
    """Detectar si un IntegrityError proviene del UNIQUE de bonos.nombre"""
    mensaje = str(getattr(error, 'orig', error)).lower()
    return 'unique' in mensaje and 'bonos.nombre' in mensaje


def error_interno(e, mensaje_usuario='Error interno del servidor'):
    """
    Maneja un error 500 sin filtrar detalles internos al cliente.

    Genera un ID corto de error, registra el traceback completo en el log
    con ese ID, y devuelve un JSON genérico (sin str(e)) con la referencia.
    """
    import uuid
    error_id = uuid.uuid4().hex[:8]
    current_app.logger.exception(f"[{error_id}] {mensaje_usuario}: {e}")
    return jsonify({
        'success': False,
        'message': f'{mensaje_usuario} (ref: {error_id})'
    }), 500


# ==================== RUTAS PRINCIPALES ====================

@bp.route('/')
def home():
    """Página de inicio"""
    return render_template('home.html')


@bp.route('/modules')
def modules():
    """Página de módulos del sistema"""
    return render_template('modules.html')


@bp.route('/v3')
def index_v3():
    """Vista principal V3 - Sistema de bonos"""
    return render_template('index-v3.html')


@bp.route('/admin')
def admin():
    """Panel de administración"""
    return render_template('admin.html')


@bp.route('/gestion-puestos')
def gestion_puestos():
    """Gestión de puestos y máquinas"""
    return render_template('gestion-puestos.html')


@bp.route('/visualizacion')
def visualizacion():
    """Visualización y monitoreo"""
    return render_template('visualizacion.html', bono_inicial='')


@bp.route('/visualizacion/<string:nombre_bono>')
def visualizacion_bono(nombre_bono):
    """Visualización pre-seleccionando un bono concreto"""
    return render_template('visualizacion.html', bono_inicial=nombre_bono)


@bp.route('/progreso-bono')
def progreso_bono():
    """Dashboard de progreso ponderado (sin bono específico)"""
    return render_template('progreso-bono.html', bono_nombre='')


@bp.route('/progreso-bono/<string:nombre_bono>')
def progreso_bono_especifico(nombre_bono):
    """Dashboard de progreso ponderado para un bono concreto"""
    return render_template('progreso-bono.html', bono_nombre=nombre_bono)


@bp.route('/etiquetas')
def etiquetas():
    """Generación de etiquetas"""
    return render_template('etiquetas.html')


def _respuesta_descarga_manguitos(ficheros: dict, ref: str, edicion: str):
    """
    Dado un dict {nombre_fichero: contenido_str}, devuelve:
    - Un .txt directamente si sólo hay un fichero.
    - Un .zip con todos si hay más de uno.
    """
    if len(ficheros) == 0:
        return jsonify({'success': False, 'error': 'No se generó ningún fichero'})
    if len(ficheros) == 1:
        nombre, contenido = next(iter(ficheros.items()))
        buf = io.BytesIO(contenido.encode('utf-8'))
        buf.seek(0)
        return send_file(buf, mimetype='text/plain', as_attachment=True,
                         download_name=nombre)
    # Múltiples ficheros → ZIP
    zip_buf = io.BytesIO()
    with _zipfile.ZipFile(zip_buf, 'w', _zipfile.ZIP_DEFLATED) as zf:
        for nombre, contenido in ficheros.items():
            zf.writestr(nombre, contenido.encode('utf-8'))
    zip_buf.seek(0)
    zip_nombre = f"{ref} {edicion} manguitos.zip"
    return send_file(zip_buf, mimetype='application/zip', as_attachment=True,
                     download_name=zip_nombre)


@bp.route('/manguitos')
def manguitos():
    """Guiado de colocación y pedidos de manguitos"""
    return render_template('manguitos.html')


@bp.route('/mangueras')
def mangueras():
    """Preparación de mangueras"""
    return render_template('mangueras.html')


@bp.route('/api/mangueras/datos', methods=['POST'])
def api_mangueras_datos():
    """Carga las filas del Excel con instrucciones de pelado en Observaciones"""
    data = request.get_json() or {}
    archivo = data.get('archivo', '').strip()
    if not archivo:
        return jsonify({'success': False, 'error': 'Archivo no especificado'})
    try:
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'data/cortes')
        em = ExcelManager(upload_folder)
        resultado = em.get_mangueras(archivo)

        # Enriquecer con numero_etiqueta desde la BD (mismo patrón que manguitos)
        try:
            with db.engine.connect() as conn:
                rows_full = conn.execute(text(
                    """SELECT elemento, numero_etiqueta, sub_numero, cod_cable
                       FROM etiquetas_elementos
                       WHERE archivo_excel = :arch AND es_grupo_padre = 0"""
                ), {'arch': archivo}).fetchall()
            num_map = {}      # clave exacta: (cod_cable.upper(), elemento)
            num_map_elem = {} # fallback: solo elemento (primer match)
            for r in rows_full:
                elem_name, num_etq, sub_num, cod = r[0], r[1], r[2], (r[3] or '').strip().upper()
                label = f"{num_etq}.{str(int(sub_num)).zfill(2)}" if sub_num and int(sub_num) > 0 else str(num_etq)
                entry = {'label': label, 'num': num_etq}
                num_map[(cod, elem_name)] = entry
                if elem_name not in num_map_elem:
                    num_map_elem[elem_name] = entry
            for mg in resultado:
                elem = mg.get('de_elemento', '')
                cod  = (mg.get('cod_cable') or '').strip().upper()
                etq  = num_map.get((cod, elem)) or num_map_elem.get(elem)
                mg['numero_etiqueta']     = etq['label'] if etq else None
                mg['numero_etiqueta_int'] = etq['num']   if etq else None
        except Exception:
            pass  # Si no hay etiquetas cargadas, no es crítico

        return jsonify({'success': True, 'mangueras': resultado})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/api/manguitos/datos', methods=['POST'])
def api_manguitos_datos():
    """Carga y agrupa los manguitos de un Excel por elemento"""
    data = request.get_json() or {}
    archivo = data.get('archivo', '').strip()
    if not archivo:
        return jsonify({'success': False, 'error': 'Archivo no especificado'})
    try:
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'data/cortes')
        em = ExcelManager(upload_folder)
        resultado = em.get_manguitos(archivo)

        # Enriquecer cada manguito individual con su numero_etiqueta según (cod_cable, elemento)
        try:
            with db.engine.connect() as conn:
                rows = conn.execute(text(
                    """SELECT elemento, numero_etiqueta, sub_numero, cod_cable
                       FROM etiquetas_elementos
                       WHERE archivo_excel = :arch AND es_grupo_padre = 0"""
                ), {'arch': archivo}).fetchall()
            num_map_full = {}   # (cod_cable.upper(), elemento) -> label
            num_map_elem = {}   # elemento -> label (fallback: primer match)
            for r in rows:
                elem_name, num_etq, sub_num, cod = r[0], r[1], r[2], (r[3] or '').strip().upper()
                label = f"{num_etq}.{str(int(sub_num)).zfill(2)}" if sub_num and int(sub_num) > 0 else str(num_etq)
                num_map_full[(cod, elem_name)] = label
                if elem_name not in num_map_elem:
                    num_map_elem[elem_name] = label
            for elem in resultado:
                for mg in elem.get('manguitos', []):
                    cod = (mg.get('cod_cable') or '').strip().upper()
                    mg['numero_etiqueta'] = num_map_full.get((cod, elem['elemento'])) or num_map_elem.get(elem['elemento'])
                # numero_etiqueta del grupo = primer manguito (para el título)
                mgs = elem.get('manguitos', [])
                elem['numero_etiqueta'] = mgs[0]['numero_etiqueta'] if mgs else None
            # Ordenar elementos por numero_etiqueta ascendente
            def _etq_sort(e):
                v = e.get('numero_etiqueta')
                try:
                    return float(v) if v else float('inf')
                except (ValueError, TypeError):
                    return float('inf')
            resultado.sort(key=_etq_sort)
        except Exception:
            pass  # Si no hay etiquetas cargadas, no es crítico

        return jsonify({'success': True, 'elementos': resultado})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/api/manguitos/generar-txt', methods=['POST'])
def api_manguitos_generar_txt():
    """Genera un TXT por código de manguito, ordenado por número de etiqueta"""
    data = request.get_json() or {}
    archivo = data.get('archivo', '').strip()
    ref     = data.get('ref', 'PC_CAB_BADEN').strip()
    edicion = data.get('edicion', 'ed_04').strip()
    if not archivo:
        return jsonify({'success': False, 'error': 'Archivo no especificado'})
    try:
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'data/cortes')
        em = ExcelManager(upload_folder)
        elementos = em.get_manguitos(archivo)

        # Obtener numero_etiqueta formateado por elemento desde BD
        num_map = {}
        try:
            with db.engine.connect() as conn:
                rows = conn.execute(text(
                    """SELECT elemento, numero_etiqueta, sub_numero
                       FROM etiquetas_elementos
                       WHERE archivo_excel = :arch AND es_grupo_padre = 0"""
                ), {'arch': archivo}).fetchall()
            for r in rows:
                elem_name, num_etq, sub_num = r[0], r[1], r[2]
                if elem_name not in num_map:
                    if sub_num and int(sub_num) > 0:
                        num_map[elem_name] = f"{num_etq}.{str(int(sub_num)).zfill(2)}"
                    else:
                        num_map[elem_name] = str(num_etq)
        except Exception:
            pass

        # Aplanar: lista de manguitos con su numero de etiqueta para ordenar
        lista_plana = []
        for elem in elementos:
            num_str = num_map.get(elem['elemento'])
            try:
                num_float = float(num_str) if num_str else float('inf')
            except (ValueError, TypeError):
                num_float = float('inf')
            for m in elem['manguitos']:
                lista_plana.append((num_float, m))

        # Ordenar por numero de etiqueta (sort estable preserva orden Excel dentro del mismo elemento)
        lista_plana.sort(key=lambda x: x[0])

        # Agrupar por codigo de manguito preservando orden de aparición
        grupos = {}
        orden_codigos = []
        for _, m in lista_plana:
            codigo = m['de_manguito']
            if codigo not in grupos:
                grupos[codigo] = []
                orden_codigos.append(codigo)
            grupos[codigo].append(m)

        # Generar TXTs en memoria y devolver como descarga
        cabecera = f"{ref},{edicion},, ,{ref},{edicion}, ,,"
        ficheros = {}  # nombre -> contenido

        for codigo in orden_codigos:
            manguitos = grupos[codigo]
            lineas = ['', cabecera]
            for m in manguitos:
                de_elem  = m.get('de_elemento', '')
                de_pto   = m.get('de_punto', '')
                de_marca = m.get('de_marca', '')
                para_elem = m.get('para_elemento', '')
                para_pto  = m.get('para_punto', '')

                col_izq  = f"{de_elem} {de_pto}".rstrip() + (' ' if not de_pto else '')
                col_der  = f"{para_elem} {para_pto}".rstrip() + (' ' if not para_pto else '')
                linea = f"{de_marca},{col_izq},,{col_der},{col_izq},{de_marca},{col_der},,"
                lineas.append(linea)

            nombre = f"{ref} {edicion}  {codigo} 1.txt"
            ficheros[nombre] = '\n'.join(lineas)

        return _respuesta_descarga_manguitos(ficheros, ref, edicion)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/api/manguitos/generar-txt-desde-excel', methods=['POST'])
def api_manguitos_generar_txt_desde_excel():
    """
    Genera TXT de manguitos a partir de un Excel subido en el momento.
    Orden: exactamente el del Excel (sin reordenar por número de etiqueta).
    """
    import tempfile, shutil
    excel_file = request.files.get('excel')
    ref        = (request.form.get('ref', 'PC_CAB_BADEN') or 'PC_CAB_BADEN').strip()
    edicion    = (request.form.get('edicion', 'ed_04') or 'ed_04').strip()

    if not excel_file or not excel_file.filename:
        return jsonify({'success': False, 'error': 'No se recibió ningún archivo Excel'})

    nombre_original = excel_file.filename
    if not nombre_original.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'El archivo debe ser .xlsx o .xls'})

    tmpdir = tempfile.mkdtemp(prefix='mg_excel_')
    try:
        ruta_tmp = os.path.join(tmpdir, nombre_original)
        excel_file.save(ruta_tmp)

        em       = ExcelManager(tmpdir)
        elementos = em.get_manguitos(nombre_original)

        # Aplanar en orden de Excel (sin ordenar por etiqueta)
        lista_plana = []
        for elem in elementos:
            for m in elem['manguitos']:
                lista_plana.append(m)

        # Agrupar por código de manguito preservando orden de aparición
        grupos       = {}
        orden_codigos = []
        for m in lista_plana:
            codigo = m['de_manguito']
            if codigo not in grupos:
                grupos[codigo] = []
                orden_codigos.append(codigo)
            grupos[codigo].append(m)

        # Generar TXTs en memoria y devolver como descarga
        cabecera = f"{ref},{edicion},, ,{ref},{edicion}, ,,"
        ficheros = {}  # nombre -> contenido

        for codigo in orden_codigos:
            manguitos = grupos[codigo]
            lineas = ['', cabecera]
            for m in manguitos:
                de_elem   = m.get('de_elemento', '')
                de_pto    = m.get('de_punto', '')
                de_marca  = m.get('de_marca', '')
                para_elem = m.get('para_elemento', '')
                para_pto  = m.get('para_punto', '')

                col_izq = f"{de_elem} {de_pto}".rstrip() + (' ' if not de_pto else '')
                col_der = f"{para_elem} {para_pto}".rstrip() + (' ' if not para_pto else '')
                linea = f"{de_marca},{col_izq},,{col_der},{col_izq},{de_marca},{col_der},,"
                lineas.append(linea)

            nombre = f"{ref} {edicion}  {codigo} 1.txt"
            ficheros[nombre] = '\n'.join(lineas)

        return _respuesta_descarga_manguitos(ficheros, ref, edicion)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ==================== GESTIÓN DE PROYECTOS ====================

@bp.route('/proyectos')
def gestion_proyectos():
    """Vista de gestión de proyectos"""
    return render_template('gestion-proyectos.html')


@bp.route('/api/proyectos', methods=['GET'])
def api_obtener_proyectos():
    """Obtener listado de proyectos"""
    try:
        proyecto_repo = ProyectoRepository(db)
        estado = request.args.get('estado')  # activo, completado, pausado, cancelado
        
        proyectos = proyecto_repo.obtener_todos_proyectos(estado)
        
        return jsonify({
            'success': True,
            'proyectos': proyectos
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/proyectos', methods=['POST'])
def api_crear_proyecto():
    """Crear nuevo proyecto"""
    try:
        data = request.get_json()
        
        proyecto_repo = ProyectoRepository(db)
        proyecto_id = proyecto_repo.crear_proyecto(
            nombre=data['nombre'],
            archivo=data['archivo'],
            carro_asignado=data.get('carro_asignado')
        )
        
        proyecto = proyecto_repo.obtener_proyecto(proyecto_id)
        
        return jsonify({
            'success': True,
            'proyecto': proyecto
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/proyectos/<int:proyecto_id>/carro', methods=['PUT'])
def api_asignar_carro(proyecto_id):
    """Asignar proyecto a un carro"""
    try:
        data = request.get_json()
        carro_numero = data.get('carro_numero')
        
        proyecto_repo = ProyectoRepository(db)
        
        if carro_numero:
            success = proyecto_repo.asignar_carro(proyecto_id, carro_numero)
        else:
            success = proyecto_repo.liberar_carro(proyecto_id)
        
        if success:
            proyecto = proyecto_repo.obtener_proyecto(proyecto_id)
            return jsonify({
                'success': True,
                'proyecto': proyecto
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo asignar el carro'
            }), 400
            
    except Exception as e:
        return error_interno(e)


@bp.route('/api/proyectos/<int:proyecto_id>/estado', methods=['PUT'])
def api_cambiar_estado_proyecto(proyecto_id):
    """Cambiar estado de un proyecto"""
    try:
        data = request.get_json()
        estado = data.get('estado')
        
        proyecto_repo = ProyectoRepository(db)
        success = proyecto_repo.cambiar_estado(proyecto_id, estado)
        
        if success:
            proyecto = proyecto_repo.obtener_proyecto(proyecto_id)
            return jsonify({
                'success': True,
                'proyecto': proyecto
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo cambiar el estado'
            }), 400
            
    except Exception as e:
        return error_interno(e)


# ==================== GESTIÓN DE ÓRDENES ====================

@bp.route('/registro-ordenes')
def registro_ordenes():
    """Vista de registro de órdenes"""
    return render_template('registro-ordenes.html')


@bp.route('/ordenes')
def lista_ordenes():
    """Tabla completa de órdenes con sidebar dark"""
    return render_template('ordenes.html')


@bp.route('/api/ordenes', methods=['GET'])
def api_obtener_ordenes():
    """Obtener listado de órdenes"""
    try:
        orden_repo = OrdenRepository(db)
        estado = request.args.get('estado')
        
        if estado:
            ordenes = orden_repo.obtener_ordenes_por_estado(estado)
        else:
            ordenes = orden_repo.obtener_ordenes_pendientes()
        
        return jsonify({
            'success': True,
            'ordenes': ordenes
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ordenes', methods=['POST'])
def api_crear_orden():
    """Crear nueva orden de producción"""
    try:
        data = request.get_json()
        
        # Buscar el archivo Excel asociado al código de corte
        codigo_repo = CodigoCorteRepository(db)
        codigo_info = codigo_repo.obtener_codigo(data['codigo_corte'])
        
        archivo_excel = None
        proyecto_nombre = None
        
        if codigo_info:
            archivo_excel = codigo_info.get('archivo_excel')
            proyecto_nombre = codigo_info.get('proyecto_nombre')
        
        # Si no se especificó proyecto, usar el del código de corte
        proyecto = data.get('proyecto', '') or proyecto_nombre or ''
        
        orden_repo = OrdenRepository(db)
        orden_id = orden_repo.crear_orden(
            codigo_corte=data['codigo_corte'],
            numero=data['numero'],
            descripcion=data.get('descripcion', ''),
            cantidad=data.get('cantidad', 1),
            fecha_entrega=data.get('fecha_entrega'),
            prioridad=data.get('prioridad', 'normal'),
            archivo_excel=archivo_excel,
            proyecto=proyecto
        )
        
        orden = orden_repo.obtener_orden(orden_id)
        
        return jsonify({
            'success': True,
            'orden': orden,
            'archivo_encontrado': archivo_excel is not None
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ordenes/eliminar/<orden_id>', methods=['DELETE'])
def api_eliminar_orden(orden_id):
    """Eliminar una orden de producción"""
    try:
        orden_repo = OrdenRepository(db)
        
        # Verificar que la orden existe
        orden = orden_repo.obtener_orden(orden_id)
        if not orden:
            return jsonify({
                'success': False,
                'message': 'Orden no encontrada'
            }), 404
        
        # Eliminar la orden
        if orden_repo.eliminar_orden(orden_id):
            return jsonify({
                'success': True,
                'message': 'Orden eliminada correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo eliminar la orden'
            }), 500
    except Exception as e:
        return error_interno(e)


@bp.route('/api/ordenes/actualizar/<orden_id>', methods=['PUT'])
def api_actualizar_orden(orden_id):
    """Actualizar una orden de producción"""
    try:
        data = request.get_json()
        orden_repo = OrdenRepository(db)
        
        # Verificar que la orden existe
        orden_actual = orden_repo.obtener_orden(orden_id)
        if not orden_actual:
            return jsonify({
                'success': False,
                'message': 'Orden no encontrada'
            }), 404
        
        # Actualizar la orden
        if orden_repo.actualizar_orden(
            orden_id=orden_id,
            codigo_corte=data.get('codigo_corte'),
            numero=data.get('numero'),
            descripcion=data.get('descripcion'),
            cantidad=data.get('cantidad'),
            fecha_entrega=data.get('fecha_entrega'),
            prioridad=data.get('prioridad'),
            proyecto=data.get('proyecto')
        ):
            orden_actualizada = orden_repo.obtener_orden(orden_id)
            return jsonify({
                'success': True,
                'orden': orden_actualizada,
                'message': 'Orden actualizada correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo actualizar la orden'
            }), 500
    except Exception as e:
        return error_interno(e)


# Alias para compatibilidad con el frontend
@bp.route('/api/ordenes/crear', methods=['POST'])
def api_crear_orden_alias():
    """Alias para crear orden (compatibilidad)"""
    return api_crear_orden()


@bp.route('/api/ordenes/listar', methods=['GET'])
def api_listar_ordenes_alias():
    """Alias para listar órdenes (compatibilidad)"""
    try:
        orden_repo = OrdenRepository(db)
        ordenes = orden_repo.obtener_todas_ordenes()
        
        return jsonify({
            'success': True,
            'ordenes': ordenes
        })
    except Exception as e:
        return error_interno(e)


# ==================== GESTIÓN DE BONOS ====================

@bp.route('/api/bonos', methods=['GET'])
def api_obtener_bonos():
    """Obtener listado de bonos"""
    try:
        bono_repo = BonoRepository(db)
        estado = request.args.get('estado')
        
        bonos = bono_repo.obtener_todos_bonos(estado)
        
        return jsonify({
            'success': True,
            'bonos': bonos
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<nombre>', methods=['GET'])
def api_obtener_bono_por_nombre(nombre):
    """Obtener bono por nombre con sus órdenes"""
    try:
        bono_repo = BonoRepository(db)
        orden_repo = OrdenRepository(db)
        
        # Buscar bono por nombre
        bonos = bono_repo.obtener_todos_bonos()
        bono = next((b for b in bonos if b['nombre'] == nombre), None)
        
        if not bono:
            return jsonify({
                'success': False,
                'message': f'No se encontró el bono {nombre}'
            }), 404
        
        # Obtener órdenes del bono
        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])
        
        # Construir respuesta con información completa
        # Si carro_numero es NULL (bonos migrados), usar índice+1 como fallback
        carros_list = [
            {
                'carro': o.get('carro_numero') if o.get('carro_numero') is not None else (idx + 1),
                'archivo_excel': o.get('archivo_excel'),
                'proyecto_nombre': o.get('numero', '')
            }
            for idx, o in enumerate(ordenes)
            if o.get('archivo_excel')
        ]
        bono_completo = {
            'id': bono['id'],
            'nombre': bono['nombre'],
            'descripcion': bono.get('descripcion'),
            'estado': bono['estado'],
            'fecha_creacion': bono['fecha_creacion'],
            'total_ordenes': len(ordenes),
            'ordenes': ordenes,
            'carros': carros_list,
            'num_cortes': len(carros_list)
        }
        
        return jsonify({
            'success': True,
            'bono': bono_completo
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/<nombre>', methods=['DELETE'])
def api_eliminar_bono(nombre):
    """Eliminar bono por nombre"""
    try:
        bono_repo = BonoRepository(db)
        bono = bono_repo.obtener_bono_por_nombre(nombre)
        if not bono:
            return jsonify({'success': False, 'error': 'Bono no encontrado'}), 404

        ok = bono_repo.eliminar_bono(bono['id'])
        if not ok:
            return jsonify({'success': False, 'error': 'No se pudo eliminar el bono'}), 500

        # Borrar fichero de progreso si existe
        import os
        progreso_path = os.path.join(current_app.config['DATA_DIR'], f'progreso_bono_{nombre}.json')
        if os.path.exists(progreso_path):
            os.remove(progreso_path)

        return jsonify({'success': True, 'message': f'Bono {nombre} eliminado correctamente'})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos', methods=['POST'])
def api_crear_bono():
    """Crear nuevo bono"""
    try:
        data = request.get_json()
        
        bono_repo = BonoRepository(db)
        with db.engine.begin() as conn:
            bono_id = bono_repo.crear_bono(
                nombre=data['nombre'],
                ordenes_ids=data['ordenes_ids'],
                descripcion=data.get('descripcion'),
                conn=conn
            )
        
        bono = bono_repo.obtener_bono_con_ordenes(bono_id)
        
        return jsonify({
            'success': True,
            'bono': bono
        })
    except IntegrityError as e:
        if _es_error_nombre_bono_duplicado(e):
            return jsonify({
                'success': False,
                'message': 'Ya existe un bono con ese nombre. Refresca el nombre sugerido e inténtalo de nuevo.'
            }), 409
        traceback.print_exc()
        return error_interno(e)
    except Exception as e:
        traceback.print_exc()
        return error_interno(e)


@bp.route('/api/bonos/<bono_id>/carro', methods=['PUT'])
def api_asignar_bono_carro(bono_id):
    """Asignar bono a un carro"""
    try:
        data = request.get_json()
        carro_numero = data.get('carro_numero')
        
        bono_repo = BonoRepository(db)
        success = bono_repo.asignar_a_carro(bono_id, carro_numero)
        
        if success:
            bono = bono_repo.obtener_bono_con_ordenes(bono_id)
            return jsonify({
                'success': True,
                'bono': bono
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo asignar el carro'
            }), 400
            
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/nombre-sugerido', methods=['GET'])
def api_obtener_nombre_sugerido_bono():
    """Obtener nombre sugerido para el siguiente bono en formato DDMMYYYY_N"""
    try:
        from datetime import datetime
        
        bono_repo = BonoRepository(db)
        
        # Formato: DDMMYYYY
        fecha_hoy = datetime.now().strftime('%d%m%Y')
        
        # Obtener todos los bonos
        bonos = bono_repo.obtener_todos_bonos()
        
        # Filtrar bonos del día de hoy y encontrar el último número
        bonos_hoy = [b for b in bonos if b['nombre'].startswith(fecha_hoy)]
        
        if bonos_hoy:
            # Extraer números y encontrar el máximo
            numeros = []
            for bono in bonos_hoy:
                try:
                    # Formato esperado: DDMMYYYY_N
                    partes = bono['nombre'].split('_')
                    if len(partes) >= 2:
                        numeros.append(int(partes[-1]))
                except (ValueError, IndexError):
                    continue
            
            siguiente_numero = max(numeros) + 1 if numeros else 1
        else:
            siguiente_numero = 1
        
        nombre_sugerido = f"{fecha_hoy}_{siguiente_numero}"
        
        return jsonify({
            'success': True,
            'nombre': nombre_sugerido
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/generar', methods=['POST'])
def api_generar_bono_desde_carros():
    """Generar bono a partir de los carros ocupados"""
    try:
        data = request.get_json()
        nombre_bono = data.get('nombre')
        
        if not nombre_bono:
            return jsonify({
                'success': False,
                'message': 'El nombre del bono es requerido'
            }), 400
        
        proyecto_repo = ProyectoRepository(db)
        orden_repo = OrdenRepository(db)
        bono_repo = BonoRepository(db)
        
        # Obtener todos los proyectos con carro asignado
        proyectos = proyecto_repo.obtener_todos_proyectos()
        proyectos_en_carros = [p for p in proyectos if p['carro_asignado'] is not None]
        
        if not proyectos_en_carros:
            return jsonify({
                'success': False,
                'message': 'No hay carros con proyectos asignados'
            }), 400
        
        if len(proyectos_en_carros) > 6:
            return jsonify({
                'success': False,
                'message': 'No se pueden incluir más de 6 carros en un bono'
            }), 400
        
        # Extraer números de orden de los proyectos
        ordenes_ids = []
        carros_info = []
        
        for proyecto in proyectos_en_carros:
            # Extraer número de orden del nombre del proyecto (formato: "60245848 - H0068722")
            try:
                numero_orden = proyecto['nombre'].split(' - ')[0].strip()
            except Exception:
                numero_orden = proyecto['nombre']
            
            ordenes_ids.append(numero_orden)
            
            carros_info.append({
                'carro': proyecto['carro_asignado'],
                'proyecto_nombre': proyecto['nombre'],
                'archivo_excel': proyecto['archivo']
            })
        
        # CREAR EL BONO + ACTUALIZAR ÓRDENES + LIBERAR CARROS DE FORMA ATÓMICA
        # Todo dentro de un único engine.begin(): se commitea junto o se
        # revierte junto si cualquier paso falla.
        descripcion = f"Bono con {len(proyectos_en_carros)} carros"
        with db.engine.begin() as conn:
            bono_id = bono_repo.crear_bono(
                nombre=nombre_bono,
                ordenes_ids=ordenes_ids,
                descripcion=descripcion,
                conn=conn
            )

            # Cambiar estado de las órdenes a 'en_bono' y guardar carro_numero
            for idx, (numero_orden, carro_info) in enumerate(zip(ordenes_ids, carros_info)):
                orden_repo.cambiar_estado(numero_orden, 'en_bono', conn=conn)
                # Guardar el carro_numero en la orden para que el dashboard ponderado funcione
                conn.execute(
                    text("UPDATE ordenes_produccion SET carro_numero=:carro WHERE numero=:numero AND bono_id=:bono_id"),
                    {'carro': carro_info['carro'], 'numero': numero_orden, 'bono_id': bono_id}
                )

            # Liberar los carros (establecer carro_asignado a NULL)
            for proyecto in proyectos_en_carros:
                proyecto_repo.liberar_carro(proyecto['id'], conn=conn)
        
        # Construir respuesta con información del bono
        bono_generado = {
            'nombre': nombre_bono,
            'num_cortes': len(carros_info),
            'carros': carros_info,
            'id': bono_id
        }
        
        return jsonify({
            'success': True,
            'bono': bono_generado
        })
        
    except IntegrityError as e:
        if _es_error_nombre_bono_duplicado(e):
            return jsonify({
                'success': False,
                'message': 'Ya existe un bono con ese nombre. Refresca el nombre sugerido e inténtalo de nuevo.'
            }), 409
        traceback.print_exc()
        return error_interno(e, 'Error al generar bono')
    except Exception as e:
        traceback.print_exc()
        return error_interno(e, 'Error al generar bono')


# ==================== CARROS ====================

@bp.route('/api/carros', methods=['GET'])
def api_obtener_carros():
    """Obtener listado de carros con información de proyectos"""
    try:
        carro_repo = CarroRepository(db)
        proyecto_repo = ProyectoRepository(db)
        
        carros = carro_repo.obtener_todos_carros()
        
        # Para cada carro, obtener sus proyectos activos
        for carro in carros:
            proyectos = proyecto_repo.obtener_proyectos_por_carro(carro['numero'])
            
            if proyectos and len(proyectos) > 0:
                # Carro ocupado
                carro['ocupado'] = True
                carro['proyecto_id'] = proyectos[0]['id']
                carro['proyecto_nombre'] = proyectos[0]['nombre']
                carro['proyecto_archivo'] = proyectos[0]['archivo']
            else:
                # Carro libre
                carro['ocupado'] = False
                carro['proyecto_id'] = None
                carro['proyecto_nombre'] = None
                carro['proyecto_archivo'] = None
        
        return jsonify({
            'success': True,
            'carros': carros
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/<int:carro_numero>', methods=['GET'])
def api_obtener_carro(carro_numero):
    """Obtener información de un carro específico"""
    try:
        carro_repo = CarroRepository(db)
        carro = carro_repo.obtener_carro(carro_numero)
        
        if carro:
            # Obtener proyectos y bonos asignados
            proyectos = carro_repo.obtener_proyectos_activos_en_carro(carro_numero)
            bonos = carro_repo.obtener_bonos_en_carro(carro_numero)
            
            carro['proyectos'] = proyectos
            carro['bonos'] = bonos
            
            return jsonify({
                'success': True,
                'carro': carro
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Carro no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/asignar-orden', methods=['POST'])
def api_asignar_orden_a_carro():
    """Asignar orden a un carro creando un proyecto"""
    try:
        data = request.get_json()
        numero_carro = data.get('numero_carro')
        proyecto_nombre = data.get('proyecto_nombre')
        archivo = data.get('archivo')
        orden_id = data.get('orden_id')  # ID de la orden
        
        if not numero_carro or not proyecto_nombre or not archivo:
            return jsonify({
                'success': False,
                'message': 'Faltan parámetros requeridos'
            }), 400
        
        # Crear proyecto
        proyecto_repo = ProyectoRepository(db)
        proyecto_id = proyecto_repo.crear_proyecto(
            nombre=proyecto_nombre,
            archivo=archivo,
            carro_asignado=numero_carro
        )
        
        # Si se proporcionó orden_id, actualizar estado de la orden
        if orden_id:
            orden_repo = OrdenRepository(db)
            orden_repo.cambiar_estado(orden_id, 'en_proceso')
        
        return jsonify({
            'success': True,
            'proyecto_id': proyecto_id,
            'message': f'Proyecto asignado al carro {numero_carro}'
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/<int:numero_carro>/liberar', methods=['POST'])
def api_liberar_carro(numero_carro):
    """Liberar un carro eliminando sus proyectos activos y devolviendo órdenes a pendiente"""
    try:
        proyecto_repo = ProyectoRepository(db)
        orden_repo = OrdenRepository(db)
        
        # Obtener proyectos activos en el carro
        carro_repo = CarroRepository(db)
        proyectos = carro_repo.obtener_proyectos_activos_en_carro(numero_carro)
        
        ordenes_liberadas = []
        
        # Liberar cada proyecto y devolver órdenes a pendiente
        for proyecto in proyectos:
            # Intentar extraer el número de orden del nombre del proyecto
            # Formato esperado: "60245848 - H0068722"
            nombre_proyecto = proyecto.get('nombre', '')
            
            if ' - ' in nombre_proyecto:
                numero_orden = nombre_proyecto.split(' - ')[0].strip()
                
                # Cambiar estado de la orden a pendiente
                query = """
                    UPDATE ordenes_produccion 
                    SET estado = 'pendiente'
                    WHERE numero = :numero AND estado = 'en_proceso'
                """
                rows = orden_repo.execute_update(query, {'numero': numero_orden})
                
                if rows > 0:
                    ordenes_liberadas.append(numero_orden)
            
            # Liberar el proyecto del carro
            proyecto_repo.liberar_carro(proyecto['id'])
        
        return jsonify({
            'success': True,
            'message': f'Carro {numero_carro} liberado',
            'ordenes_liberadas': ordenes_liberadas
        })
        
    except Exception as e:
        return error_interno(e)


@bp.route('/api/carros/asignar', methods=['POST'])
def api_asignar_proyecto_carro():
    """Asignar proyecto existente a un carro"""
    try:
        data = request.get_json()
        proyecto_id = data.get('proyecto_id')
        carro = data.get('carro')
        
        if not proyecto_id or not carro:
            return jsonify({
                'success': False,
                'message': 'Faltan parámetros'
            }), 400
        
        proyecto_repo = ProyectoRepository(db)
        success = proyecto_repo.asignar_carro(proyecto_id, carro)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Proyecto asignado al carro'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo asignar el proyecto'
            }), 500
            
    except Exception as e:
        return error_interno(e)


# ==================== CÓDIGOS DE CORTES ====================

@bp.route('/api/codigos', methods=['GET'])
def api_obtener_codigos():
    """Obtener códigos de cortes"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        return jsonify({
            'success': True,
            'codigos': codigos
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/codigos/<codigo>', methods=['GET'])
def api_obtener_codigo(codigo):
    """Obtener información de un código específico"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigo_info = codigo_repo.obtener_codigo(codigo)
        
        if codigo_info:
            return jsonify({
                'success': True,
                'codigo': codigo_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Código no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e)


# ==================== GESTIÓN DE ARCHIVOS EXCEL ====================

@bp.route('/api/upload', methods=['POST'])
def upload_file():
    """Subir archivo Excel"""
    try:
        # Verificar que se envió un archivo
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': 'No se encontró archivo'
            }), 400
        
        file = request.files['file']
        
        # Verificar que se seleccionó un archivo
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'No se seleccionó archivo'
            }), 400
        
        # Verificar extensión permitida
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            # Crear carpeta de uploads si no existe
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            
            # Guardar archivo
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)

            # Leer nombres de hojas y buscar patrón CODIGO_EDICION (ej: H0457486_ED04)
            hoja_codigo = None
            codigo_extraido = None
            edicion_extraida = None
            try:
                xl = pd.ExcelFile(filepath)
                import re as _re
                for sheet in xl.sheet_names:
                    m = _re.match(r'^([A-Za-z0-9]+)_([A-Za-z0-9]+)$', sheet.strip())
                    if m:
                        hoja_codigo = sheet.strip()
                        codigo_extraido = m.group(1).upper()
                        edicion_extraida = m.group(2).upper()
                        break
            except Exception:
                pass

            # Regenerar etiquetas si este archivo ya tenía registros en la BD
            etiquetas_regeneradas = False
            etiquetas_total = 0
            try:
                with db.engine.connect() as conn:
                    count = conn.execute(
                        text("SELECT COUNT(*) FROM etiquetas_elementos WHERE archivo_excel = :a"),
                        {'a': filename}
                    ).scalar()
                if count and count > 0:
                    total = _regenerar_etiquetas_archivo(filename, filepath)
                    etiquetas_regeneradas = True
                    etiquetas_total = total
            except Exception as _e:
                print(f"⚠️ No se pudieron regenerar etiquetas tras subida: {_e}")

            return jsonify({
                'success': True,
                'message': 'Archivo subido correctamente',
                'filename': filename,
                'hoja_codigo': hoja_codigo,
                'codigo': codigo_extraido,
                'edicion': edicion_extraida,
                'etiquetas_regeneradas': etiquetas_regeneradas,
                'etiquetas_total': etiquetas_total
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Tipo de archivo no permitido. Solo .xlsx y .xls'
            }), 400
            
    except Exception as e:
        return error_interno(e, 'Error al subir archivo')


@bp.route('/api/list_files', methods=['GET'])
def list_files():
    """Listar archivos Excel en la carpeta de uploads"""
    try:
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        if not os.path.exists(upload_folder):
            return jsonify({'success': True, 'files': []})
        
        files = []
        for filename in os.listdir(upload_folder):
            if allowed_file(filename):
                filepath = os.path.join(upload_folder, filename)
                file_size = os.path.getsize(filepath)
                
                # Formatear tamaño
                if file_size < 1024:
                    size_str = f"{file_size} B"
                elif file_size < 1024 * 1024:
                    size_str = f"{file_size / 1024:.1f} KB"
                else:
                    size_str = f"{file_size / (1024 * 1024):.1f} MB"
                
                files.append({
                    'nombre': filename,
                    'tamano': size_str
                })
        
        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        return error_interno(e, 'Error al listar archivos')


@bp.route('/api/add_corte', methods=['POST'])
def add_corte():
    """Agregar nuevo corte de cable (asociar código de barras con archivo)"""
    try:
        data = request.get_json()
        
        codigo_barras = data.get('codigo_barras', '').strip().upper()
        archivo = data.get('archivo', '').strip()
        descripcion = data.get('descripcion', '').strip()
        proyecto = data.get('proyecto', '').strip()
        forzar = data.get('forzar', False)

        if not codigo_barras or not archivo:
            return jsonify({
                'success': False,
                'message': 'Código de barras y archivo son obligatorios'
            }), 400

        # Verificar que el archivo existe
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], archivo)
        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'message': f'El archivo "{archivo}" no existe'
            }), 400

        # Agregar código a la base de datos
        codigo_repo = CodigoCorteRepository(db)

        # Verificar si ya existe; si no se fuerza, avisar al frontend
        existe = codigo_repo.obtener_codigo(codigo_barras)
        if existe and not forzar:
            return jsonify({
                'success': False,
                'ya_existe': True,
                'message': f'El código {codigo_barras} ya está asociado al archivo "{existe["archivo_excel"]}". ¿Deseas sobreescribirlo?'
            }), 409

        # Agregar/sobreescribir código
        success = codigo_repo.agregar_codigo(
            codigo=codigo_barras,
            archivo_excel=archivo,
            proyecto_nombre=proyecto or descripcion or None
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Corte agregado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al agregar el corte'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al agregar corte')


@bp.route('/api/list_cortes', methods=['GET'])
def list_cortes():
    """Listar todos los cortes registrados"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        # Formatear para compatibilidad con el formato antiguo
        cortes = []
        for codigo in codigos:
            cortes.append({
                'codigo': codigo['codigo'],
                'codigo_barras': codigo['codigo'],
                'archivo': codigo['archivo_excel'],
                'descripcion': codigo.get('proyecto_nombre', ''),
                'proyecto': codigo.get('proyecto_nombre', '')
            })
        
        return jsonify({
            'success': True,
            'cortes': cortes
        })
    except Exception as e:
        return error_interno(e, 'Error al listar cortes')


# Alias para compatibilidad con el frontend
@bp.route('/api/codigos_cortes/listar', methods=['GET'])
def api_listar_codigos_alias():
    """Alias para listar códigos de corte (compatibilidad)"""
    try:
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        # Formatear códigos para el select
        codigos_formateados = []
        for codigo in codigos:
            codigos_formateados.append({
                'codigo': codigo['codigo'],
                'descripcion': codigo.get('proyecto_nombre', ''),
                'proyecto': codigo.get('proyecto_nombre', ''),
                'archivo': codigo['archivo_excel']
            })
        
        return jsonify({
            'success': True,
            'codigos': codigos_formateados
        })
    except Exception as e:
        return error_interno(e, 'Error al listar códigos')


@bp.route('/api/delete_corte', methods=['POST'])
def delete_corte():
    """Eliminar corte de cable"""
    try:
        data = request.get_json()
        codigo_barras = data.get('codigo_barras', '').strip().upper()
        
        if not codigo_barras:
            return jsonify({
                'success': False,
                'message': 'Código de barras vacío'
            }), 400
        
        codigo_repo = CodigoCorteRepository(db)
        
        if codigo_repo.desactivar_codigo(codigo_barras):
            return jsonify({
                'success': True,
                'message': 'Corte eliminado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Código de barras no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al eliminar corte')


@bp.route('/api/delete_file', methods=['POST'])
def delete_file():
    """Eliminar archivo Excel"""
    try:
        data = request.get_json()
        filename = data.get('filename', '').strip()
        
        if not filename:
            return jsonify({
                'success': False,
                'message': 'Nombre de archivo vacío'
            }), 400
        
        # Eliminar archivo físico
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'message': 'Archivo no encontrado'
            }), 404
        
        os.remove(filepath)
        
        # Desactivar todos los códigos asociados a este archivo
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.buscar_por_archivo(filename)
        for codigo in codigos:
            codigo_repo.desactivar_codigo(codigo['codigo'])
        
        return jsonify({
            'success': True,
            'message': 'Archivo eliminado correctamente'
        })
        
    except Exception as e:
        return error_interno(e, 'Error al eliminar archivo')


# ==================== PUESTOS Y MÁQUINAS ====================

@bp.route('/api/puestos', methods=['GET'])
def api_obtener_puestos():
    """Obtener lista de puestos con sus máquinas"""
    try:
        puesto_repo = PuestoRepository(db)
        maquina_repo = MaquinaRepository(db)
        
        puestos = puesto_repo.obtener_todos_puestos()
        
        # Agregar máquinas a cada puesto
        for puesto in puestos:
            maquinas = maquina_repo.obtener_maquinas_por_puesto(puesto['id'])
            # Agregar terminales a cada máquina
            for maquina in maquinas:
                maquina['terminales_asignados'] = maquina_repo.obtener_terminales_asignados(maquina['id'])
            puesto['maquinas'] = maquinas
        
        return jsonify({
            'success': True,
            'puestos': puestos
        })
    except Exception as e:
        return error_interno(e, 'Error al obtener puestos')


@bp.route('/api/puestos', methods=['POST'])
def api_crear_puesto():
    """Crear nuevo puesto"""
    try:
        data = request.get_json()
        
        nombre = data.get('nombre', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return jsonify({
                'success': False,
                'message': 'El nombre del puesto es obligatorio'
            }), 400
        
        # Generar ID único
        puesto_repo = PuestoRepository(db)
        puestos_existentes = puesto_repo.obtener_todos_puestos(solo_activos=False)
        
        import random
        new_id = f"puesto_{len(puestos_existentes) + 1:03d}"
        while any(p['id'] == new_id for p in puestos_existentes):
            new_id = f"puesto_{len(puestos_existentes) + 1:03d}_{random.randint(100, 999)}"
        
        # Crear puesto
        if puesto_repo.crear_puesto(new_id, nombre, descripcion):
            nuevo_puesto = puesto_repo.obtener_puesto(new_id)
            return jsonify({
                'success': True,
                'puesto': nuevo_puesto
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al crear el puesto'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al crear puesto')


@bp.route('/api/puestos/<puesto_id>', methods=['PUT'])
def api_actualizar_puesto(puesto_id):
    """Actualizar puesto existente"""
    try:
        data = request.get_json()
        
        puesto_repo = PuestoRepository(db)
        
        # Verificar que existe
        puesto = puesto_repo.obtener_puesto(puesto_id)
        if not puesto:
            return jsonify({
                'success': False,
                'message': 'Puesto no encontrado'
            }), 404
        
        # Actualizar
        nombre = data.get('nombre')
        descripcion = data.get('descripcion')
        
        if puesto_repo.actualizar_puesto(puesto_id, nombre, descripcion):
            puesto_actualizado = puesto_repo.obtener_puesto(puesto_id)
            return jsonify({
                'success': True,
                'puesto': puesto_actualizado
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se realizaron cambios'
            }), 400
            
    except Exception as e:
        return error_interno(e, 'Error al actualizar puesto')


@bp.route('/api/puestos/<puesto_id>', methods=['DELETE'])
def api_eliminar_puesto(puesto_id):
    """Eliminar puesto"""
    try:
        puesto_repo = PuestoRepository(db)
        
        if puesto_repo.desactivar_puesto(puesto_id):
            return jsonify({
                'success': True,
                'message': 'Puesto eliminado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Puesto no encontrado'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al eliminar puesto')


@bp.route('/api/maquinas', methods=['GET'])
def api_obtener_maquinas():
    """Obtener lista de máquinas con información del puesto"""
    try:
        maquina_repo = MaquinaRepository(db)
        maquinas = maquina_repo.obtener_todas_maquinas()
        
        # Agregar terminales asignados a cada máquina
        for maquina in maquinas:
            maquina['terminales_asignados'] = maquina_repo.obtener_terminales_asignados(maquina['id'])
        
        return jsonify({
            'success': True,
            'maquinas': maquinas
        })
    except Exception as e:
        return error_interno(e, 'Error al obtener máquinas')


@bp.route('/api/maquinas', methods=['POST'])
def api_crear_maquina():
    """Crear nueva máquina"""
    try:
        data = request.get_json()
        
        puesto_id = data.get('puesto_id', '').strip()
        nombre = data.get('nombre', '').strip()
        modelo = data.get('modelo', '').strip()
        descripcion = data.get('descripcion', '').strip()
        
        if not puesto_id or not nombre:
            return jsonify({
                'success': False,
                'message': 'Puesto y nombre son obligatorios'
            }), 400
        
        # Verificar que el puesto existe
        puesto_repo = PuestoRepository(db)
        puesto = puesto_repo.obtener_puesto(puesto_id)
        if not puesto:
            return jsonify({
                'success': False,
                'message': 'Puesto no encontrado'
            }), 404
        
        # Generar ID único
        maquina_repo = MaquinaRepository(db)
        maquinas_existentes = maquina_repo.obtener_todas_maquinas(solo_activas=False)
        
        import random
        new_id = f"maq_{len(maquinas_existentes) + 1:03d}"
        while any(m['id'] == new_id for m in maquinas_existentes):
            new_id = f"maq_{len(maquinas_existentes) + 1:03d}_{random.randint(100, 999)}"
        
        # Crear máquina
        if maquina_repo.crear_maquina(new_id, puesto_id, nombre, modelo, descripcion):
            nueva_maquina = maquina_repo.obtener_maquina(new_id)
            nueva_maquina['terminales_asignados'] = []
            return jsonify({
                'success': True,
                'maquina': nueva_maquina
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al crear la máquina'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al crear máquina')


@bp.route('/api/maquinas/<maquina_id>', methods=['PUT'])
def api_actualizar_maquina(maquina_id):
    """Actualizar máquina existente"""
    try:
        data = request.get_json()
        
        maquina_repo = MaquinaRepository(db)
        
        # Verificar que existe
        maquina = maquina_repo.obtener_maquina(maquina_id)
        if not maquina:
            return jsonify({
                'success': False,
                'message': 'Máquina no encontrada'
            }), 404
        
        # Actualizar
        nombre = data.get('nombre')
        modelo = data.get('modelo')
        descripcion = data.get('descripcion')
        
        if maquina_repo.actualizar_maquina(maquina_id, nombre, modelo, descripcion):
            maquina_actualizada = maquina_repo.obtener_maquina(maquina_id)
            maquina_actualizada['terminales_asignados'] = maquina_repo.obtener_terminales_asignados(maquina_id)
            return jsonify({
                'success': True,
                'maquina': maquina_actualizada
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se realizaron cambios'
            }), 400
            
    except Exception as e:
        return error_interno(e, 'Error al actualizar máquina')


@bp.route('/api/maquinas/<maquina_id>', methods=['DELETE'])
def api_eliminar_maquina(maquina_id):
    """Eliminar máquina"""
    try:
        maquina_repo = MaquinaRepository(db)
        
        if maquina_repo.desactivar_maquina(maquina_id):
            return jsonify({
                'success': True,
                'message': 'Máquina eliminada correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Máquina no encontrada'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al eliminar máquina')


@bp.route('/api/terminales-disponibles', methods=['GET'])
def api_terminales_disponibles():
    """Obtener todos los terminales disponibles con su estado de asignación"""
    try:
        # Obtener códigos de archivos activos
        codigo_repo = CodigoCorteRepository(db)
        codigos = codigo_repo.obtener_todos_codigos()
        
        # Leer todos los archivos Excel y extraer terminales
        upload_folder = current_app.config['UPLOAD_FOLDER']
        terminales_sistema = set()
        archivos_procesados = 0
        errores_lectura = []
        
        for codigo in codigos:
            archivo = codigo['archivo_excel']
            filepath = os.path.join(upload_folder, archivo)
            
            if os.path.exists(filepath):
                try:
                    df = pd.read_excel(filepath, sheet_name=_detectar_hoja(filepath))
                    
                    # Buscar columnas de terminales (pueden ser 'Terminal', 'De Terminal', 'Para Terminal')
                    columnas_terminales = []
                    for col in df.columns:
                        col_lower = str(col).lower()
                        if 'terminal' in col_lower:
                            columnas_terminales.append(col)
                    
                    # Extraer terminales únicos de todas las columnas encontradas
                    # Excluir terminales con * (son manuales, no se engastan)
                    if columnas_terminales:
                        for col in columnas_terminales:
                            terminales_unicos = df[col].dropna().unique()
                            nuevos_terminales = [
                                str(t).strip() for t in terminales_unicos
                                if str(t).strip() and not str(t).strip().endswith('*')
                            ]
                            terminales_sistema.update(nuevos_terminales)
                        archivos_procesados += 1
                    
                except Exception as e:
                    errores_lectura.append({
                        'archivo': archivo,
                        'error': str(e)
                    })
        
        # Obtener asignaciones actuales
        maquina_repo = MaquinaRepository(db)
        maquinas = maquina_repo.obtener_todas_maquinas()
        
        # Crear diccionario de asignaciones
        terminales_asignados = {}
        for maquina in maquinas:
            terminales_maq = maquina_repo.obtener_terminales_asignados(maquina['id'])
            for terminal in terminales_maq:
                terminales_asignados[terminal] = {
                    'maquina_id': maquina['id'],
                    'maquina_nombre': maquina['nombre'],
                    'puesto_nombre': maquina.get('puesto_nombre', '')
                }
        
        # Preparar respuesta con estado de cada terminal
        terminales_con_estado = []
        for terminal in sorted(list(terminales_sistema)):
            estado = {
                'terminal': terminal,
                'asignado': terminal in terminales_asignados,
                'asignacion': terminales_asignados.get(terminal, None)
            }
            terminales_con_estado.append(estado)
        
        # Contar terminales sin asignar
        sin_asignar = len([t for t in terminales_con_estado if not t['asignado']])
        
        respuesta = {
            'success': True,
            'terminales': terminales_con_estado,
            'total': len(terminales_sistema),
            'sin_asignar': sin_asignar,
            'asignados': len(terminales_asignados),
            'archivos_procesados': archivos_procesados,
            'total_archivos': len(codigos)
        }
        
        # Incluir errores si los hay (para debugging)
        if errores_lectura:
            respuesta['errores_lectura'] = errores_lectura
        
        return jsonify(respuesta)
        
    except Exception as e:
        return error_interno(e, 'Error al obtener terminales')


@bp.route('/api/excel/<path:archivo>/terminales', methods=['GET'])
def api_excel_terminales(archivo):
    """Obtener terminales que REALMENTE se engastan en un archivo Excel.

    Usa la misma lógica que la vista de engastado (_crimps_por_terminal_archivo):
    un terminal solo cuenta si tiene al menos un crimp real (lado sin '*'). Así el
    detalle de la visualización coincide con la lista seleccionable y el peso
    ponderado, sin incluir terminales que solo aparecen con asterisco (no se engastan).
    """
    try:
        archivo = os.path.basename((archivo or '').strip())
        if not archivo:
            return jsonify({
                'success': False,
                'error': 'Archivo no especificado'
            }), 400

        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'data/cortes')
        filepath = os.path.join(upload_folder, archivo)

        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'error': f'Archivo no encontrado: {archivo}'
            }), 404

        crimps = _crimps_por_terminal_archivo(archivo)
        terminales = sorted(t for t, n in crimps.items() if n > 0)

        return jsonify({
            'success': True,
            'terminales': terminales,
            'total': len(terminales)
        })

    except Exception as e:
        return error_interno(e)


@bp.route('/api/asignar-terminal', methods=['POST'])
def api_asignar_terminal():
    """Asignar un terminal a una máquina"""
    try:
        data = request.get_json()
        
        terminal = data.get('terminal', '').strip()
        maquina_id = data.get('maquina_id', '').strip()
        
        if not terminal or not maquina_id:
            return jsonify({
                'success': False,
                'message': 'Terminal y máquina son obligatorios'
            }), 400
        
        maquina_repo = MaquinaRepository(db)
        
        # Verificar que no esté ya asignado
        asignacion_actual = maquina_repo.verificar_terminal_asignado(terminal)
        if asignacion_actual:
            return jsonify({
                'success': False,
                'message': f'El terminal ya está asignado a {asignacion_actual["maquina_nombre"]}'
            }), 400
        
        # Asignar terminal
        if maquina_repo.asignar_terminal(maquina_id, terminal):
            return jsonify({
                'success': True,
                'message': f'Terminal {terminal} asignado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al asignar el terminal'
            }), 500
            
    except Exception as e:
        return error_interno(e, 'Error al asignar terminal')


@bp.route('/api/desasignar-terminal', methods=['POST'])
def api_desasignar_terminal():
    """Desasignar un terminal de su máquina actual"""
    try:
        data = request.get_json()
        
        terminal = data.get('terminal', '').strip()
        
        if not terminal:
            return jsonify({
                'success': False,
                'message': 'Terminal es obligatorio'
            }), 400
        
        maquina_repo = MaquinaRepository(db)
        
        if maquina_repo.desasignar_terminal(terminal):
            return jsonify({
                'success': True,
                'message': f'Terminal {terminal} desasignado correctamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Terminal no encontrado o no asignado'
            }), 404
            
    except Exception as e:
        return error_interno(e, 'Error al desasignar terminal')


# ==================== PALETA DE COLORES DE CABLES ====================

def _text_color_for_bg(hex_color):
    """Devuelve #000000 o #ffffff según la luminancia relativa (WCAG 2.1)."""
    try:
        h = str(hex_color).lstrip('#')
        if len(h) != 6:
            return '#ffffff'
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        def _lin(c):
            c /= 255.0
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        L = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
        return '#000000' if L > 0.179 else '#ffffff'
    except Exception:
        return '#ffffff'


@bp.route('/api/cable-colores', methods=['GET'])
def api_cable_colores_get():
    """Devuelve todos los colores de cables definidos en BD"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT cod_cable, color_hex, color_texto FROM cable_colores ORDER BY cod_cable"
            )).fetchall()
        return jsonify({'success': True, 'colores': [
            {'cod_cable': r[0], 'color_hex': r[1],
             'color_texto': r[2] if r[2] else None}
            for r in rows
        ]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/cable-colores', methods=['POST'])
def api_cable_colores_upsert():
    """Crea o actualiza el color de un cable (cod_cable, color_hex, color_texto opcional)"""
    try:
        data = request.get_json() or {}
        cod = (data.get('cod_cable') or '').strip().upper()
        hex_col = (data.get('color_hex') or '').strip().lower()
        # color_texto: None/'' = auto (calcular por luminancia), o un hex válido
        color_texto_raw = (data.get('color_texto') or '').strip().lower()
        color_texto = color_texto_raw if re.match(r'^#[0-9a-f]{6}$', color_texto_raw) else None
        if not cod or not hex_col:
            return jsonify({'success': False, 'error': 'cod_cable y color_hex son obligatorios'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO cable_colores (cod_cable, color_hex, color_texto) VALUES (:c, :h, :t) "
                "ON CONFLICT(cod_cable) DO UPDATE SET color_hex=excluded.color_hex, color_texto=excluded.color_texto"
            ), {'c': cod, 'h': hex_col, 't': color_texto})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/cable-colores/<path:cod_cable>', methods=['DELETE'])
def api_cable_colores_delete(cod_cable):
    """Elimina la asignación de color de un cable (vuelve al hash fallback)"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text("DELETE FROM cable_colores WHERE cod_cable = :c"), {'c': cod_cable.upper()})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/cable-colores/sin-asignar', methods=['GET'])
def api_cable_colores_sin_asignar():
    """Cables presentes en etiquetas_elementos que no tienen color definido en BD"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT cod_cable FROM etiquetas_elementos
                WHERE cod_cable IS NOT NULL AND cod_cable != '' AND LOWER(cod_cable) != 'nan'
                  AND UPPER(cod_cable) NOT IN (SELECT cod_cable FROM cable_colores)
                ORDER BY cod_cable
            """)).fetchall()
        return jsonify({'success': True, 'cables': [r[0] for r in rows]})
    except Exception as e:
        return error_interno(e)


# ==================== OPERARIOS ====================

@bp.route('/api/operarios', methods=['GET'])
def api_operarios_get():
    """Listar operarios activos"""
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, nombre, activo, created_at FROM operarios ORDER BY nombre"
            )).fetchall()
        return jsonify({'success': True, 'operarios': [
            {'id': r[0], 'nombre': r[1], 'activo': r[2], 'created_at': r[3]}
            for r in rows
        ]})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios', methods=['POST'])
def api_operarios_create():
    """Crear nuevo operario"""
    try:
        import uuid
        data = request.get_json() or {}
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400
        op_id = str(uuid.uuid4())[:8]
        with db.engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO operarios (id, nombre) VALUES (:id, :nombre)"
            ), {'id': op_id, 'nombre': nombre})
            conn.commit()
        return jsonify({'success': True, 'operario': {'id': op_id, 'nombre': nombre, 'activo': 1}})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>', methods=['PUT'])
def api_operarios_update(op_id):
    """Actualizar nombre de operario"""
    try:
        data = request.get_json() or {}
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Nombre es obligatorio'}), 400
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET nombre=:nombre WHERE id=:id"
            ), {'nombre': nombre, 'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>', methods=['DELETE'])
def api_operarios_delete(op_id):
    """Desactivar operario"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET activo=0 WHERE id=:id"
            ), {'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/operarios/<op_id>/activar', methods=['POST'])
def api_operarios_activar(op_id):
    """Reactivar operario desactivado"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE operarios SET activo=1 WHERE id=:id"
            ), {'id': op_id})
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


# ==================== REPORTS / TRAZABILIDAD ====================

def _terminales_validos_bono(nombre_bono):
    """Set de terminales que REALMENTE se engastan en un bono (crimps > 0).

    Devuelve None si no se puede determinar (bono desconocido o sin archivos),
    en cuyo caso el llamante no debe filtrar. Si devuelve un set no vacío,
    los terminales que no estén en él solo aparecen con '*' y no se ponen.
    """
    try:
        bono_repo = BonoRepository(db)
        orden_repo = OrdenRepository(db)
        bono = bono_repo.obtener_bono_por_nombre(nombre_bono)
        if not bono:
            return None
        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])
        validos = set()
        cache = {}
        for orden in ordenes:
            archivo = orden.get('archivo_excel')
            if not archivo:
                continue
            if archivo not in cache:
                cache[archivo] = _crimps_por_terminal_archivo(archivo)
            for terminal, n in cache[archivo].items():
                if terminal and n and n > 0:
                    validos.add(str(terminal).upper())
        return validos or None
    except Exception:
        return None


@bp.route('/api/report/progreso', methods=['GET'])
def api_report_progreso():
    """
    Agrega todos los JSON de progreso y devuelve trazabilidad completa.
    Parámetros opcionales:
      ?bono=<nombre>        → filtrar por bono
      ?terminal=<codigo>    → filtrar por terminal
      ?operario=<nombre>    → filtrar por operario
    """
    try:
        filtro_bono = request.args.get('bono', '').strip() or None
        filtro_terminal = request.args.get('terminal', '').strip().upper() or None
        filtro_operario = request.args.get('operario', '').strip() or None

        data_dir = current_app.config['DATA_DIR']
        registros = []

        # Cache de terminales que REALMENTE se engastan por bono (crimps > 0),
        # para no mostrar terminales que solo aparecen con '*' (no se ponen).
        _validos_cache = {}

        for fname in sorted(os.listdir(data_dir)):
            if not (fname.startswith('progreso_bono_') and fname.endswith('.json')):
                continue
            nombre_bono = fname[len('progreso_bono_'):-len('.json')]
            if filtro_bono and nombre_bono != filtro_bono:
                continue
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    progreso = json.load(f)
            except Exception:
                continue

            if nombre_bono not in _validos_cache:
                _validos_cache[nombre_bono] = _terminales_validos_bono(nombre_bono)
            validos = _validos_cache[nombre_bono]

            for terminal, datos in progreso.items():
                if filtro_terminal and terminal.upper() != filtro_terminal:
                    continue
                # Ocultar terminales que no se engastan (solo aparecen con '*')
                if validos and terminal.upper() not in validos:
                    continue
                operario = datos.get('operario', '')
                if filtro_operario and operario.lower() != filtro_operario.lower():
                    continue
                registros.append({
                    'bono': nombre_bono,
                    'terminal': terminal,
                    'operario': operario,
                    'estado': datos.get('estado', ''),
                    'carros_completados': datos.get('carros_completados', []),
                    'fecha_inicio': datos.get('fecha_inicio', ''),
                    'fecha_ultima_actualizacion': datos.get('fecha_ultima_actualizacion', ''),
                })

        # Estadísticas
        bonos_unicos = len(set(r['bono'] for r in registros))
        terminales_unicos = len(set(r['terminal'] for r in registros))
        operarios_unicos = len(set(r['operario'] for r in registros if r['operario']))

        return jsonify({
            'success': True,
            'registros': registros,
            'total': len(registros),
            'bonos': bonos_unicos,
            'terminales': terminales_unicos,
            'operarios': operarios_unicos,
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return error_interno(e)


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
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/api/datos_trabajo_v3')
def datos_trabajo_v3():
    """
    Obtener datos de trabajo para V3
    Parámetros: archivo, terminal, maquina
    Procesa el Excel y retorna los paquetes agrupados para el terminal
    """
    try:
        archivo = request.args.get('archivo')
        terminal = request.args.get('terminal')
        maquina = request.args.get('maquina')
        
        if not archivo or not terminal:
            return jsonify({
                'success': False,
                'message': 'Parámetros incompletos (se requiere archivo y terminal)'
            })
        
        # Crear instancia del ExcelManager
        upload_folder = current_app.config['UPLOAD_FOLDER']
        manager = ExcelManager(upload_folder)
        
        # Cargar el archivo Excel
        if not manager.cargar_excel_directo(archivo):
            return jsonify({
                'success': False,
                'message': f'No se pudo cargar el archivo {archivo}. Verifica que existe en data/cortes/'
            })
        
        # Buscar datos del terminal
        resultados = manager.buscar_terminal(terminal)
        
        if not resultados:
            return jsonify({
                'success': True,
                'paquetes': [],
                'total_terminales': 0,
                'grupos': [],
                'message': f'Terminal {terminal} no encontrado en el archivo'
            })
        
        # Agrupar por cable y elemento
        grupos = manager.agrupar_por_cable_elemento(resultados, terminal)
        
        # Convertir a lista de paquetes
        paquetes_raw = []
        total_terminales = 0

        for grupo in grupos.values():
            paquete = {
                'cod_cable': grupo['cod_cable'],
                'elemento': grupo['elemento'],
                'descripcion': grupo['descripcion'],
                'seccion': grupo['seccion'],
                'longitud': grupo['longitud'],
                'cables': grupo['todos_cables'],
                'num_cables': grupo['num_cables'],
                'num_terminales': grupo['num_terminales'],
                'cables_doble_terminal': grupo.get('cables_doble_terminal', []),
                'cables_de_terminal': grupo.get('cables_de_terminal', []),
                'cables_para_terminal': grupo.get('cables_para_terminal', []),
                'archivo_excel': archivo  # para lookup de etiqueta correcto por archivo
            }
            paquetes_raw.append(paquete)
            total_terminales += grupo['num_terminales']

        # Ocultar paquetes que no tienen NADA que engastar para este terminal.
        # Ocurre cuando todas las filas del grupo tienen el elemento marcado con '*'
        # (terminal no se engasta ahí): las tres listas de cables quedan vacías.
        # El operario no debe ver esos paquetes (no hay trabajo que hacer en ellos).
        def _tiene_engaste(p):
            return (len(p.get('cables_de_terminal', [])) +
                    len(p.get('cables_para_terminal', [])) +
                    len(p.get('cables_doble_terminal', []))) > 0

        paquetes_raw = [p for p in paquetes_raw if _tiene_engaste(p)]

        # Fusionar paquetes de la misma serie SXX en un paquete virtual único
        _SERIE_PAT = re.compile(r'\((\w+)\)$')
        series_paquetes = {}       # serie_code -> [paquete, ...]
        paquetes_individuales = []
        for p in paquetes_raw:
            m = _SERIE_PAT.search(str(p['elemento']).strip())
            if m:
                series_paquetes.setdefault(m.group(1), []).append(p)
            else:
                paquetes_individuales.append(p)

        # NOTA: NO se eliminan individuales cuyo nombre base exista como hijo de serie.
        # TB1 y TB1(S206) son grupos distintos aunque compartan cod_cable y base del nombre.

        paquetes = list(paquetes_individuales)
        for serie_code, miembros in series_paquetes.items():
            for sub_idx, mp in enumerate(miembros, 1):
                mp['sub_numero'] = sub_idx
                mp['grupo_serie'] = serie_code
            paquetes.append({
                'cod_cable': 'GRUPO_SERIE',
                'elemento': serie_code,
                'descripcion': f'Grupo serie {serie_code}',
                'seccion': miembros[0]['seccion'] if miembros else '',
                'longitud': 0.0,
                'cables': [],
                'num_cables': sum(m['num_cables'] for m in miembros),
                'num_terminales': sum(m['num_terminales'] for m in miembros),
                'cables_doble_terminal': [c for m in miembros for c in m.get('cables_doble_terminal', [])],
                'cables_de_terminal':    [c for m in miembros for c in m.get('cables_de_terminal', [])],
                'cables_para_terminal':  [c for m in miembros for c in m.get('cables_para_terminal', [])],
                'es_grupo': True,
                'grupo_serie': serie_code,
                'sub_paquetes': miembros
            })
        
        # -------------------------------------------------------
        # Bloqueo concurrente: verificar y, opcionalmente, crear sesión
        # -------------------------------------------------------
        iniciar_sesion = request.args.get('iniciar_sesion', '').lower() in ('1', 'true')
        sesion_id_param = request.args.get('sesion_id', '').strip() or None

        sesion_repo = SesionTrabajoRepository(db)
        sesion_id_nuevo = None

        if iniciar_sesion and maquina:
            # Crear sesión con lista vacía: los paquetes se actualizarán desde el frontend
            # de 5 en 5 (página a página), para no bloquear paquetes que aún no están
            # en pantalla del operario.
            sesion_id_nuevo = sesion_repo.crear_sesion(
                maquina_id=maquina,
                terminal_codigo=terminal,
                archivo_excel=archivo,
                carro_numero=request.args.get('carro', ''),
                paquetes=[]
            )
            # Verificar qué paquetes están reclamados por OTRAS sesiones
            bloqueos = sesion_repo.verificar_bloqueos(paquetes, sesion_id_excluir=sesion_id_nuevo)
        else:
            # Solo consulta (preview de carros, sin crear sesión)
            excluir = sesion_id_param
            bloqueos = sesion_repo.verificar_bloqueos(paquetes, sesion_id_excluir=excluir)

        # Anotar en cada paquete si está bloqueado y por qué máquina
        paquetes_bloqueados_count = 0
        for paquete in paquetes:
            if paquete.get('es_grupo'):
                # Paquete virtual de serie: verificar sub_paquetes individuales
                sub_bloqueados = 0
                for sub in paquete.get('sub_paquetes', []):
                    clave = (sub['cod_cable'], sub['elemento'])
                    info_bloqueo = bloqueos.get(clave)
                    if info_bloqueo:
                        sub['bloqueado'] = True
                        sub['bloqueado_por'] = info_bloqueo['maquina_nombre']
                        sub['bloqueado_terminal'] = info_bloqueo['terminal_codigo']
                        sub_bloqueados += 1
                    else:
                        sub['bloqueado'] = False
                        sub['bloqueado_por'] = None
                        sub['bloqueado_terminal'] = None
                paquete['bloqueado'] = sub_bloqueados > 0
                paquete['bloqueado_por'] = None
                paquete['bloqueado_terminal'] = None
                if sub_bloqueados > 0:
                    paquetes_bloqueados_count += 1
            else:
                clave = (paquete['cod_cable'], paquete['elemento'])
                info_bloqueo = bloqueos.get(clave)
                if info_bloqueo:
                    paquete['bloqueado'] = True
                    paquete['bloqueado_por'] = info_bloqueo['maquina_nombre']
                    paquete['bloqueado_terminal'] = info_bloqueo['terminal_codigo']
                    paquetes_bloqueados_count += 1
                else:
                    paquete['bloqueado'] = False
                    paquete['bloqueado_por'] = None
                    paquete['bloqueado_terminal'] = None

        respuesta = {
            'success': True,
            'paquetes': paquetes,
            'total_terminales': total_terminales,
            'grupos': list(grupos.values()),
            'terminal': terminal,
            'archivo': archivo,
            'paquetes_bloqueados': paquetes_bloqueados_count,
            'paquetes_libres': len(paquetes) - paquetes_bloqueados_count
        }
        if sesion_id_nuevo:
            respuesta['sesion_id'] = sesion_id_nuevo

        return jsonify(respuesta)

    except Exception as e:
        import traceback
        print(f"❌ Error en datos_trabajo_v3: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al obtener datos: {str(e)}'
        })


# ==================== SESIONES DE TRABAJO (BLOQUEO CONCURRENTE) ====================

@bp.route('/api/sesion/liberar', methods=['POST'])
def api_liberar_sesion():
    """
    Libera una sesión de trabajo activa (todos sus paquetes quedan libres).
    Llamado cuando el operario termina el terminal o navega fuera.
    """
    try:
        data = request.get_json() or {}
        sesion_id = data.get('sesion_id', '').strip()

        if not sesion_id:
            return jsonify({'success': False, 'message': 'sesion_id es obligatorio'}), 400

        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.liberar_sesion(sesion_id)
        return jsonify({'success': True})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/liberar-paquete', methods=['POST'])
def api_liberar_paquete_sesion():
    """
    Libera un paquete concreto de una sesión (el operario lo saltó).
    Si la sesión queda sin paquetes, se libera por completo.
    """
    try:
        data = request.get_json() or {}
        sesion_id = data.get('sesion_id', '').strip()
        cod_cable = data.get('cod_cable', '').strip()
        elemento = data.get('elemento', '').strip()

        if not sesion_id or not elemento:
            return jsonify({'success': False, 'message': 'sesion_id y elemento son obligatorios'}), 400

        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.liberar_paquete_de_sesion(sesion_id, cod_cable, elemento)
        return jsonify({'success': True})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/actualizar-paquetes', methods=['PUT'])
def api_actualizar_paquetes_sesion():
    """
    Reemplaza los paquetes de una sesión activa con el lote actual visible en pantalla.
    El frontend llama a este endpoint cada vez que muestra una nueva página de paquetes,
    de modo que la sesión solo bloquea los paquetes que el operario tiene en ese momento.
    """
    try:
        data = request.get_json() or {}
        sesion_id = data.get('sesion_id', '').strip()
        paquetes = data.get('paquetes', [])

        if not sesion_id:
            return jsonify({'success': False, 'message': 'sesion_id es obligatorio'}), 400

        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.actualizar_paquetes_sesion(sesion_id, paquetes)
        return jsonify({'success': True})

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/verificar-pendientes', methods=['POST'])
def api_verificar_pendientes():
    """
    Comprueba qué paquetes de una lista están bloqueados por otras sesiones activas.

    Body JSON:
      { "paquetes": [{"cod_cable": "X", "elemento": "Y"}, ...],
        "sesion_id_excluir": "<uuid>"  (opcional, para no contarse a uno mismo) }

    Responde con:
      - bloqueados: paquetes todavía en uso por otra sesión
      - libres:     paquetes disponibles ahora
      - total:      número total consultado
    """
    try:
        data = request.get_json() or {}
        paquetes = data.get('paquetes', [])
        sesion_id_excluir = data.get('sesion_id_excluir', '').strip() or None

        if not paquetes:
            return jsonify({'success': True, 'bloqueados': [], 'libres': [], 'total': 0})

        sesion_repo = SesionTrabajoRepository(db)
        bloqueos = sesion_repo.verificar_bloqueos(paquetes, sesion_id_excluir=sesion_id_excluir)

        bloqueados = []
        libres = []
        for p in paquetes:
            clave = (p.get('cod_cable', ''), p.get('elemento', ''))
            if clave in bloqueos:
                info = bloqueos[clave]
                bloqueados.append({**p,
                    'bloqueado_por': info.get('maquina_nombre') or info.get('maquina_id', ''),
                    'bloqueado_terminal': info.get('terminal_codigo', '')
                })
            else:
                libres.append(p)

        return jsonify({
            'success': True,
            'total': len(paquetes),
            'bloqueados': bloqueados,
            'libres': libres,
            'num_bloqueados': len(bloqueados),
            'num_libres': len(libres)
        })

    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/sesiones-activas', methods=['GET'])
def api_sesiones_activas():
    """
    Devuelve las sesiones activas con info del bono al que pertenecen.
    Parámetro opcional: ?bono=nombre_bono para filtrar por bono.
    """
    try:
        filtro_bono = request.args.get('bono', '').strip() or None

        sesion_repo = SesionTrabajoRepository(db)
        # Extender la consulta para incluir bono a través de carro
        query = """
            SELECT st.id, st.maquina_id, st.terminal_codigo,
                   st.archivo_excel, st.carro_numero,
                   st.timestamp_inicio, st.paquetes_json,
                   m.nombre AS maquina_nombre,
                   b.nombre AS bono_nombre
            FROM sesiones_trabajo st
            LEFT JOIN maquinas m ON st.maquina_id = m.id
            LEFT JOIN carros c ON CAST(c.numero AS TEXT) = st.carro_numero
            LEFT JOIN bonos b ON b.id = c.bono_id
            WHERE st.activo = 1
        """
        params = {}
        if filtro_bono:
            query += " AND b.nombre = :bono"
            params['bono'] = filtro_bono
        query += " ORDER BY st.timestamp_inicio DESC"

        sesiones = sesion_repo.execute_select(query, params)
        result = []
        for s in sesiones:
            try:
                paquetes = json.loads(s['paquetes_json'] or '[]')
            except Exception:
                paquetes = []
            result.append({
                'id': s['id'],
                'maquina_nombre': s.get('maquina_nombre') or s['maquina_id'],
                'terminal_codigo': s['terminal_codigo'],
                'carro_numero': s['carro_numero'],
                'bono_nombre': s.get('bono_nombre') or '—',
                'timestamp_inicio': s['timestamp_inicio'],
                'num_paquetes': len(paquetes),
                'paquetes': paquetes
            })
        return jsonify({'success': True, 'sesiones': result, 'total': len(result)})
    except Exception as e:
        return error_interno(e)



@bp.route('/api/sesion/liberar-sesion/<sesion_id>', methods=['POST'])
def api_liberar_sesion_admin(sesion_id):
    """Libera una sesión concreta por su ID."""
    try:
        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.liberar_sesion(sesion_id)
        return jsonify({'success': True})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/sesion/limpiar-sesiones-fantasma', methods=['POST'])
def api_limpiar_sesiones_fantasma():
    """Libera TODAS las sesiones activas de golpe."""
    try:
        sesion_repo = SesionTrabajoRepository(db)
        sesion_repo.execute_query(
            "UPDATE sesiones_trabajo SET activo = 0 WHERE activo = 1", {}
        )
        return jsonify({'success': True, 'message': 'Todos los bloqueos liberados'})
    except Exception as e:
        return error_interno(e)


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
def api_comprobar_actualizaciones():
    """
    Comprueba si hay commits nuevos en GitHub comparando con el HEAD local.
    """
    try:
        base_dir = current_app.root_path.replace('\\app', '').replace('/app', '')
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
def api_actualizar_sistema():
    """
    Ejecuta git pull origin main y actualiza dependencias si requirements.txt cambió.
    El servidor debe reiniciarse manualmente para aplicar cambios de Python.
    """
    try:
        base_dir = current_app.root_path.replace('\\app', '').replace('/app', '')
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


# ==================== API DE ETIQUETAS ====================

@bp.route('/api/etiquetas/grupos_json', methods=['GET'])
def api_etiquetas_grupos_json():
    """Obtener grupos de etiquetas desde SQL"""
    try:
        # Leer desde base de datos SQLite
        query = """
            SELECT
                numero_etiqueta,
                cod_cable,
                elemento,
                descripcion,
                seccion,
                longitud,
                de_terminal,
                num_cables,
                num_terminales,
                archivo_excel,
                codigo_corte,
                grupo_serie,
                es_grupo_padre,
                sub_numero
            FROM etiquetas_elementos
            ORDER BY numero_etiqueta, sub_numero
        """
        
        with db.engine.connect() as conn:
            resultados = conn.execute(text(query)).fetchall()
        
        grupos = []
        for row in resultados:
            grupos.append({
                'numero_etiqueta': row[0],
                'cod_cable': row[1],
                'elemento': row[2],
                'descripcion': row[3],
                'seccion': row[4],
                'longitud': row[5],
                'de_terminal': row[6],
                'num_cables': row[7],
                'num_terminales': row[8],
                'archivo': row[9],
                'codigo_corte': row[10],
                'grupo_serie': row[11],
                'es_grupo_padre': row[12],
                'sub_numero': row[13]
            })
        
        return jsonify({
            'success': True,
            'grupos': grupos,
            'total': len(grupos)
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al cargar etiquetas: {str(e)}'
        })


@bp.route('/api/etiquetas/cargar_grupos', methods=['POST'])
def api_etiquetas_cargar_grupos():
    """Cargar grupos de etiquetas de un archivo específico"""
    try:
        data = request.get_json()
        archivo = data.get('archivo')
        
        if not archivo:
            return jsonify({
                'success': False,
                'message': 'Falta nombre de archivo'
            })
        
        # Primero: buscar si ya existen etiquetas en la BD
        query_check = """
            SELECT COUNT(*) FROM etiquetas_elementos
            WHERE archivo_excel = :archivo
        """
        
        with db.engine.connect() as conn:
            count = conn.execute(text(query_check), {'archivo': archivo}).scalar()
        
        # Si no existen, generarlas automáticamente usando la misma lógica que /api/etiquetas/regenerar
        if count == 0:
            print(f"📦 Generando etiquetas para {archivo}...")
            excel_path = os.path.join(current_app.config['UPLOAD_FOLDER'], archivo)
            if not os.path.exists(excel_path):
                return jsonify({'success': False, 'message': f'Archivo no encontrado: {archivo}'})
            try:
                total = _regenerar_etiquetas_archivo(archivo, excel_path)
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error al generar etiquetas: {str(e)}'})
            print(f"✅ {total} etiquetas generadas y guardadas")
            # Caer al bloque de lectura de BD (count > 0 ahora)
        
        # Si ya existen, cargarlas de la BD
        query = """
            SELECT
                numero_etiqueta,
                cod_cable,
                elemento,
                descripcion,
                seccion,
                longitud,
                de_terminal,
                num_cables,
                num_terminales,
                archivo_excel,
                codigo_corte,
                grupo_serie,
                es_grupo_padre,
                sub_numero
            FROM etiquetas_elementos
            WHERE archivo_excel = :archivo
            ORDER BY numero_etiqueta, sub_numero
        """

        with db.engine.connect() as conn:
            resultados = conn.execute(text(query), {'archivo': archivo}).fetchall()

        grupos = []
        codigo_corte = None

        for row in resultados:
            if not codigo_corte:
                codigo_corte = row[10]

            grupos.append({
                'numero_etiqueta': row[0],
                'cod_cable': row[1],
                'elemento': row[2],
                'descripcion': row[3],
                'seccion': row[4],
                'longitud': row[5],
                'de_terminal': row[6],
                'num_cables': row[7],
                'num_terminales': row[8],
                'archivo': row[9],
                'codigo_corte': row[10],
                'grupo_serie': row[11],
                'es_grupo_padre': row[12],
                'sub_numero': row[13]
            })
        
        return jsonify({
            'success': True,
            'grupos': grupos,
            'total': len(grupos),
            'codigo_corte': codigo_corte,
            'generadas': False
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al cargar grupos: {str(e)}'
        })


@bp.route('/api/etiquetas/generar_html', methods=['POST'])
def generar_etiquetas_html():
    """Generar HTML de etiquetas para imprimir en impresora normal"""
    try:
        data = request.get_json()
        archivo = data.get('archivo', '').strip()
        grupos = data.get('grupos', [])
        codigo_corte = data.get('codigo_corte', '').strip()
        
        if not archivo or not grupos:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos (archivo, grupos)'
            }), 400
        
        # Cargar colores desde BD
        color_map = {}
        text_color_map = {}
        try:
            with db.engine.connect() as _cc:
                _rows = _cc.execute(text("SELECT cod_cable, color_hex, color_texto FROM cable_colores")).fetchall()
                color_map = {r[0]: r[1] for r in _rows}
                text_color_map = {r[0]: r[2] for r in _rows if r[2]}
        except Exception:
            pass

        # Generar HTML para imprimir
        html = generar_html_etiquetas_impresion(grupos, archivo, codigo_corte, color_map=color_map, text_color_map=text_color_map)
        
        return jsonify({
            'success': True,
            'html': html,
            'total_etiquetas': len(grupos)
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return error_interno(e, 'Error al generar HTML')


_COLOR_PALETA = ['#d97706','#2563eb','#059669','#7c3aed','#dc2626','#0891b2',
                 '#db2777','#65a30d','#0d9488','#ea580c','#4f46e5','#be185d']

def _get_cable_color(cod_cable, color_map=None):
    if not cod_cable or str(cod_cable).strip() == '' or str(cod_cable).lower() == 'nan':
        return '#6b7280'
    key = str(cod_cable).strip().upper()
    if color_map and key in color_map:
        return color_map[key]
    h = 0
    for c in key:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return _COLOR_PALETA[h % len(_COLOR_PALETA)]


def generar_html_etiquetas_impresion(grupos, archivo, codigo_corte="", color_map=None, text_color_map=None):
    """
    Generar HTML con CSS para imprimir etiquetas en impresora normal
    Formato: 13 columnas x 5 filas = 65 etiquetas por hoja A4 apaisada
    """
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Etiquetas - {archivo}</title>
    <style>
        @media print {{
            @page {{
                size: A4 landscape;
                margin: 10mm 10mm 10mm 8mm;
            }}
            body {{
                margin: 0;
                padding: 0;
            }}
            .no-print {{
                display: none;
            }}
            .page-break {{
                page-break-after: always;
                page-break-inside: avoid;
                break-after: page;
            }}
            .etiquetas-container {{
                page-break-inside: avoid;
                break-inside: avoid;
            }}
        }}
        
        body {{
            font-family: Arial, sans-serif;
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 10px;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 5px;
        }}
        
        .no-print {{
            margin-bottom: 15px;
            text-align: center;
        }}
        
        .etiquetas-container {{
            display: grid;
            grid-template-columns: repeat(13, 21.3mm);
            grid-template-rows: repeat(5, 38mm);
            gap: 0;
            width: fit-content;
            margin: 0 auto;
            justify-content: center;
        }}
        
        .etiqueta {{
            width: 21.3mm;
            height: 38mm;
            border: 2px solid #333;
            padding: 0;
            background: white;
            box-sizing: border-box;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            break-inside: avoid;
            page-break-inside: avoid;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
            color-adjust: exact;
        }}
        
        .etiqueta-top {{
            height: 19mm;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border-bottom: 2px solid #0ea5e9;
            padding: 2mm 1mm;
            gap: 1mm;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
            color-adjust: exact;
        }}
        
        .etiqueta-numero {{
            font-size: 16pt;
            font-weight: bold;
            padding: 2mm 4mm;
            border-radius: 4mm;
            min-width: 10mm;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
            color-adjust: exact;
        }}
        
        .etiqueta-elemento {{
            font-size: 9pt;
            font-weight: bold;
            color: #1e40af;
            text-align: center;
            line-height: 1.1;
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            word-break: break-word;
        }}
        
        .etiqueta-bottom {{
            height: 19mm;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: white;
            padding: 2mm 1mm;
            gap: 0.5mm;
        }}
        
        .etiqueta-info-line {{
            font-size: 7pt;
            text-align: center;
            line-height: 1.2;
            width: 100%;
        }}
        
        .etiqueta-corte {{
            font-weight: bold;
            color: #059669;
            font-size: 7pt;
            background: #d1fae5;
            padding: 0.5mm 2mm;
            border-radius: 2mm;
            margin-bottom: 0.5mm;
        }}
        
        .etiqueta-cable {{
            font-weight: bold;
            color: #2563eb;
            font-size: 8pt;
        }}
        
        .etiqueta-descripcion {{
            color: #334155;
            font-size: 7pt;
        }}
        
        .etiqueta-seccion {{
            color: #64748b;
            font-size: 7pt;
            background: #f1f5f9;
            padding: 0.5mm 2mm;
            border-radius: 2mm;
            margin-top: 0.5mm;
        }}
        
        /* Estilos para vista previa en pantalla */
        @media screen {{
            .etiquetas-container {{
                transform: scale(1.5);
                transform-origin: top left;
                margin-bottom: 50px;
            }}
        }}
    </style>
</head>
<body>
    <div class="no-print">
        <button onclick="window.print()" style="padding: 10px 20px; font-size: 16px; cursor: pointer; background: #4CAF50; color: white; border: none; border-radius: 5px;">
            🖨️ Imprimir Etiquetas
        </button>
        <button onclick="window.close()" style="padding: 10px 20px; font-size: 16px; cursor: pointer; background: #f44336; color: white; border: none; border-radius: 5px; margin-left: 10px;">
            ✕ Cerrar
        </button>
        <p style="margin-top: 10px; color: #666;">Formato: A4 Apaisado | 13 columnas × 5 filas | 21mm × 38mm por etiqueta</p>
    </div>
    
    <div class="header no-print">
        <h2>Etiquetas de Grupos - {archivo}</h2>
        <p style="margin-top: 10px; color: #666;">Total de etiquetas: {len(grupos)}</p>
    </div>
    
    <div class="etiquetas-container">
"""
    
    # Generar etiquetas (hasta 65 por página: 13 columnas x 5 filas)
    for i, grupo in enumerate(grupos):
        sub_num = grupo.get('sub_numero', 0)
        if sub_num and sub_num > 0:
            numero = f"{grupo.get('numero_etiqueta', i + 1)}.{str(sub_num).zfill(2)}"
        else:
            numero = grupo.get('numero_etiqueta', i + 1)

        es_padre = grupo.get('es_grupo_padre', 0) == 1
        badge_label = f"★ {numero}" if es_padre else str(numero)
        etq_color   = _get_cable_color(grupo.get('cod_cable', ''), color_map=color_map)
        # Color de texto: manual si existe, sino auto por luminancia
        cod_key = str(grupo.get('cod_cable', '')).strip().upper()
        etq_txt_color = (text_color_map or {}).get(cod_key) or _text_color_for_bg(etq_color)
        border_color = '#f59e0b' if es_padre else '#333'
        top_border   = '#f59e0b' if es_padre else '#0ea5e9'

        # Truncar textos para que quepan en etiquetas pequeñas
        elemento = grupo['elemento'][:15] if len(grupo['elemento']) > 15 else grupo['elemento']
        cod_cable = grupo['cod_cable'][:12] if len(grupo['cod_cable']) > 12 else grupo['cod_cable']
        seccion = grupo.get('seccion', '')[:10] if grupo.get('seccion') else ''
        descripcion = grupo.get('descripcion', '')[:18] if grupo.get('descripcion') else ''

        html += f"""
        <div class="etiqueta" style="border-color: {border_color};">
            <div class="etiqueta-top" style="border-bottom-color: {top_border};">
                <div class="etiqueta-numero" style="background: {etq_color}; color: {etq_txt_color};">{badge_label}</div>
                <div class="etiqueta-elemento">{elemento}</div>
            </div>
            <div class="etiqueta-bottom">"""
        
        # Añadir código de corte si existe
        if codigo_corte:
            html += f"""
                <div class="etiqueta-info-line etiqueta-corte">{codigo_corte}</div>"""
        
        html += f"""
                <div class="etiqueta-info-line etiqueta-cable">{cod_cable}</div>"""
        
        if seccion:
            html += f"""
                <div class="etiqueta-info-line etiqueta-seccion">{seccion}</div>"""
        
        html += """
            </div>
        </div>
"""
        
        # Salto de página cada 65 etiquetas (13 columnas x 5 filas)
        if (i + 1) % 65 == 0 and (i + 1) < len(grupos):
            html += """
    </div>
    <div class="page-break"></div>
    <div class="etiquetas-container">
"""
    
    html += """
    </div>
</body>
</html>
"""
    
    return html


@bp.route('/api/etiquetas/grupos_bono/<nombre_bono>', methods=['GET'])
def api_etiquetas_grupos_bono(nombre_bono):
    """Obtener etiquetas agrupadas de todos los archivos de un bono"""
    try:
        # Obtener órdenes del bono
        bono_repo = BonoRepository(db)
        bono = bono_repo.obtener_bono_por_nombre(nombre_bono)
        
        if not bono:
            return jsonify({
                'success': False,
                'message': f'Bono {nombre_bono} no encontrado'
            })
        
        # Obtener órdenes asociadas
        orden_repo = OrdenRepository(db)
        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])
        
        if not ordenes:
            return jsonify({
                'success': True,
                'grupos': [],
                'total': 0,
                'archivos_procesados': 0
            })
        
        # Obtener códigos de corte de las órdenes (también intentar con archivo_excel)
        codigos = [orden['codigo_corte'] for orden in ordenes if orden.get('codigo_corte')]
        archivos = [orden['archivo_excel'] for orden in ordenes if orden.get('archivo_excel')]
        
        if not codigos and not archivos:
            return jsonify({
                'success': True,
                'grupos': [],
                'total': 0,
                'archivos_procesados': 0
            })
        
        # Construir condiciones LIKE para cada código/archivo
        # Las etiquetas pueden tener el codigo_corte completo (ej: 'h0420724_PC_CAB_...')
        # mientras que las órdenes tienen el código corto (ej: 'H0420724')
        # Se busca por: coincidencia exacta OR que empiece por el código corto
        import sqlite3 as _sqlite3
        
        # Lista de resultados (sin deduplicar por archivo, para que el frontend
        # pueda filtrar por archivo_excel y obtener el número correcto)
        resultados_list = []
        archivos_vistos = set()
        
        with db.engine.connect() as conn:
            raw_conn = conn.connection
            cur = raw_conn.cursor()
            
            # Intentar primero con archivo_excel exacto
            for archivo in archivos:
                nombre_sin_ext = archivo.rsplit('.', 1)[0] if '.' in archivo else archivo
                cur.execute("""
                    SELECT numero_etiqueta, cod_cable, elemento, descripcion, seccion,
                           longitud, de_terminal, num_cables, num_terminales, archivo_excel, codigo_corte,
                           grupo_serie, es_grupo_padre, sub_numero
                    FROM etiquetas_elementos
                    WHERE LOWER(archivo_excel) = LOWER(?) OR LOWER(codigo_corte) = LOWER(?)
                    ORDER BY numero_etiqueta, sub_numero
                """, (archivo, nombre_sin_ext))
                rows = cur.fetchall()
                for row in rows:
                    resultados_list.append(row)
                if rows:
                    archivos_vistos.add(archivo)
            
            # Si no hay resultados, buscar por prefijo (código corto al inicio del código largo)
            if not resultados_list:
                for codigo in codigos:
                    cur.execute("""
                        SELECT numero_etiqueta, cod_cable, elemento, descripcion, seccion,
                               longitud, de_terminal, num_cables, num_terminales, archivo_excel, codigo_corte,
                               grupo_serie, es_grupo_padre, sub_numero
                        FROM etiquetas_elementos
                        WHERE LOWER(codigo_corte) LIKE LOWER(?) || '%'
                           OR LOWER(codigo_corte) = LOWER(?)
                        ORDER BY numero_etiqueta, sub_numero
                    """, (codigo, codigo))
                    for row in cur.fetchall():
                        resultados_list.append(row)
        
        # Ordenar: primero por archivo (para agrupar), luego por numero_etiqueta
        resultados = sorted(resultados_list, key=lambda r: (r[9] or '', r[0] if r[0] else 0))
        
        grupos = []
        for row in resultados:
            grupos.append({
                'numero_etiqueta': row[0],
                'cod_cable': row[1],
                'elemento': row[2],
                'descripcion': row[3],
                'seccion': row[4],
                'longitud': row[5],
                'de_terminal': row[6],
                'num_cables': row[7],
                'num_terminales': row[8],
                'archivo': row[9],
                'codigo_corte': row[10],
                'grupo_serie': row[11],
                'es_grupo_padre': row[12],
                'sub_numero': row[13]
            })
        
        return jsonify({
            'success': True,
            'grupos': grupos,
            'total': len(grupos),
            'archivos_procesados': len(set(g['codigo_corte'] for g in grupos if g.get('codigo_corte')))
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al cargar etiquetas del bono: {str(e)}'
        })


@bp.route('/api/etiquetas/regenerar', methods=['POST'])
def api_etiquetas_regenerar():
    """
    Elimina las etiquetas almacenadas para un archivo y las regenera desde el Excel actual.
    Body JSON: { "archivo": "nombre_del_archivo.xlsx" }
    """
    try:
        data = request.get_json() or {}
        archivo = (data.get('archivo') or '').strip()
        if not archivo:
            return jsonify({'success': False, 'message': 'Falta nombre de archivo'}), 400

        excel_path = os.path.join(current_app.config['UPLOAD_FOLDER'], archivo)
        total = _regenerar_etiquetas_archivo(archivo, excel_path)
        return jsonify({'success': True, 'total': total, 'archivo': archivo})

    except FileNotFoundError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return error_interno(e, 'Error al regenerar')

        # 1. Borrar entradas existentes
        with db.engine.connect() as conn:
            deleted = conn.execute(
                text("DELETE FROM etiquetas_elementos WHERE archivo_excel = :a"), {'a': archivo}
            ).rowcount
            conn.commit()

        print(f"🗑️  Etiquetas eliminadas para {archivo}: {deleted} filas")

        # 2. Regenerar: reusar la lógica de cargar_grupos (que auto-genera cuando count=0)
        # Llamamos internamente a la misma función
        from flask import current_app as _app
        excel_path = os.path.join(_app.config['UPLOAD_FOLDER'], archivo)
        if not os.path.exists(excel_path):
            return jsonify({'success': False, 'message': f'Archivo no encontrado: {archivo}'}), 404

        df = pd.read_excel(excel_path, sheet_name=_detectar_hoja(excel_path))

        grupos_generados = []
        numero_etiqueta = 1
        codigo_corte = archivo.replace('.xlsx', '').replace('.xls', '')

        if 'Cod. cable' not in df.columns or 'De Elemento Etiquetas' not in df.columns:
            return jsonify({'success': False, 'message': 'El archivo no tiene las columnas requeridas'}), 400

        agrupados = df.groupby(['Cod. cable', 'De Elemento Etiquetas']).first().reset_index()

        SERIE_PAT_R = re.compile(r'\((\w+)\)$')
        series_dict_r = {}
        individuales_r = []

        for _, row in agrupados.iterrows():
            cod_cable = str(row['Cod. cable'])
            elemento = str(row['De Elemento Etiquetas']).strip()
            m = SERIE_PAT_R.search(elemento)
            if m:
                series_dict_r.setdefault(m.group(1), []).append((cod_cable, elemento, row))
            else:
                individuales_r.append((cod_cable, elemento, row))

        serie_bases_r = set()
        for miembros_r in series_dict_r.values():
            for cb, el, _ in miembros_r:
                base = SERIE_PAT_R.sub('', el).strip()
                serie_bases_r.add((cb, base))
        # NOTA: NO se eliminan individuales cuyo base exista en series (TB1 != TB1(S206))

        def _get_cols_r(row_data):
            desc = str(row_data.get('Descripción Cable', row_data.get('Descripción', '')))
            sec  = str(row_data.get('Sección', row_data.get('Seccion', '')))
            try:
                lon = float(row_data.get('Longitud', 0) or 0)
            except (ValueError, TypeError):
                lon = 0.0
            det = str(row_data.get('De Terminal', ''))
            return desc, sec, lon, det

        # Series SXX
        for serie_code, miembros in series_dict_r.items():
            total_cables = total_terminales = 0
            primer_det = primer_desc = primer_sec = ''
            for cod_cable, elemento, row_data in miembros:
                mask = (df['Cod. cable'] == cod_cable) & (df['De Elemento Etiquetas'] == elemento)
                nc = int(len(df[mask]))
                total_cables += nc
                total_terminales += nc
                desc, sec, _, det = _get_cols_r(row_data)
                if not primer_det:  primer_det  = det
                if not primer_desc: primer_desc = desc
                if not primer_sec:  primer_sec  = sec

            grupos_generados.append({
                'numero_etiqueta': numero_etiqueta, 'sub_numero': 0, 'es_grupo_padre': 1,
                'grupo_serie': serie_code, 'cod_cable': 'GRUPO_SERIE', 'elemento': serie_code,
                'descripcion': f'Grupo serie {serie_code}', 'seccion': primer_sec,
                'longitud': 0.0, 'de_terminal': primer_det, 'num_cables': total_cables,
                'num_terminales': total_terminales, 'archivo': archivo, 'codigo_corte': codigo_corte
            })
            for sub_idx, (cod_cable, elemento, row_data) in enumerate(miembros, 1):
                mask = (df['Cod. cable'] == cod_cable) & (df['De Elemento Etiquetas'] == elemento)
                nc = int(len(df[mask]))
                desc, sec, lon, det = _get_cols_r(row_data)
                grupos_generados.append({
                    'numero_etiqueta': numero_etiqueta, 'sub_numero': sub_idx, 'es_grupo_padre': 0,
                    'grupo_serie': serie_code, 'cod_cable': cod_cable, 'elemento': elemento,
                    'descripcion': desc, 'seccion': sec, 'longitud': lon, 'de_terminal': det,
                    'num_cables': nc, 'num_terminales': nc, 'archivo': archivo, 'codigo_corte': codigo_corte
                })
            numero_etiqueta += 1

        # Individuales
        for cod_cable, elemento, row_data in individuales_r:
            mask = (df['Cod. cable'] == cod_cable) & (df['De Elemento Etiquetas'] == elemento)
            nc = int(len(df[mask]))
            desc, sec, lon, det = _get_cols_r(row_data)
            grupos_generados.append({
                'numero_etiqueta': numero_etiqueta, 'sub_numero': 0, 'es_grupo_padre': 0,
                'grupo_serie': None, 'cod_cable': cod_cable, 'elemento': elemento,
                'descripcion': desc, 'seccion': sec, 'longitud': lon, 'de_terminal': det,
                'num_cables': nc, 'num_terminales': nc, 'archivo': archivo, 'codigo_corte': codigo_corte
            })
            numero_etiqueta += 1

        # Guardar
        query_ins = """
            INSERT INTO etiquetas_elementos
            (archivo_excel, codigo_corte, numero_etiqueta, sub_numero, es_grupo_padre,
             grupo_serie, cod_cable, elemento, descripcion, seccion, longitud,
             de_terminal, num_cables, num_terminales)
            VALUES (:archivo, :codigo_corte, :numero, :sub_numero, :es_grupo_padre,
                    :grupo_serie, :cod_cable, :elemento, :descripcion, :seccion, :longitud,
                    :de_terminal, :num_cables, :num_terminales)
        """
        with db.engine.connect() as conn:
            for g in grupos_generados:
                conn.execute(text(query_ins), {
                    'archivo': g['archivo'], 'codigo_corte': g['codigo_corte'],
                    'numero': g['numero_etiqueta'], 'sub_numero': g['sub_numero'],
                    'es_grupo_padre': g['es_grupo_padre'], 'grupo_serie': g['grupo_serie'],
                    'cod_cable': g['cod_cable'], 'elemento': g['elemento'],
                    'descripcion': g['descripcion'], 'seccion': g['seccion'],
                    'longitud': g['longitud'], 'de_terminal': g['de_terminal'],
                    'num_cables': g['num_cables'], 'num_terminales': g['num_terminales']
                })
            conn.commit()

        print(f"✅ {len(grupos_generados)} etiquetas regeneradas para {archivo}")
        return jsonify({'success': True, 'total': len(grupos_generados), 'archivo': archivo})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return error_interno(e, 'Error al regenerar')


def _regenerar_etiquetas_archivo(archivo: str, excel_path: str) -> int:
    """
    Borra las etiquetas existentes de 'archivo' y las regenera desde el Excel.
    Devuelve el número de etiquetas generadas.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f'Archivo no encontrado: {excel_path}')

    # 1. Borrar las existentes
    with db.engine.connect() as conn:
        deleted = conn.execute(
            text("DELETE FROM etiquetas_elementos WHERE archivo_excel = :a"), {'a': archivo}
        ).rowcount
        conn.commit()
    print(f"🗑️  Etiquetas eliminadas para {archivo}: {deleted} filas")

    # 2. Leer Excel y regenerar
    df = pd.read_excel(excel_path, sheet_name=_detectar_hoja(excel_path))

    if 'Cod. cable' not in df.columns or 'De Elemento Etiquetas' not in df.columns:
        raise ValueError('El archivo no tiene las columnas requeridas (Cod. cable, De Elemento Etiquetas)')

    # Filtrar filas auxiliares (sin Cod. cable o sin Sección) — misma lógica que agrupar_por_cable_elemento
    _sec_col = 'Sección' if 'Sección' in df.columns else ('Seccion' if 'Seccion' in df.columns else None)
    _mask_validas = df['Cod. cable'].notna() & (df['Cod. cable'].astype(str).str.strip() != '')
    if _sec_col:
        _mask_validas &= df[_sec_col].notna() & (df[_sec_col].astype(str).str.strip() != '')
    df = df[_mask_validas].copy()

    grupos_generados = []
    numero_etiqueta = 1
    codigo_corte = archivo.replace('.xlsx', '').replace('.xls', '')

    # Agrupar ordenado alfabéticamente por Cod. cable + elemento (orden del corte)
    agrupados = df.groupby(['Cod. cable', 'De Elemento Etiquetas']).first().reset_index()

    SERIE_PAT_R = re.compile(r'\((\w+)\)$')
    series_dict_r = {}
    series_orden_r = []   # para mantener el orden de primera aparición de cada serie
    individuales_r = []

    for _, row in agrupados.iterrows():
        cod_cable = str(row['Cod. cable'])
        elemento  = str(row['De Elemento Etiquetas']).strip()
        m = SERIE_PAT_R.search(elemento)
        if m:
            sc = m.group(1)
            if sc not in series_dict_r:
                series_dict_r[sc] = []
                series_orden_r.append(sc)
            series_dict_r[sc].append((cod_cable, elemento, row))
        else:
            individuales_r.append((cod_cable, elemento, row))

    def _get_cols_r(row_data):
        desc = str(row_data.get('Descripción Cable', row_data.get('Descripción', '')))
        sec  = str(row_data.get('Sección', row_data.get('Seccion', '')))
        try:
            lon = float(row_data.get('Longitud', 0) or 0)
        except (ValueError, TypeError):
            lon = 0.0
        det = str(row_data.get('De Terminal', ''))
        return desc, sec, lon, det

    # Series (en orden de primera aparición en el groupby)
    for serie_code in series_orden_r:
        miembros = series_dict_r[serie_code]
        total_cables = total_terminales = 0
        primer_det = primer_desc = primer_sec = ''
        for cod_cable, elemento, row_data in miembros:
            mask = (df['Cod. cable'] == cod_cable) & (df['De Elemento Etiquetas'] == elemento)
            nc = int(len(df[mask]))
            total_cables += nc
            total_terminales += nc
            desc, sec, _, det = _get_cols_r(row_data)
            if not primer_det:  primer_det  = det
            if not primer_desc: primer_desc = desc
            if not primer_sec:  primer_sec  = sec

        grupos_generados.append({
            'numero_etiqueta': numero_etiqueta, 'sub_numero': 0, 'es_grupo_padre': 1,
            'grupo_serie': serie_code, 'cod_cable': 'GRUPO_SERIE', 'elemento': serie_code,
            'descripcion': f'Grupo serie {serie_code}', 'seccion': primer_sec,
            'longitud': 0.0, 'de_terminal': primer_det, 'num_cables': total_cables,
            'num_terminales': total_terminales, 'archivo': archivo, 'codigo_corte': codigo_corte
        })
        for sub_idx, (cod_cable, elemento, row_data) in enumerate(miembros, 1):
            mask = (df['Cod. cable'] == cod_cable) & (df['De Elemento Etiquetas'] == elemento)
            nc = int(len(df[mask]))
            desc, sec, lon, det = _get_cols_r(row_data)
            grupos_generados.append({
                'numero_etiqueta': numero_etiqueta, 'sub_numero': sub_idx, 'es_grupo_padre': 0,
                'grupo_serie': serie_code, 'cod_cable': cod_cable, 'elemento': elemento,
                'descripcion': desc, 'seccion': sec, 'longitud': lon, 'de_terminal': det,
                'num_cables': nc, 'num_terminales': nc, 'archivo': archivo, 'codigo_corte': codigo_corte
            })
        numero_etiqueta += 1

    # Individuales
    for cod_cable, elemento, row_data in individuales_r:
        mask = (df['Cod. cable'] == cod_cable) & (df['De Elemento Etiquetas'] == elemento)
        nc = int(len(df[mask]))
        desc, sec, lon, det = _get_cols_r(row_data)
        grupos_generados.append({
            'numero_etiqueta': numero_etiqueta, 'sub_numero': 0, 'es_grupo_padre': 0,
            'grupo_serie': None, 'cod_cable': cod_cable, 'elemento': elemento,
            'descripcion': desc, 'seccion': sec, 'longitud': lon, 'de_terminal': det,
            'num_cables': nc, 'num_terminales': nc, 'archivo': archivo, 'codigo_corte': codigo_corte
        })
        numero_etiqueta += 1

    # 3. Guardar
    query_ins = """
        INSERT INTO etiquetas_elementos
        (archivo_excel, codigo_corte, numero_etiqueta, sub_numero, es_grupo_padre,
         grupo_serie, cod_cable, elemento, descripcion, seccion, longitud,
         de_terminal, num_cables, num_terminales)
        VALUES (:archivo, :codigo_corte, :numero, :sub_numero, :es_grupo_padre,
                :grupo_serie, :cod_cable, :elemento, :descripcion, :seccion, :longitud,
                :de_terminal, :num_cables, :num_terminales)
    """
    with db.engine.connect() as conn:
        for g in grupos_generados:
            conn.execute(text(query_ins), {
                'archivo': g['archivo'], 'codigo_corte': g['codigo_corte'],
                'numero': g['numero_etiqueta'], 'sub_numero': g['sub_numero'],
                'es_grupo_padre': g['es_grupo_padre'], 'grupo_serie': g['grupo_serie'],
                'cod_cable': g['cod_cable'], 'elemento': g['elemento'],
                'descripcion': g['descripcion'], 'seccion': g['seccion'],
                'longitud': g['longitud'], 'de_terminal': g['de_terminal'],
                'num_cables': g['num_cables'], 'num_terminales': g['num_terminales']
            })
        conn.commit()

    print(f"✅ {len(grupos_generados)} etiquetas regeneradas para {archivo}")
    return len(grupos_generados)


@bp.route('/api/etiquetas/buscar_por_numero', methods=['POST'])
def api_etiquetas_buscar_por_numero():
    """Buscar grupo por número de etiqueta"""
    try:
        data = request.get_json()
        numero_etiqueta = data.get('numero_etiqueta')
        
        if not numero_etiqueta:
            return jsonify({
                'success': False,
                'message': 'Número de etiqueta requerido'
            })
        
        # Buscar en base de datos
        query = """
            SELECT 
                numero_etiqueta,
                cod_cable,
                elemento,
                descripcion,
                seccion,
                longitud,
                de_terminal,
                num_cables,
                num_terminales
            FROM etiquetas_elementos
            WHERE numero_etiqueta = :numero
            LIMIT 1
        """
        
        with db.engine.connect() as conn:
            resultado = conn.execute(text(query), {'numero': numero_etiqueta}).fetchone()
        
        if not resultado:
            return jsonify({
                'success': False,
                'message': f'No se encontró etiqueta #{numero_etiqueta}'
            })
        
        grupo = {
            'numero_etiqueta': resultado[0],
            'cod_cable': resultado[1],
            'elemento': resultado[2],
            'descripcion': resultado[3],
            'seccion': resultado[4],
            'longitud': resultado[5],
            'de_terminal': resultado[6],
            'num_cables': resultado[7],
            'num_terminales': resultado[8]
        }
        
        return jsonify({
            'success': True,
            'grupo': grupo
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al buscar etiqueta: {str(e)}'
        })


# ==================== API DE PROGRESO ====================

@bp.route('/api/bonos/<nombre_bono>/progreso', methods=['GET'])
def api_bonos_progreso_get(nombre_bono):
    """Obtener progreso guardado de un bono"""
    try:
        progreso_path = os.path.join(current_app.config['DATA_DIR'], f'progreso_bono_{nombre_bono}.json')
        
        if not os.path.exists(progreso_path):
            return jsonify({
                'success': True,
                'progreso': {}
            })
        
        with open(progreso_path, 'r', encoding='utf-8') as f:
            progreso = json.load(f)
        
        return jsonify({
            'success': True,
            'progreso': progreso
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al cargar progreso: {str(e)}'
        })


@bp.route('/api/bonos/<nombre_bono>/terminales-disponibles', methods=['GET'])
def api_bonos_terminales_disponibles(nombre_bono):
    """Obtener terminales que tienen datos en los archivos del bono"""
    try:
        # Obtener bono
        bono_repo = BonoRepository(db)
        bono = bono_repo.obtener_bono_por_nombre(nombre_bono)
        
        if not bono:
            return jsonify({'success': False, 'message': 'Bono no encontrado'})
        
        # Obtener órdenes del bono
        orden_repo = OrdenRepository(db)
        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])
        
        terminales_con_datos = set()
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        # Para cada orden, obtener el archivo y extraer terminales
        archivos_procesados = set()
        for orden in ordenes:
            archivo = orden.get('archivo_excel')
            if not archivo or archivo in archivos_procesados:
                continue
            
            archivos_procesados.add(archivo)
            filepath = os.path.join(upload_folder, archivo)
            
            if not os.path.exists(filepath):
                continue
            
            try:
                # Cargar Excel
                df = pd.read_excel(filepath, sheet_name=_detectar_hoja(filepath))

                def _terminal_valido(val):
                    t = str(val).strip().upper()
                    return t and t != 'S/T' and t != 'NAN'

                # Extraer terminales SOLO si realmente se engastan en ese lado.
                # Si el elemento de ese lado termina en '*', el terminal NO se engasta
                # ahí, por lo que NO debe ofrecerse como terminal seleccionable.
                tiene_de   = 'De Terminal' in df.columns
                tiene_para = 'Para Terminal' in df.columns
                for _, fila in df.iterrows():
                    if tiene_de:
                        de_term = fila.get('De Terminal', '')
                        de_no_poner = str(fila.get('De Elemento', '')).strip().endswith('*')
                        if _terminal_valido(de_term) and not de_no_poner:
                            terminales_con_datos.add(str(de_term).strip().upper())
                    if tiene_para:
                        para_term = fila.get('Para Terminal', '')
                        para_no_poner = str(fila.get('Para Elemento', '')).strip().endswith('*')
                        if _terminal_valido(para_term) and not para_no_poner:
                            terminales_con_datos.add(str(para_term).strip().upper())
            
            except Exception as e:
                print(f"Error procesando archivo {archivo}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'terminales': sorted(list(terminales_con_datos))
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})


@bp.route('/api/bonos/<nombre_bono>/progreso', methods=['POST'])
def api_bonos_progreso_post(nombre_bono):
    """Guardar progreso de un terminal/carro en un bono"""
    try:
        data = request.get_json()
        terminal = data.get('terminal')
        carro = data.get('carro')
        terminales_proyecto = data.get('terminales_proyecto', [])
        operario = (data.get('operario') or '').strip()

        if not terminal or not (carro or isinstance(carro, int)):
            return jsonify({
                'success': False,
                'message': 'Se requiere terminal y carro'
            })
        
        # Cargar progreso existente
        progreso_path = os.path.join(current_app.config['DATA_DIR'], f'progreso_bono_{nombre_bono}.json')
        
        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)
        else:
            progreso = {}
        
        # Inicializar estructura para este terminal si no existe
        if terminal not in progreso:
            progreso[terminal] = {
                'estado': 'en_proceso',
                'carros_completados': [],
                'fecha_inicio': _ahora_iso(),
                'fecha_ultima_actualizacion': _ahora_iso()
            }

        # Guardar operario si se envió
        if operario:
            progreso[terminal]['operario'] = operario

        # Agregar carro a completados si no está ya
        if carro not in progreso[terminal]['carros_completados']:
            progreso[terminal]['carros_completados'].append(carro)

        # Limpiar de carros_con_pendientes si estaba anotado ahí
        carros_pend = progreso[terminal].get('carros_con_pendientes', {})
        carros_pend.pop(str(carro), None)
        progreso[terminal]['carros_con_pendientes'] = carros_pend
        
        # Actualizar fecha
        progreso[terminal]['fecha_ultima_actualizacion'] = _ahora_iso()
        
        # Marcar como completado si ya no hay más carros pendientes
        # Nota: necesitaríamos saber el total de carros del bono, por ahora solo marcamos como en_proceso
        
        # Guardar progreso
        with open(progreso_path, 'w', encoding='utf-8') as f:
            json.dump(progreso, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            'success': True,
            'message': f'Progreso guardado para terminal {terminal}, carro {carro}',
            'progreso_actual': progreso[terminal]
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al guardar progreso: {str(e)}'
        })

@bp.route('/api/bonos/<nombre_bono>/progreso/parcial', methods=['POST'])
def api_bonos_progreso_parcial(nombre_bono):
    """Guardar progreso parcial de un carro (cancelado a mitad, con paquetes saltados)"""
    try:
        data = request.get_json()
        terminal = data.get('terminal')
        carro = data.get('carro')
        paquetes_saltados = data.get('paquetes_saltados', [])
        paquetes_hechos = data.get('paquetes_hechos', 0)
        operario = (data.get('operario') or '').strip()

        if not terminal:
            return jsonify({'success': False, 'message': 'Se requiere terminal'})

        progreso_path = os.path.join(current_app.config['DATA_DIR'], f'progreso_bono_{nombre_bono}.json')

        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)
        else:
            progreso = {}

        if terminal not in progreso:
            progreso[terminal] = {
                'estado': 'en_proceso',
                'carros_completados': [],
                'fecha_inicio': _ahora_iso(),
                'fecha_ultima_actualizacion': _ahora_iso()
            }

        # Guardar operario si se envió
        if operario:
            progreso[terminal]['operario'] = operario

        # Guardar paquetes saltados por carro
        if 'paquetes_saltados_por_carro' not in progreso[terminal]:
            progreso[terminal]['paquetes_saltados_por_carro'] = {}

        carro_key = str(carro) if carro is not None else 'sin_carro'

        paquetes_pendientes = data.get('paquetes_pendientes', paquetes_saltados)  # alias

        if paquetes_pendientes:
            # Hay paquetes pendientes: guardar en carros_con_pendientes (carro NO completado)
            if 'carros_con_pendientes' not in progreso[terminal]:
                progreso[terminal]['carros_con_pendientes'] = {}
            progreso[terminal]['carros_con_pendientes'][carro_key] = {
                'paquetes': paquetes_pendientes,
                'fecha': _ahora_iso()
            }
        else:
            # Sin pendientes: marcar como completado y limpiar cualquier entrada previa
            if 'carros_con_pendientes' in progreso[terminal]:
                progreso[terminal]['carros_con_pendientes'].pop(carro_key, None)
            if carro is not None and carro not in progreso[terminal]['carros_completados']:
                progreso[terminal]['carros_completados'].append(carro)

        progreso[terminal]['paquetes_saltados_por_carro'][carro_key] = {
            'paquetes_hechos': paquetes_hechos,
            'saltados': paquetes_saltados,
            'fecha': _ahora_iso()
        }
        progreso[terminal]['fecha_ultima_actualizacion'] = _ahora_iso()

        with open(progreso_path, 'w', encoding='utf-8') as f:
            json.dump(progreso, f, indent=2, ensure_ascii=False)

        return jsonify({
            'success': True,
            'message': f'{paquetes_hechos} paquetes hechos, {len(paquetes_saltados)} saltados guardados para carro {carro}'
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})


@bp.route('/api/bonos/<nombre_bono>/progreso/estado', methods=['POST'])
def api_bonos_progreso_estado(nombre_bono):
    """Actualizar solo el estado de un terminal (en_proceso / completado)"""
    try:
        data = request.get_json()
        terminal = data.get('terminal')
        estado = data.get('estado')  # 'en_proceso' o 'completado'
        operario = (data.get('operario') or '').strip()

        if not terminal or estado not in ('en_proceso', 'completado'):
            return jsonify({'success': False, 'message': 'Parámetros inválidos'})

        progreso_path = os.path.join(current_app.config['DATA_DIR'], f'progreso_bono_{nombre_bono}.json')

        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)
        else:
            progreso = {}

        if terminal not in progreso:
            progreso[terminal] = {
                'estado': estado,
                'carros_completados': [],
                'fecha_inicio': _ahora_iso(),
                'fecha_ultima_actualizacion': _ahora_iso()
            }
        else:
            progreso[terminal]['estado'] = estado
            progreso[terminal]['fecha_ultima_actualizacion'] = _ahora_iso()

        if operario:
            progreso[terminal]['operario'] = operario

        with open(progreso_path, 'w', encoding='utf-8') as f:
            json.dump(progreso, f, indent=2, ensure_ascii=False)

        return jsonify({'success': True, 'terminal': terminal, 'estado': estado})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@bp.route('/api/bonos/<nombre_bono>/progreso-por-carro', methods=['GET'])
def api_bonos_progreso_por_carro(nombre_bono):
    """Progreso agrupado por carro: {carro_id: {terminales_completados: [...]}}"""
    try:
        progreso_path = os.path.join(current_app.config['DATA_DIR'], f'progreso_bono_{nombre_bono}.json')
        progreso = {}
        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)

        por_carro = {}
        for terminal, data in progreso.items():
            for carro in (data.get('carros_completados') or []):
                carro_key = str(carro)
                if carro_key not in por_carro:
                    por_carro[carro_key] = {'terminales_completados': []}
                por_carro[carro_key]['terminales_completados'].append(terminal)

        return jsonify({'success': True, 'progreso_por_carro': por_carro})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


def _crimps_por_terminal_archivo(archivo: str) -> dict:
    """
    Calcula el nº de crimps (terminales a engastar) por terminal de un archivo Excel,
    usando EXACTAMENTE la misma lógica que la vista de engastado
    (excel_manager.agrupar_por_cable_elemento): cada lado sin '*' = 1 crimp; si el
    terminal está en ambos lados de la fila sin '*' = 2 crimps. Los lados con '*'
    (terminal no se engasta) o terminales vacíos/'S/T' no cuentan.

    Devuelve {TERMINAL_UPPER: num_crimps}. Esto refleja el trabajo REAL del operario,
    a diferencia del antiguo cálculo que solo miraba 'De Terminal' y descartaba los
    grupos cuyo terminal estaba en el lado 'Para' (de_terminal vacío/S/T).
    """
    upload_folder = current_app.config['UPLOAD_FOLDER']
    mgr = ExcelManager(upload_folder)
    if not mgr.cargar_excel_directo(archivo):
        return {}
    df = mgr.current_df
    if df is None:
        return {}

    def _valido(t):
        return t and t not in ('NAN', 'S/T', '')

    cont = {}
    for _, row in df.iterrows():
        # Ignorar filas auxiliares (sin Cod. cable o sin Sección) — igual que el engastado
        cod = str(row.get('Cod. cable', '')).strip()
        if cod == '' or cod.lower() == 'nan':
            continue
        sec_raw = row.get('Sección', row.get('Seccion', ''))
        sec = str(sec_raw).strip()
        if sec == '' or sec.lower() == 'nan':
            continue

        de_t   = str(row.get('De Terminal', '')).strip().upper()
        para_t = str(row.get('Para Terminal', '')).strip().upper()
        de_np   = str(row.get('De Elemento', '')).strip().endswith('*')
        para_np = str(row.get('Para Elemento', '')).strip().endswith('*')

        tiene_o = _valido(de_t)
        tiene_d = _valido(para_t)

        if tiene_o and tiene_d and de_t == para_t:
            # Terminal en ambos lados de la misma fila
            if de_np and para_np:
                pass
            elif de_np or para_np:
                cont[de_t] = cont.get(de_t, 0) + 1
            else:
                cont[de_t] = cont.get(de_t, 0) + 2
        else:
            if tiene_o and not de_np:
                cont[de_t] = cont.get(de_t, 0) + 1
            if tiene_d and not para_np:
                cont[para_t] = cont.get(para_t, 0) + 1

    return cont


@bp.route('/api/bonos/<nombre_bono>/progreso-ponderado', methods=['GET'])
def api_bonos_progreso_ponderado(nombre_bono):
    """
    Progreso ponderado del bono usando num_terminales como peso.
    Devuelve:
      - peso_total_bono, peso_completado_bono, porcentaje_bono
      - terminales: lista con peso_total, peso_completado, porcentaje, estado por terminal
      - progreso_por_carro: {carro_id: {peso_total, peso_completado, porcentaje, terminales_completados}}
    """
    try:
        bono_repo = BonoRepository(db)
        orden_repo = OrdenRepository(db)

        bono = bono_repo.obtener_bono_por_nombre(nombre_bono)
        if not bono:
            return jsonify({'success': False, 'message': 'Bono no encontrado'})

        ordenes = orden_repo.obtener_ordenes_por_bono(bono['id'])

        # Construir pesos: {terminal: {str(carro_numero): peso_acumulado}}
        pesos_terminal_carro = {}
        _cache_crimps = {}  # archivo -> {terminal: num_crimps}

        for idx, orden in enumerate(ordenes):
            archivo = orden.get('archivo_excel')
            if not archivo:
                continue
            # IMPORTANTE: el carro se numera por POSICIÓN (idx+1), igual que el
            # frontend de engastado (carrosDelBono = ordenes.map((o, idx) => carro: idx+1)).
            # No usar carro_numero de la BD: puede no coincidir con el orden posicional
            # y provoca que carros_completados nunca cuadre con los pesos (progreso a 0).
            carro_key = str(idx + 1)

            # Crimps por terminal con la MISMA lógica que ve el operario (De+Para, sin '*')
            if archivo not in _cache_crimps:
                _cache_crimps[archivo] = _crimps_por_terminal_archivo(archivo)

            for terminal, peso in _cache_crimps[archivo].items():
                if not terminal:
                    continue
                if terminal not in pesos_terminal_carro:
                    pesos_terminal_carro[terminal] = {}
                pesos_terminal_carro[terminal][carro_key] = (
                    pesos_terminal_carro[terminal].get(carro_key, 0) + int(peso or 0)
                )

        # Leer progreso guardado
        progreso_path = os.path.join(current_app.config['DATA_DIR'], f'progreso_bono_{nombre_bono}.json')
        progreso = {}
        if os.path.exists(progreso_path):
            with open(progreso_path, 'r', encoding='utf-8') as f:
                progreso = json.load(f)

        # Calcular métricas por terminal
        resumen_terminales = []
        peso_total_bono = 0
        peso_completado_bono = 0

        for terminal, pesos_por_carro in sorted(pesos_terminal_carro.items()):
            peso_total_terminal = sum(pesos_por_carro.values())
            prog_t = progreso.get(terminal, {})
            carros_completados = [str(c) for c in (prog_t.get('carros_completados') or [])]
            tiene_pendientes = bool(prog_t.get('carros_con_pendientes'))
            estado_guardado = prog_t.get('estado')

            peso_completado_terminal = sum(
                pesos_por_carro.get(carro_id, 0) for carro_id in carros_completados
            )
            # Red de seguridad: si el operario marcó el terminal como 'completado',
            # contar todo su peso aunque el mapeo de carros no cuadre perfectamente.
            if estado_guardado == 'completado':
                peso_completado_terminal = peso_total_terminal

            peso_total_bono += peso_total_terminal
            peso_completado_bono += peso_completado_terminal

            if peso_total_terminal > 0 and peso_completado_terminal >= peso_total_terminal:
                estado = 'completado'
            elif peso_completado_terminal > 0 or tiene_pendientes:
                estado = 'en_proceso'
            else:
                estado = 'pendiente'

            resumen_terminales.append({
                'terminal': terminal,
                'peso_total': peso_total_terminal,
                'peso_completado': peso_completado_terminal,
                'porcentaje': round(peso_completado_terminal / peso_total_terminal * 100, 1) if peso_total_terminal > 0 else 0,
                'estado': estado,
                'carros_completados': carros_completados,
                'tiene_pendientes': tiene_pendientes,
                'pesos_por_carro': pesos_por_carro
            })

        porcentaje_bono = round(peso_completado_bono / peso_total_bono * 100, 1) if peso_total_bono > 0 else 0

        # Calcular progreso ponderado por carro
        # Usar las claves de pesos_terminal_carro (ya incluye fallback sintético idx+1)
        carros_unicos = set()
        for pesos in pesos_terminal_carro.values():
            carros_unicos.update(pesos.keys())
        carros_data = {}
        for carro_key in sorted(carros_unicos):
            peso_carro_total = sum(pesos.get(carro_key, 0) for pesos in pesos_terminal_carro.values())
            peso_carro_completado = 0
            terminales_completados = []
            for terminal, pesos in pesos_terminal_carro.items():
                prog_t = progreso.get(terminal, {})
                ccs = [str(c) for c in (prog_t.get('carros_completados') or [])]
                # Cuenta el carro como hecho si está en carros_completados, o si el
                # terminal entero está marcado como 'completado' (red de seguridad).
                if carro_key in ccs or prog_t.get('estado') == 'completado':
                    peso_carro_completado += pesos.get(carro_key, 0)
                    if terminal not in terminales_completados:
                        terminales_completados.append(terminal)
            carros_data[carro_key] = {
                'peso_total': peso_carro_total,
                'peso_completado': peso_carro_completado,
                'porcentaje': round(peso_carro_completado / peso_carro_total * 100, 1) if peso_carro_total > 0 else 0,
                'terminales_completados': terminales_completados
            }

        return jsonify({
            'success': True,
            'peso_total_bono': peso_total_bono,
            'peso_completado_bono': peso_completado_bono,
            'porcentaje_bono': porcentaje_bono,
            'terminales': resumen_terminales,
            'progreso_por_carro': carros_data
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})


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
    if not expected or token != expected:
        return jsonify({'success': False, 'error': 'unauthorized', 'path_checked': os.path.join(os.path.dirname(current_app.root_path), '.deploy_token')}), 401

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
        return jsonify({'success': False, 'error': str(e)}), 500