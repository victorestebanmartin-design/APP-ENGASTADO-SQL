"""
Etiquetas de elementos: generación, regeneración, HTML de impresión y búsqueda.
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
from app.excel_manager import ExcelManager, leer_excel_cacheado
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
from app.routes.cable_colores import _text_color_for_bg


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
        # El JS comprueba response.ok antes de leer el JSON; un 500 lo
        # trataría como fallo de red, por eso se mantiene el código 200.
        return error_interno(e, 'Error al cargar etiquetas', status=200)


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
            excel_path = _ruta_upload_segura(archivo)
            if not excel_path or not os.path.exists(excel_path):
                return jsonify({'success': False, 'message': f'Archivo no encontrado: {archivo}'})
            try:
                total = _regenerar_etiquetas_archivo(archivo, excel_path)
            except Exception as e:
                return error_interno(e, 'Error al generar etiquetas')
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
        return error_interno(e, 'Error al cargar grupos')


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
        # El JS comprueba response.ok antes de leer el JSON; un 500 lo
        # trataría como fallo de red, por eso se mantiene el código 200.
        return error_interno(e, 'Error al cargar etiquetas del bono', status=200)


@bp.route('/api/etiquetas/regenerar', methods=['POST'])
@requiere_pin_admin
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

        excel_path = _ruta_upload_segura(archivo)
        if not excel_path:
            return jsonify({'success': False, 'message': 'Nombre de archivo no válido'}), 400
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


def _regenerar_etiquetas_archivo(archivo: str, excel_path: str) -> int:
    """
    Borra las etiquetas existentes de 'archivo' y las regenera desde el Excel.
    Devuelve el número de etiquetas generadas.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f'Archivo no encontrado: {archivo}')

    # 1. Borrar las existentes
    with db.engine.connect() as conn:
        deleted = conn.execute(
            text("DELETE FROM etiquetas_elementos WHERE archivo_excel = :a"), {'a': archivo}
        ).rowcount
        conn.commit()
    print(f"🗑️  Etiquetas eliminadas para {archivo}: {deleted} filas")

    # 2. Leer Excel y regenerar
    df = leer_excel_cacheado(excel_path)

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

    # Para Series, tomar el primer valor no-nulo del grupo (first() puede coger NaN)
    if 'Series' in df.columns:
        _series_first = (
            df.groupby(['Cod. cable', 'De Elemento Etiquetas'])['Series']
            .apply(lambda x: next((v for v in x if not pd.isna(v)), None))
            .reset_index(name='_serie_val')
        )
        agrupados = agrupados.drop(columns=['Series'], errors='ignore').merge(
            _series_first, on=['Cod. cable', 'De Elemento Etiquetas'], how='left'
        )
        agrupados.rename(columns={'_serie_val': 'Series'}, inplace=True)

    _col_series_ok = 'Series' in agrupados.columns
    series_dict_r = {}
    series_orden_r = []   # para mantener el orden de primera aparición de cada serie
    individuales_r = []

    for _, row in agrupados.iterrows():
        cod_cable = str(row['Cod. cable'])
        elemento  = str(row['De Elemento Etiquetas']).strip()
        if _col_series_ok:
            _sv = row.get('Series', None)
            try:
                _sc_raw = '' if pd.isna(_sv) else str(_sv).strip()
            except Exception:
                _sc_raw = str(_sv).strip() if _sv else ''
            # Convertir floats enteros (1706.0 → '1706')
            if _sc_raw.endswith('.0'):
                try:
                    _sc_raw = str(int(float(_sc_raw)))
                except ValueError:
                    pass
            sc = '' if _sc_raw.lower() in ('nan', 'none', '') else _sc_raw
        else:
            sc = ''
        if sc:
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
        return error_interno(e, 'Error al buscar etiqueta')
