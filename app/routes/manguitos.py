"""
Guiado de manguitos y preparación de mangueras (páginas y APIs).
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
from app.excel_manager import ExcelManager, leer_excel_cacheado, _serie_str
from app.colisiones_etiquetas import detectar_colisiones, etiqueta_texto
from app.auth import (
    requiere_pin_admin,
    requiere_modulo,
    pc_dedicado_a,
    proteccion_activa,
    sesion_admin_valida,
    marcar_sesion_admin,
    cerrar_sesion_admin,
)
from app.routes.base import (
    bp, db, error_interno, allowed_file, _ruta_upload_segura,
    _ahora_iso, _detectar_hoja, _es_error_nombre_bono_duplicado,
)


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


def _buscador_etiquetas(archivo):
    """Devuelve buscar(manguito, elemento) -> 'N' o 'N.SS' (o None).

    Una etiqueta se identifica por (cable, elemento, serie): el mismo
    elemento con el mismo cable puede estar en una serie (1.01) y suelto (24).
    Enlazar solo por (cable, elemento) dejaba el manguito en la última
    etiqueta leída y la serie entera desaparecía de la pantalla.
    """
    por_serie = {}   # (cod, elemento, serie) -> label
    por_cable = {}   # (cod, elemento) -> label (primer match)
    por_elem = {}    # elemento -> label (primer match)
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                """SELECT elemento, numero_etiqueta, sub_numero, cod_cable, grupo_serie
                   FROM etiquetas_elementos
                   WHERE archivo_excel = :arch AND (es_grupo_padre = 0 OR COALESCE(es_padre_manual,0) = 1)
                   ORDER BY numero_etiqueta, sub_numero"""
            ), {'arch': archivo}).fetchall()
    except Exception:
        rows = []
    for elem, num_etq, sub_num, cod, serie in rows:
        cod = (cod or '').strip().upper()
        serie = (serie or '').strip()
        label = f"{num_etq}.{str(int(sub_num)).zfill(2)}" if sub_num and int(sub_num) > 0 else str(num_etq)
        por_serie.setdefault((cod, elem, serie), label)
        por_cable.setdefault((cod, elem), label)
        por_elem.setdefault(elem, label)

    def buscar(mg, elemento):
        cod = (mg.get('cod_cable') or '').strip().upper()
        serie = (mg.get('serie') or '').strip()
        return (por_serie.get((cod, elemento, serie))
                or por_cable.get((cod, elemento))
                or por_elem.get(elemento))
    return buscar


@bp.route('/manguitos')
@requiere_modulo('manguitos')
def manguitos():
    """Guiado de colocación y pedidos de manguitos.

    No tiene puestos: el PC entero se dedica a este módulo (ver
    app/routes/puestos.py:_pc_identidad). puesto_id/nombre van igualmente a
    la plantilla porque un PC de engastado también puede abrir esta página
    desde /modules si tiene el módulo permitido.
    """
    from app.routes.puestos import _pc_identidad
    _, puesto_id, puesto_nombre = _pc_identidad()
    return render_template('manguitos.html', puesto_id=puesto_id,
                           puesto_nombre=puesto_nombre,
                           pc_dedicado=pc_dedicado_a('manguitos'))


@bp.route('/mangueras')
@requiere_modulo('mangueras')
def mangueras():
    """Preparación de mangueras. Sin puestos, igual que manguitos."""
    from app.routes.puestos import _pc_identidad
    _, puesto_id, puesto_nombre = _pc_identidad()
    return render_template('mangueras.html', puesto_id=puesto_id,
                           puesto_nombre=puesto_nombre,
                           pc_dedicado=pc_dedicado_a('mangueras'))


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
                       WHERE archivo_excel = :arch AND (es_grupo_padre = 0 OR COALESCE(es_padre_manual,0) = 1)"""
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
        return error_interno(e)


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
            buscar = _buscador_etiquetas(archivo)
            for elem in resultado:
                for mg in elem.get('manguitos', []):
                    mg['numero_etiqueta'] = buscar(mg, elem['elemento'])

            # Reagrupar por etiqueta (paquete): cada paquete corresponde a un único
            # cable/etiqueta. Agrupar por 'De Elemento' mezclaba manguitos de etiquetas
            # distintas que comparten el mismo elemento de destino.
            grupos = {}
            orden  = []
            for elem in resultado:
                for mg in elem.get('manguitos', []):
                    label = mg.get('numero_etiqueta')
                    key   = label if label else ('__sin_etq__', elem['elemento'])
                    if key not in grupos:
                        grupos[key] = {
                            'elemento':        elem['elemento'],
                            'manguitos':       [],
                            'numero_etiqueta': label,
                        }
                        orden.append(key)
                    grupos[key]['manguitos'].append(mg)
            resultado = [grupos[k] for k in orden]

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
        return error_interno(e)


@bp.route('/api/manguitos/reetiquetado', methods=['POST'])
def api_manguitos_reetiquetado():
    """Paquetes que la máquina de corte ha juntado y hay que repartir.

    Devuelve, por cada (cable, elemento) repetido en varias etiquetas, qué
    cables se quedan con la etiqueta principal y cuáles hay que pasar a cada
    etiqueta de reserva. Los cables se distinguen por marca y longitud; si en
    la principal hay otros iguales, da lo mismo cuál se mueve.
    """
    data = request.get_json() or {}
    archivo = data.get('archivo', '').strip()
    if not archivo:
        return jsonify({'success': False, 'error': 'Archivo no especificado'})
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(text(
                """SELECT numero_etiqueta, sub_numero, cod_cable, elemento, grupo_serie, num_cables
                   FROM etiquetas_elementos WHERE archivo_excel = :arch
                   ORDER BY numero_etiqueta, sub_numero"""
            ), {'arch': archivo}).fetchall()
        etiquetas = [dict(zip(('numero_etiqueta', 'sub_numero', 'cod_cable', 'elemento',
                               'grupo_serie', 'num_cables'), r)) for r in rows]
        colisiones = detectar_colisiones(etiquetas)
        if not colisiones:
            return jsonify({'success': True, 'colisiones': []})

        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'data/cortes')
        filepath = ExcelManager(upload_folder)._ruta_segura(archivo)
        if not filepath or not os.path.exists(filepath):
            raise FileNotFoundError(f'Archivo no encontrado: {archivo}')
        df = leer_excel_cacheado(filepath)

        col_marca = next((c for c in ('Cable / Marca', 'De Marca') if c in df.columns), None)
        df = df[df['Cod. cable'].notna() & (df['Cod. cable'].astype(str).str.strip() != '')]
        series = df['Series'].apply(_serie_str) if 'Series' in df.columns else pd.Series('', index=df.index)
        cods = df['Cod. cable'].astype(str).str.strip().str.upper()
        elems = df['De Elemento Etiquetas'].astype(str).str.strip()

        def _cables(cod, elem, serie):
            sub = df[(cods == cod) & (elems == elem) & (series == serie)]
            cuenta = {}
            for _, r in sub.iterrows():
                marca = _serie_str(r[col_marca]) if col_marca else ''
                try:
                    lon = round(float(r['Longitud']), 3)
                except (KeyError, TypeError, ValueError):
                    lon = None
                cuenta[(marca, lon)] = cuenta.get((marca, lon), 0) + 1
            return cuenta

        def _ficha(e, cod, elem):
            cuenta = _cables(cod, elem, (e.get('grupo_serie') or '').strip())
            return {'etiqueta': etiqueta_texto(e['numero_etiqueta'], e['sub_numero']),
                    'num_cables': e['num_cables'], 'cuenta': cuenta}

        salida = []
        for c in colisiones:
            cod, elem = c['cod_cable'], c['elemento']
            principal = _ficha(c['principal'], cod, elem)
            reservas = []
            for r in c['reservas']:
                f = _ficha(r, cod, elem)
                cables = [{'marca': m, 'longitud': l, 'cantidad': n,
                           'igual_en_principal': (m, l) in principal['cuenta']}
                          for (m, l), n in sorted(f['cuenta'].items(), key=lambda kv: (str(kv[0][0]), kv[0][1] or 0))]
                reservas.append({'etiqueta': f['etiqueta'], 'num_cables': f['num_cables'], 'cables': cables})
            salida.append({'cod_cable': cod, 'elemento': elem,
                           'principal': {'etiqueta': principal['etiqueta'], 'num_cables': principal['num_cables']},
                           'reservas': reservas})
        return jsonify({'success': True, 'colisiones': salida})
    except Exception as e:
        return error_interno(e)


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

        # Obtener numero_etiqueta formateado por (cod_cable, elemento) desde BD
        buscar = _buscador_etiquetas(archivo)

        # Aplanar: lista de manguitos con su numero de etiqueta (por cable) para ordenar
        lista_plana = []
        for elem in elementos:
            for m in elem['manguitos']:
                num_str = buscar(m, elem['elemento'])
                try:
                    num_float = float(num_str) if num_str else float('inf')
                except (ValueError, TypeError):
                    num_float = float('inf')
                lista_plana.append((num_float, m))

        # Ordenar por numero de etiqueta (sort estable preserva orden Excel dentro del mismo paquete)
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
        return error_interno(e, 'Error al generar TXT', clave='error')


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

    # secure_filename neutraliza separadores y '..': sin esto un nombre como
    # '../../../evil.xlsx' escaparia del directorio temporal al guardarlo.
    nombre_original = secure_filename(excel_file.filename)
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
        return error_interno(e, 'Error al generar TXT', clave='error')
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
