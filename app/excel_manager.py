"""
Gestor de archivos Excel para análisis de terminales y cables
"""
import pandas as pd
import os
import re
import threading
import unicodedata
from typing import List, Dict, Optional

# ─── Caché de DataFrames por archivo ──────────────────────────────────────────
# Parsear un Excel cuesta cientos de ms y se repetía en cada petición de cada
# operario. La caché se invalida sola cuando el fichero cambia en disco (mtime).
_EXCEL_CACHE = {}  # ruta_abs -> (mtime, hoja_usada, DataFrame)
_EXCEL_CACHE_LOCK = threading.Lock()
_EXCEL_CACHE_MAX = 16

_ALIASES_COLUMNAS_EXCEL = {
    'cod cable': 'Cod. cable',
    'de terminal': 'De Terminal',
    'para terminal': 'Para Terminal',
    'de elemento etiquetas': 'De Elemento Etiquetas',
    'seccion': 'Sección',
    'descripcion cable': 'Descripción Cable',
    'descripcion': 'Descripción',
}


def _normalizar_texto_columna(nombre: object) -> str:
    """Normaliza nombres de columnas para comparación tolerante."""
    if nombre is None:
        return ''
    texto = str(nombre).replace('\u00a0', ' ').strip().lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r'[._/\\-]+', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def normalizar_nombres_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas conocidas a un formato canonico esperado por la app.

    Soporta variaciones comunes en mayusculas/minusculas, acentos, puntos,
    guiones y espacios repetidos.
    """
    renombres = {}
    columnas_actuales = set(df.columns)
    canonicas_presentes = {c for c in columnas_actuales if c in _ALIASES_COLUMNAS_EXCEL.values()}

    for col in df.columns:
        normalizada = _normalizar_texto_columna(col)
        canonica = _ALIASES_COLUMNAS_EXCEL.get(normalizada)
        if not canonica:
            continue
        # Si la canónica ya existe, no sobreescribir ni crear duplicados.
        if canonica in canonicas_presentes and col != canonica:
            continue
        if col != canonica:
            renombres[col] = canonica
            canonicas_presentes.add(canonica)

    if not renombres:
        return df
    return df.rename(columns=renombres)


def leer_excel_cacheado(filepath: str, hoja_preferida: str = 'Format') -> pd.DataFrame:
    """DataFrame del Excel, cacheado por (ruta, mtime).

    Usa 'hoja_preferida' si existe en el archivo, sino la primera hoja.
    El DataFrame devuelto es COMPARTIDO entre peticiones: los consumidores
    no deben mutarlo (hacer .copy() antes de modificar).

    Lanza OSError si el fichero no existe.
    """
    ruta = os.path.abspath(filepath)
    mtime = os.path.getmtime(ruta)

    with _EXCEL_CACHE_LOCK:
        entrada = _EXCEL_CACHE.get(ruta)
        if entrada and entrada[0] == mtime:
            return entrada[2]

    xl = pd.ExcelFile(ruta)
    hoja = hoja_preferida if hoja_preferida in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(xl, sheet_name=hoja)
    df = normalizar_nombres_columnas(df)

    with _EXCEL_CACHE_LOCK:
        if len(_EXCEL_CACHE) >= _EXCEL_CACHE_MAX:
            # Descartar la entrada más antigua (orden de inserción de dict)
            _EXCEL_CACHE.pop(next(iter(_EXCEL_CACHE)))
        _EXCEL_CACHE[ruta] = (mtime, hoja, df)
    return df


class ExcelManager:
    """Maneja la lectura y procesamiento de archivos Excel de cortes"""
    
    def __init__(self, upload_folder: str):
        """
        Inicializar gestor de Excel
        
        Args:
            upload_folder: Ruta a la carpeta de uploads
        """
        self.upload_folder = upload_folder
        self.current_df = None
        self.current_filename = None

    def _ruta_segura(self, filename: str) -> Optional[str]:
        """Ruta absoluta dentro de upload_folder, o None si el nombre
        intenta salirse de la carpeta (path traversal)."""
        base = os.path.abspath(self.upload_folder)
        ruta = os.path.abspath(os.path.join(base, filename or ''))
        if os.path.commonpath([ruta, base]) != base:
            return None
        return ruta

    def cargar_excel_directo(self, filename: str, sheet_name: str = 'Format') -> bool:
        """
        Cargar archivo Excel directamente desde la carpeta de uploads
        
        Args:
            filename: Nombre del archivo Excel
            sheet_name: Nombre de la hoja a cargar
        
        Returns:
            True si se cargó correctamente, False en caso contrario
        """
        filepath = self._ruta_segura(filename)

        if not filepath or not os.path.exists(filepath):
            print(f"❌ Archivo no encontrado: {filename}")
            return False
        
        try:
            df = leer_excel_cacheado(filepath, hoja_preferida=sheet_name)

            # Verificar que tenga columnas básicas
            required_cols = ['Cod. cable', 'De Terminal', 'Para Terminal']
            missing = [col for col in required_cols if col not in df.columns]
            
            if missing:
                print(f"⚠️ Columnas faltantes en {filename}: {missing}")
                print(f"📋 Columnas disponibles: {df.columns.tolist()[:10]}")
                return False
            
            self.current_df = df
            self.current_filename = filename
            print(f"✅ Excel cargado: {filename} ({len(df)} filas)")
            return True
            
        except Exception as e:
            print(f"❌ Error al cargar Excel: {e}")
            return False
    
    def buscar_terminal(self, terminal: str) -> List[Dict]:
        """
        Buscar terminal en las columnas 'De Terminal' y 'Para Terminal'
        Retorna lista de diccionarios con los datos encontrados
        BÚSQUEDA INSENSIBLE A MAYÚSCULAS/MINÚSCULAS
        
        Args:
            terminal: Número de terminal a buscar
        
        Returns:
            Lista de diccionarios con las filas donde aparece el terminal
        """
        if self.current_df is None:
            return []
        
        # Convertir terminal a mayúsculas para búsqueda case-insensitive
        terminal_upper = str(terminal).upper().strip()
        
        # Preparar máscaras seguras
        cols = self.current_df.columns
        
        if 'De Terminal' in cols:
            mask_origen = self.current_df['De Terminal'].astype(str).str.upper() == terminal_upper
        else:
            mask_origen = pd.Series(False, index=self.current_df.index)
        
        if 'Para Terminal' in cols:
            mask_destino = self.current_df['Para Terminal'].astype(str).str.upper() == terminal_upper
        else:
            mask_destino = pd.Series(False, index=self.current_df.index)
        
        # Seleccionar filas que coincidan
        mask_any = mask_origen | mask_destino
        if not mask_any.any():
            return []
        
        df = self.current_df[mask_any].copy()
        
        # Etiquetar el tipo de coincidencia
        tipo = pd.Series(index=self.current_df.index, dtype=object)
        tipo[(mask_origen) & (~mask_destino)] = 'origen'
        tipo[(~mask_origen) & (mask_destino)] = 'destino'
        tipo[(mask_origen) & (mask_destino)] = 'ambas'
        df['tipo_conexion'] = tipo.loc[df.index].fillna('origen')
        
        return df.to_dict('records')
    
    def agrupar_por_cable_elemento(self, resultados: List[Dict], terminal_buscado: str) -> Dict:
        """
        Agrupar resultados por código de cable y elemento (De Elemento)
        
        REGLAS:
        1. Agrupar por Código de Cable + De Elemento
        2. AZUL (cables_de_terminal): terminal solo en "De Terminal" (1 terminal)
        3. VERDE (cables_para_terminal): terminal solo en "Para Terminal" (1 terminal)
        4. ROJO (cables_doble_terminal): terminal en AMBOS lados de la MISMA fila (2 terminales)
        
        Args:
            resultados: Lista de filas del Excel donde aparece el terminal
            terminal_buscado: Terminal que estamos buscando
        
        Returns:
            Diccionario con los grupos organizados por cable + elemento
        """
        if not resultados:
            return {}
        
        grupos = {}
        
        # Helper para evitar NaN/None
        def _safe_str(v):
            try:
                if pd.isna(v):
                    return ''
            except:
                pass
            return '' if v is None else str(v)
        
        def _safe_num(v):
            try:
                if pd.isna(v):
                    return ''
            except:
                pass
            return v
        
        for row in resultados:
            # Ignorar filas sin código de cable o sin sección (son líneas auxiliares del cableador)
            _cod_raw = row.get('Cod. cable', '')
            _sec_raw = row.get('Sección', row.get('Seccion', ''))
            try:
                _cod_vacio = (pd.isna(_cod_raw) or str(_cod_raw).strip() == '')
            except Exception:
                _cod_vacio = (str(_cod_raw).strip() == '')
            try:
                _sec_vacio = (pd.isna(_sec_raw) or str(_sec_raw).strip() == '')
            except Exception:
                _sec_vacio = (str(_sec_raw).strip() == '')
            if _cod_vacio or _sec_vacio:
                continue

            # Datos de la fila
            cod_cable = row.get('Cod. cable', 'Sin código')
            _cable_marca_raw = str(row.get('Cable / Marca', '')).strip()
            _de_marca_raw    = str(row.get('De Marca', '')).strip()
            # Si Cable / Marca está vacío o es 'nan', usar De Marca como fallback
            cable_marca = (_cable_marca_raw if _cable_marca_raw and _cable_marca_raw.lower() != 'nan'
                           else _de_marca_raw if _de_marca_raw and _de_marca_raw.lower() != 'nan'
                           else 'nan')
            de_elemento   = row.get('De Elemento Etiquetas', 'Sin elemento')
            de_terminal   = row.get('De Terminal', '')
            para_terminal = row.get('Para Terminal', '')

            # Si De Elemento o Para Elemento terminan en *, ese terminal no se engasta
            de_no_poner   = str(row.get('De Elemento', '')).strip().endswith('*')
            para_no_poner = str(row.get('Para Elemento', '')).strip().endswith('*')
            
            # Clave del grupo: Cable + Elemento
            clave = f"{cod_cable}|{de_elemento}"
            
            if clave not in grupos:
                # Buscar descripción y sección con normalización
                descripcion_val = row.get('Descripción Cable', row.get('Descripcion Cable', ''))
                seccion_val = row.get('Sección', row.get('Seccion', ''))
                
                grupos[clave] = {
                    'cod_cable': _safe_str(cod_cable),
                    'elemento': _safe_str(de_elemento),
                    'descripcion': _safe_str(descripcion_val),
                    'seccion': _safe_str(seccion_val),
                    'longitud': _safe_num(row.get('Longitud', '')),
                    'de_terminal': _safe_str(de_terminal),
                    'cables_lista': [],
                    'cables_doble_terminal': [],  # ROJO: terminal en ambos lados
                    'cables_de_terminal': [],     # AZUL: terminal solo en "De Terminal"
                    'cables_para_terminal': [],   # VERDE: terminal solo en "Para Terminal"
                    'num_terminales': 0,
                    'serie_col': _safe_str(row['Series']) if 'Series' in row and row['Series'] == row['Series'] else '',
                }

            if cable_marca:
                # Verificar si ESTA FILA tiene el terminal en ambos lados (case-insensitive)
                terminal_buscado_upper = str(terminal_buscado).upper().strip()
                de_terminal_upper = str(de_terminal).upper().strip()
                para_terminal_upper = str(para_terminal).upper().strip()
                
                tiene_origen = de_terminal_upper == terminal_buscado_upper
                tiene_destino = para_terminal_upper == terminal_buscado_upper
                es_doble_en_esta_fila = tiene_origen and tiene_destino
                
                # Agregar cable a la lista
                grupos[clave]['cables_lista'].append(cable_marca)
                
                if es_doble_en_esta_fila:
                    if de_no_poner and para_no_poner:
                        pass  # ningún terminal que engastar en esta fila
                    elif de_no_poner:
                        # De Terminal no se engasta, Para Terminal sí -> VERDE
                        grupos[clave]['cables_para_terminal'].append(cable_marca)
                        grupos[clave]['num_terminales'] += 1
                    elif para_no_poner:
                        # Para Terminal no se engasta, De Terminal sí -> AZUL
                        grupos[clave]['cables_de_terminal'].append(cable_marca)
                        grupos[clave]['num_terminales'] += 1
                    else:
                        # ROJO: terminal en AMBOS lados (2 terminales)
                        grupos[clave]['cables_doble_terminal'].append(cable_marca)
                        grupos[clave]['num_terminales'] += 2
                elif tiene_origen:
                    if not de_no_poner:
                        # AZUL: terminal solo en "De Terminal" (1 terminal)
                        grupos[clave]['cables_de_terminal'].append(cable_marca)
                        grupos[clave]['num_terminales'] += 1
                elif tiene_destino:
                    if not para_no_poner:
                        # VERDE: terminal solo en "Para Terminal" (1 terminal)
                        grupos[clave]['cables_para_terminal'].append(cable_marca)
                        grupos[clave]['num_terminales'] += 1
        
        # Ordenar cables y preparar datos finales
        for grupo in grupos.values():
            def sort_cable(cable):
                cable_str = str(cable).strip()
                try:
                    return (0, int(cable_str))  # Números primero
                except ValueError:
                    return (1, cable_str)  # Strings después
            
            grupo['todos_cables'] = sorted(grupo['cables_lista'], key=sort_cable)
            grupo['num_cables'] = len(grupo['cables_lista'])
            
            # Limpiar
            del grupo['cables_lista']
        
        return grupos
    
    def get_columnas(self) -> List[str]:
        """Obtener nombres de columnas del DataFrame actual"""
        if self.current_df is not None:
            return list(self.current_df.columns)
        return []

    def get_manguitos(self, filename: str) -> list:
        """
        Lee todas las filas del Excel donde 'De Manguito' tiene valor válido
        (no vacío y no 'S/M'), agrupa por 'De Elemento' preservando orden de aparición.

        Returns:
            Lista de dicts: [{ 'elemento': str, 'manguitos': [{de_marca, de_manguito,
                               de_punto, para_elemento, para_punto}] }]
        """
        filepath = self._ruta_segura(filename)
        if not filepath or not os.path.exists(filepath):
            raise FileNotFoundError(f'Archivo no encontrado: {filename}')

        df = leer_excel_cacheado(filepath)

        def _safe(v):
            try:
                if pd.isna(v):
                    return ''
            except Exception:
                pass
            return '' if v is None else str(v).strip()

        def _sin_asterisco(v):
            # El '*' marca terminales que no se engastan; no aplica en manguitos
            return _safe(v).rstrip('*').rstrip()

        def _col(names):
            for n in names:
                if n in df.columns:
                    return n
            return None

        col_de_manguito      = _col(['De Manguito'])
        col_de_marca         = _col(['De Marca'])
        col_de_elemento      = _col(['De Elemento Etiquetas', 'De Elemento'])
        col_de_elemento_orig = _col(['De Elemento Original', 'De Elemento'])
        col_de_punto         = _col(['De Punto Conexión', 'De Punto Conexion', 'De Punto'])
        col_para_elem        = _col(['Para Elemento'])
        col_para_punto       = _col(['Para Punto Conexión', 'Para Punto Conexion', 'Para Punto'])
        col_cod_cable        = _col(['Cod. cable'])
        col_longitud         = _col(['Longitud'])
        col_seccion          = _col(['Sección', 'Seccion'])
        col_observaciones    = _col(['Observaciones'])

        if not col_de_manguito:
            raise ValueError("Columna 'De Manguito' no encontrada en el Excel")

        elementos = {}
        orden_elementos = []

        for _, row in df.iterrows():
            de_manguito = _safe(row[col_de_manguito])
            if not de_manguito or de_manguito.upper() == 'S/M':
                continue

            # Clave de agrupación y lookup de etiquetas: columna renombrada
            de_elemento = (_safe(row[col_de_elemento]) if col_de_elemento else '') or 'Sin elemento'

            # Valor para pantalla y TXT: columna original si existe, si no la renombrada (sin fallback)
            if col_de_elemento_orig:
                de_elemento_display = _sin_asterisco(row[col_de_elemento_orig])
            else:
                de_elemento_display = _sin_asterisco(row[col_de_elemento]) if col_de_elemento else ''

            # Longitud numérica
            _lon_raw = row[col_longitud] if col_longitud else None
            try:
                _lon = float(_lon_raw) if _lon_raw is not None and not pd.isna(_lon_raw) else None
            except Exception:
                _lon = None

            activo_manguera = None
            if _lon is not None and abs(_lon) < 1e-9 and col_observaciones:
                obs = _safe(row[col_observaciones])
                m_act = re.search(r'\(\s*(\d+)\s*\)', obs)
                if m_act:
                    activo_manguera = m_act.group(1)

            manguito = {
                'de_marca':      _safe(row[col_de_marca])      if col_de_marca   else '',
                'de_manguito':   de_manguito,
                'de_elemento':   de_elemento_display,
                'de_punto':      _safe(row[col_de_punto])      if col_de_punto   else '',
                'para_elemento': _sin_asterisco(row[col_para_elem])     if col_para_elem  else '',
                'para_punto':    _safe(row[col_para_punto])    if col_para_punto else '',
                'cod_cable':     _safe(row[col_cod_cable])     if col_cod_cable  else '',
                'longitud':      _lon,
                'seccion':       _safe(row[col_seccion])        if col_seccion    else '',
                'activo_manguera': activo_manguera,
            }

            if de_elemento not in elementos:
                elementos[de_elemento] = []
                orden_elementos.append(de_elemento)
            elementos[de_elemento].append(manguito)

        return [{'elemento': el, 'manguitos': elementos[el]} for el in orden_elementos]


# ── Helpers de parseo de Observaciones (Preparación de Mangueras) ─────────────

def _parse_retractiles(val_str):
    """Parsea '649255_40/649251_70' en lista de dicts {codigo, medida}."""
    if not val_str:
        return []
    result = []
    for token in val_str.split('/'):
        t = token.strip()
        if not t:
            continue
        m = re.match(r'^(.+?)_(\d+)$', t)
        if m:
            result.append({'codigo': m.group(1).strip(), 'medida': int(m.group(2))})
    return result


def _parse_instrucciones(inst_str):
    """Parsea una cadena de instrucciones como 'PM120/M110/A150' en un dict."""
    inst = {'pm': None, 'm': None, 'm_cortar': False, 'm_mrs': False, 'm_mrs_medida': None, 'm_mrc': False, 'm_mrc_medida': None, 'a_todos': None, 'a_especificos': {}}
    for token in inst_str.split('/'):
        t = token.strip().upper()
        if not t:
            continue
        m = re.match(r'^PM(\d+)$', t)
        if m:
            inst['pm'] = int(m.group(1))
            continue
        if t in ('M_CORTAR', 'MCORTAR'):
            inst['m_cortar'] = True
            continue
        if t == 'MRS':
            inst['m_mrs'] = True
            continue
        m = re.match(r'^MRS(\d+)$', t)
        if m:
            inst['m_mrs'] = True
            inst['m_mrs_medida'] = int(m.group(1))
            continue
        m = re.match(r'^MRC(\d+)$', t)
        if m:
            inst['m_mrc'] = True
            inst['m_mrc_medida'] = int(m.group(1))
            continue
        if t == 'MRC':
            inst['m_mrc'] = True
            continue
        m = re.match(r'^M(\d+)$', t)
        if m:
            inst['m'] = int(m.group(1))
            continue
        m = re.match(r'^A(\d+)_(\d+)$', t)
        if m:
            inst['a_especificos'][m.group(1)] = int(m.group(2))
            continue
        m = re.match(r'^A(\d+)$', t)
        if m:
            inst['a_todos'] = int(m.group(1))
            continue
    return inst


def _parse_pelado(obs_str):
    """Parsea '<-PM120/M110 // PM300->' en {'de': {...}, 'para': {...}}."""
    result = {'de': None, 'para': None}
    parts = re.split(r'//|\$', obs_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '<-' in part:
            side = 'de'
            inst_str = part[part.index('<-')+2:].strip()
        elif '->' in part:
            side = 'para'
            inst_str = part[:part.index('->')].strip()
        else:
            continue
        result[side] = _parse_instrucciones(inst_str)
    return result


class ManguerasManager:
    """Método auxiliar que reutiliza la misma carpeta que ExcelManager"""
    pass


# Extender ExcelManager con get_mangueras
def _get_mangueras(self, filename: str) -> list:
    """
    Lee las filas del Excel con instrucciones de pelado de mangueras.

    Soporta dos formatos (con fallback automático):
      1. NUEVO: columnas 'Instrucciones Mangueras DE' y/o 'Instrucciones Mangueras PARA'
         Cada columna contiene los tokens directamente: PM150/M70
      2. LEGACY: columna 'Observaciones' con sintaxis '<-tokens // tokens->'
         Se mantiene como fallback mientras se migran los Excels.
    """
    filepath = self._ruta_segura(filename)
    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError(f'Archivo no encontrado: {filename}')

    df = leer_excel_cacheado(filepath)

    def _safe(v):
        try:
            if pd.isna(v):
                return ''
        except Exception:
            pass
        return '' if v is None else str(v).strip()

    def _col(names):
        for n in names:
            if n in df.columns:
                return n
        return None

    col_inst_de       = _col(['Instrucciones Mangueras DE'])
    col_inst_para     = _col(['Instrucciones Mangueras PARA'])
    col_ret_de        = _col(['Retractil DE', 'Retráctil DE'])
    col_ret_para      = _col(['Retractil PARA', 'Retráctil PARA'])
    col_obs           = _col(['Observaciones'])
    col_cable_marca   = _col(['Cable / Marca'])
    col_de_marca      = _col(['De Marca'])
    col_de_elemento   = _col(['De Elemento Etiquetas', 'De Elemento'])
    col_cod_cable     = _col(['Cod. cable', 'Cod.cable', 'Cod cable'])
    col_de_terminal   = _col(['De Terminal'])
    col_para_terminal = _col(['Para Terminal'])

    # Al menos una fuente de instrucciones debe existir
    usa_columnas_nuevas = col_inst_de or col_inst_para
    if not usa_columnas_nuevas and not col_obs:
        raise ValueError(
            "No se encontró ninguna columna de instrucciones de mangueras. "
            "Se esperaba 'Instrucciones Mangueras DE'/'PARA' o 'Observaciones'."
        )

    resultado = []
    for _, row in df.iterrows():
        val_de   = _safe(row[col_inst_de])   if col_inst_de   else ''
        val_para = _safe(row[col_inst_para]) if col_inst_para else ''
        obs      = _safe(row[col_obs])       if col_obs       else ''

        # Determinar si esta fila tiene instrucciones de manguera
        val_ret_de   = _safe(row[col_ret_de])   if col_ret_de   else ''
        val_ret_para = _safe(row[col_ret_para]) if col_ret_para else ''
        tiene_nuevas    = bool(val_de or val_para)
        tiene_legacy    = '<-' in obs or '->' in obs
        tiene_retractil = bool(val_ret_de or val_ret_para)

        if not tiene_nuevas and not tiene_legacy and not tiene_retractil:
            continue

        cm_raw = _safe(row[col_cable_marca]) if col_cable_marca else ''
        dm_raw = _safe(row[col_de_marca])    if col_de_marca    else ''
        cable_marca = (cm_raw if cm_raw and cm_raw.lower() != 'nan'
                       else dm_raw if dm_raw and dm_raw.lower() != 'nan'
                       else 'nan')

        if tiene_nuevas:
            # Formato nuevo: cada columna ya contiene los tokens del lado
            inst_de   = _parse_instrucciones(val_de)   if val_de   else None
            inst_para = _parse_instrucciones(val_para) if val_para else None
            obs_raw   = f"DE: {val_de} | PARA: {val_para}" if (val_de or val_para) else obs
        else:
            # Formato legacy: parsear <-tokens // tokens->
            parsed    = _parse_pelado(obs)
            inst_de   = parsed.get('de')
            inst_para = parsed.get('para')
            obs_raw   = obs

        resultado.append({
            'cable_marca':       cable_marca,
            'cod_cable':         _safe(row[col_cod_cable])    if col_cod_cable    else '',
            'de_elemento':       _safe(row[col_de_elemento])  if col_de_elemento  else '',
            'de_terminal':       _safe(row[col_de_terminal])  if col_de_terminal  else '',
            'para_terminal':     _safe(row[col_para_terminal]) if col_para_terminal else '',
            'observaciones_raw': obs_raw,
            'de':                inst_de,
            'para':              inst_para,
            'retractil_de':      _parse_retractiles(val_ret_de),
            'retractil_para':    _parse_retractiles(val_ret_para),
        })

    return resultado


ExcelManager.get_mangueras = _get_mangueras


# ── Validación de columnas Excel al subir fichero ─────────────────────────────

COLUMNAS_MANGUERAS_ESPERADAS = [
    'De Elemento Etiquetas',
    'Instrucciones Mangueras DE',
    'Retractil DE',
    'Instrucciones Mangueras PARA',
    'Retractil PARA',
    'Series',
]

_FEATURE_POR_COLUMNA = {
    'De Elemento Etiquetas':        'Etiquetas de elementos',
    'Instrucciones Mangueras DE':   'Preparación mangueras — lado De',
    'Retractil DE':                 'Retráctiles — lado De',
    'Instrucciones Mangueras PARA': 'Preparación mangueras — lado Para',
    'Retractil PARA':               'Retráctiles — lado Para',
    'Series':                       'Agrupación por series',
}


def _tokens_invalidos_instrucciones(inst_str):
    """Retorna lista de tokens no reconocidos en una cadena de instrucciones de manguera."""
    invalidos = []
    for token in inst_str.split('/'):
        t = token.strip().upper()
        if not t:
            continue
        if (re.match(r'^PM\d+$', t) or
                re.match(r'^M\d+$', t) or
                re.match(r'^MRC\d*$', t) or
                re.match(r'^A\d+_\d+$', t) or
                re.match(r'^A\d+$', t) or
                re.match(r'^MRS\d+$', t) or
                t in ('MCORTAR', 'M_CORTAR', 'MRS')):
            continue
        invalidos.append(token.strip())
    return invalidos


def _retractil_formato_valido(val_str):
    """Verifica que todos los tokens de retráctil tienen formato CODIGO_MEDIDA."""
    for token in val_str.split('/'):
        t = token.strip()
        if not t:
            continue
        if not re.match(r'^.+_\d+$', t):
            return False
    return True


def validar_excel_columnas(filepath):
    """
    Valida las columnas de preparación de mangueras en un Excel recién subido.
    """
    def _celda_vacia(val):
        """True si la celda no tiene contenido útil."""
        try:
            if pd.isna(val):
                return True
        except Exception:
            pass
        s = str(val).strip()
        return s == '' or s.lower() in ('nan', 'none', 'nat')

    try:
        df = leer_excel_cacheado(filepath)
    except Exception as exc:
        return {
            'columnas_faltantes': [], 'features_no_disponibles': [],
            'advertencias': [], 'advertencias_total': 0,
            'error': str(exc),
        }

    columnas_faltantes      = [c for c in COLUMNAS_MANGUERAS_ESPERADAS if c not in df.columns]
    features_no_disponibles = [_FEATURE_POR_COLUMNA[c] for c in columnas_faltantes]
    advertencias = []

    for col in ['Instrucciones Mangueras DE', 'Instrucciones Mangueras PARA']:
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            if _celda_vacia(val):
                continue
            val_str = str(val).strip()
            errores = _tokens_invalidos_instrucciones(val_str)
            if errores:
                advertencias.append({
                    'columna': col,
                    'fila': int(idx) + 2,
                    'valor': val_str[:60],
                    'mensaje': f"Token(s) no reconocido(s): {', '.join(errores)}",
                })

    for col in ['Retractil DE', 'Retractil PARA']:
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            if _celda_vacia(val):
                continue
            val_str = str(val).strip()
            if not _retractil_formato_valido(val_str):
                advertencias.append({
                    'columna': col,
                    'fila': int(idx) + 2,
                    'valor': val_str[:60],
                    'mensaje': 'Formato inválido — se esperaba CODIGO_MEDIDA (ej: 649255_40)',
                })

    total = len(advertencias)
    return {
        'columnas_faltantes':      columnas_faltantes,
        'features_no_disponibles': features_no_disponibles,
        'advertencias':            advertencias[:30],
        'advertencias_total':      total,
    }

