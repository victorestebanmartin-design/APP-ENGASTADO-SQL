import hashlib
import io
import re
from copy import copy

from openpyxl import load_workbook

from app.excel_manager import (
    _normalizar_texto_columna, _parse_instrucciones, _parse_pelado,
    _parse_retractiles, _tokens_invalidos_instrucciones, _serie_str,
)


PREPARACION_COLUMNAS = (
    'Instrucciones Mangueras DE', 'Instrucciones Mangueras PARA',
    'Retractil DE', 'Retractil PARA',
)


def _texto(valor):
    return '' if valor is None else str(valor).strip()


def _columnas(hoja):
    columnas = {}
    for celda in hoja[1]:
        if celda.value is not None:
            clave = _normalizar_texto_columna(celda.value)
            if clave in columnas:
                raise ValueError(f'Cabecera duplicada: {celda.value}')
            columnas[clave] = celda.column
    return columnas


def _valor(hoja, columnas, fila, *nombres):
    for nombre in nombres:
        indice = columnas.get(_normalizar_texto_columna(nombre))
        if indice:
            return _texto(hoja.cell(fila, indice).value)
    return ''


def _marca_base_asociada(marca):
    numero = re.fullmatch(r'(.+?)\(\s*([A-Za-z]+|\d+)\s*\)', marca, flags=re.I)
    if numero:
        base = numero.group(1).strip()
        base_sin_numero = re.sub(r'(?<=[A-Za-z])\d+$', '', base)
        return base_sin_numero.upper(), numero.group(2).upper()
    numero = re.fullmatch(r'(.+)-(\d+)', marca)
    if numero:
        return numero.group(1).strip().upper(), numero.group(2)
    return None, None


def _abrir(contenido, nombre):
    if not nombre.lower().endswith(('.xlsx', '.xlsm')):
        raise ValueError('Selecciona un Excel .xlsx o .xlsm. Convierte los .xls antes de abrirlos.')
    libro = load_workbook(io.BytesIO(contenido), keep_vba=nombre.lower().endswith('.xlsm'))
    hoja = libro['Format'] if 'Format' in libro.sheetnames else libro.worksheets[0]
    return libro, hoja, _columnas(hoja)


def _vinculos_mangueras(hoja, columnas):
    padres = {}
    candidatos = {}
    activos = {}
    for fila in range(2, hoja.max_row + 1):
        marca = (_valor(hoja, columnas, fila, 'Cable / Marca') or
                 _valor(hoja, columnas, fila, 'De Marca'))
        elemento = (_valor(hoja, columnas, fila, 'De Elemento Etiquetas') or
                _valor(hoja, columnas, fila, 'De Elemento')).rstrip('*').strip().upper()
        codigo = _valor(hoja, columnas, fila, 'Cod. cable').upper()
        serie = _serie_str(_valor(hoja, columnas, fila, 'Series'))
        try:
            longitud = float(_valor(hoja, columnas, fila, 'Longitud').replace(',', '.'))
        except ValueError:
            continue
        seccion = _valor(hoja, columnas, fila, 'Sección')
        if longitud > 0 and re.match(r'^\s*\d+\s*[xX\u00d7]', seccion) and marca and elemento and codigo:
            base = re.sub(r'-P$', '', marca, flags=re.I).upper()
            clave = (base, codigo, elemento, serie)
            padres[fila] = clave
            candidatos.setdefault(clave, []).append(fila)
        elif longitud == 0 and marca and elemento and codigo:
            base, activo = _marca_base_asociada(marca)
            if base is None:
                numero = re.search(r'\(\s*(\d+)\s*\)', _valor(hoja, columnas, fila, 'Observaciones'))
                if not numero:
                    continue
                base, activo = marca.upper(), numero.group(1)
            clave = (base, codigo, elemento, serie)
            activos.setdefault(clave, []).append((fila, activo))
    resultado = {}
    for fila, clave in padres.items():
        encontrados = activos.get(clave, [])
        ambiguo = len(candidatos[clave]) != 1
        resultado[fila] = {'confirmados': bool(encontrados) and not ambiguo,
                           'ambiguo': ambiguo, 'activos': [], 'mallas': []}
        for fila_activo, numero in encontrados:
            grupo = 'mallas' if numero == 'S' else 'activos'
            resultado[fila][grupo].append({
                'fila': fila_activo, 'numero': numero,
                'cable_marca': _valor(hoja, columnas, fila_activo, 'Cable / Marca'),
                'de_elemento': _valor(hoja, columnas, fila_activo, 'De Elemento', 'De Elemento Etiquetas'),
                'para_elemento': _valor(hoja, columnas, fila_activo, 'Para Elemento'),
                'de_terminal': _valor(hoja, columnas, fila_activo, 'De Terminal'),
                'para_terminal': _valor(hoja, columnas, fila_activo, 'Para Terminal'),
                'bloqueo_automatico_de': _valor(hoja, columnas, fila_activo, 'Bloqueo Mangueras DE') in ('1', '1.0'),
                'bloqueo_automatico_para': _valor(hoja, columnas, fila_activo, 'Bloqueo Mangueras PARA') in ('1', '1.0'),
            })
    return resultado


def _columna_escritura(hoja, columnas, cabecera):
    clave = _normalizar_texto_columna(cabecera)
    if clave not in columnas:
        indice = hoja.max_column + 1
        nueva = hoja.cell(1, indice, cabecera)
        nueva._style = copy(hoja.cell(1, indice - 1)._style)
        hoja.column_dimensions[nueva.column_letter].width = 32
        columnas[clave] = indice
    hoja.cell(1, columnas[clave]).value = cabecera
    return columnas[clave]


def _lados_preparados(hoja, columnas, fila):
    de = _valor(hoja, columnas, fila, PREPARACION_COLUMNAS[0])
    para = _valor(hoja, columnas, fila, PREPARACION_COLUMNAS[1])
    if de or para:
        instrucciones = {'de': _parse_instrucciones(de), 'para': _parse_instrucciones(para)}
    else:
        instrucciones = _parse_pelado(_valor(hoja, columnas, fila, 'Observaciones'))
    return {lado: (instrucciones[lado] or {}).get('pm') is not None for lado in ('de', 'para')}


def _actualizar_bloqueos(hoja, columnas, fila, vinculacion):
    if not vinculacion.get('confirmados'):
        return
    preparados = _lados_preparados(hoja, columnas, fila)
    for lado, cabecera_elemento, cabecera_terminal in (
            ('de', 'De Elemento', 'De Terminal'), ('para', 'Para Elemento', 'Para Terminal')):
        bloquear = not preparados[lado]
        marca_bloqueo = 'Bloqueo Mangueras ' + lado.upper()
        asociados = vinculacion['activos'] + vinculacion.get('mallas', [])
        for fila_destino in [fila] + [activo['fila'] for activo in asociados]:
            terminal = _valor(hoja, columnas, fila_destino, cabecera_terminal)
            if terminal.upper() in ('', 'S/T', 'NAN', 'NONE'):
                continue
            elemento = _valor(hoja, columnas, fila_destino, cabecera_elemento)
            automatico = _valor(hoja, columnas, fila_destino, marca_bloqueo) in ('1', '1.0')
            if bloquear and not elemento.endswith('*'):
                if lado == 'de' and not elemento:
                    elemento = _valor(hoja, columnas, fila_destino, 'De Elemento Etiquetas')
                hoja.cell(fila_destino, _columna_escritura(hoja, columnas, cabecera_elemento), elemento + '*')
                hoja.cell(fila_destino, _columna_escritura(hoja, columnas, marca_bloqueo), '1')
            elif not bloquear and automatico:
                hoja.cell(fila_destino, _columna_escritura(hoja, columnas, cabecera_elemento),
                          elemento[:-1] if elemento.endswith('*') else elemento)
                hoja.cell(fila_destino, _columna_escritura(hoja, columnas, marca_bloqueo)).value = None


def leer_preparacion(contenido, nombre):
    libro, hoja, columnas = _abrir(contenido, nombre)
    try:
        if _normalizar_texto_columna('Sección') not in columnas:
            raise ValueError('El Excel no contiene la columna Sección.')
        vinculos = _vinculos_mangueras(hoja, columnas)
        filas_activos = {activo['fila'] for vinculo in vinculos.values()
                for activo in vinculo['activos'] + vinculo.get('mallas', [])}
        filas = []
        for fila in range(2, hoja.max_row + 1):
            if fila in filas_activos:
                continue
            seccion = _valor(hoja, columnas, fila, 'Sección')
            inst_de = _valor(hoja, columnas, fila, PREPARACION_COLUMNAS[0])
            inst_para = _valor(hoja, columnas, fila, PREPARACION_COLUMNAS[1])
            ret_de = _valor(hoja, columnas, fila, PREPARACION_COLUMNAS[2])
            ret_para = _valor(hoja, columnas, fila, PREPARACION_COLUMNAS[3])
            obs = _valor(hoja, columnas, fila, 'Observaciones')
            sugerida = bool(re.match(r'^\s*\d+\s*[xX\u00d7]', seccion))
            if not sugerida and not any((inst_de, inst_para, ret_de, ret_para, '<-' in obs, '->' in obs)):
                continue
            if inst_de or inst_para:
                de = _parse_instrucciones(inst_de)
                para = _parse_instrucciones(inst_para)
            else:
                legacy = _parse_pelado(obs)
                de = legacy['de'] or _parse_instrucciones('')
                para = legacy['para'] or _parse_instrucciones('')
                partes = re.split(r'//|\$', obs)
                inst_de = next((parte.split('<-', 1)[1].strip() for parte in partes if '<-' in parte), '')
                inst_para = next((parte.split('->', 1)[0].strip() for parte in partes if '->' in parte and '<-' not in parte), '')
            for instrucciones, raw in ((de, inst_de), (para, inst_para)):
                instrucciones['otros_tokens'] = _tokens_invalidos_instrucciones(raw)
            filas.append({
                'fila': fila, 'sugerida': sugerida, 'seccion': seccion,
                'cable_marca': _valor(hoja, columnas, fila, 'Cable / Marca', 'De Marca'),
                'cod_cable': _valor(hoja, columnas, fila, 'Cod. cable'),
                'de_elemento': _valor(hoja, columnas, fila, 'De Elemento Etiquetas', 'De Elemento'),
                'de_elemento_original': _valor(hoja, columnas, fila, 'De Elemento', 'De Elemento Etiquetas'),
                'para_elemento': _valor(hoja, columnas, fila, 'Para Elemento'),
                'de_terminal': _valor(hoja, columnas, fila, 'De Terminal'),
                'para_terminal': _valor(hoja, columnas, fila, 'Para Terminal'),
                'bloqueo_automatico_de': _valor(hoja, columnas, fila, 'Bloqueo Mangueras DE') in ('1', '1.0'),
                'bloqueo_automatico_para': _valor(hoja, columnas, fila, 'Bloqueo Mangueras PARA') in ('1', '1.0'),
                'de': de, 'para': para,
                'retractil_de': _parse_retractiles(ret_de),
                'retractil_para': _parse_retractiles(ret_para),
                'retractil_de_raw': ret_de, 'retractil_para_raw': ret_para,
                'vinculacion': vinculos.get(fila, {'confirmados': False, 'ambiguo': False, 'activos': []}),
                'campos': {str(hoja.cell(1, indice).value): _texto(hoja.cell(fila, indice).value)
                           for indice in columnas.values()},
            })
        return {'nombre': nombre, 'hoja': hoja.title, 'filas': filas,
                'revision': hashlib.sha256(contenido).hexdigest()}
    finally:
        libro.close()


def _medida(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, bool) or not re.fullmatch(r'\d{1,6}', str(valor)):
        raise ValueError('Las medidas deben ser enteros entre 0 y 999999 mm.')
    return str(int(valor))


def serializar_instrucciones(instrucciones):
    if not isinstance(instrucciones, dict):
        raise ValueError('Instrucciones no válidas.')
    tokens = []
    for campo, prefijo in (('pm', 'PM'), ('a_todos', 'A')):
        medida = _medida(instrucciones.get(campo))
        if medida is not None:
            tokens.append(prefijo + medida)
    modos = [campo for campo in ('m_cortar', 'm_mrs', 'm_mrc') if instrucciones.get(campo)]
    if len(modos) > 1 or (modos and instrucciones.get('m') not in (None, '')):
        raise ValueError('Selecciona un único tratamiento de malla.')
    if modos:
        modo = modos[0]
        if modo == 'm_cortar':
            tokens.append('M_CORTAR')
        else:
            tokens.append(('MRS' if modo == 'm_mrs' else 'MRC') +
                          (_medida(instrucciones.get(modo + '_medida')) or ''))
    else:
        medida = _medida(instrucciones.get('m'))
        if medida is not None:
            tokens.append('M' + medida)
    activos = instrucciones.get('a_especificos', {})
    if not isinstance(activos, dict):
        raise ValueError('Activos individuales no válidos.')
    for activo, valor in activos.items():
        if not re.fullmatch(r'[1-9]\d{0,3}', str(activo)):
            raise ValueError('El número de activo debe estar entre 1 y 9999.')
        medida = _medida(valor)
        if medida is None:
            raise ValueError('Falta la medida del activo.')
        tokens.append(f'A{activo}_{medida}')
    otros = instrucciones.get('otros_tokens', [])
    if not isinstance(otros, list) or any(not isinstance(token, str) or
                                          re.search(r'[/\r\n]', token) for token in otros):
        raise ValueError('Tokens adicionales no válidos.')
    tokens.extend(otros)
    return '/'.join(tokens)


def _serializar_retractiles(retractiles):
    if not isinstance(retractiles, list):
        raise ValueError('Lista de retráctiles no válida.')
    tokens = []
    for retractil in retractiles:
        if not isinstance(retractil, dict):
            raise ValueError('Retráctil no válido.')
        codigo = _texto(retractil.get('codigo'))
        medida = _medida(retractil.get('medida'))
        if not codigo or re.search(r'[/\r\n]', codigo) or codigo.startswith(('=', '+', '-', '@')) or medida is None:
            raise ValueError('Cada retráctil necesita código y medida, sin / en el código.')
        tokens.append(f'{codigo}_{medida}')
    return '/'.join(tokens)


def exportar_preparacion(contenido, nombre, cambios, revision):
    if revision != hashlib.sha256(contenido).hexdigest():
        raise ValueError('El Excel ha cambiado. Vuelve a cargarlo antes de descargar.')
    if not isinstance(cambios, list):
        raise ValueError('Los cambios deben ser una lista.')
    disponibles = {fila['fila'] for fila in leer_preparacion(contenido, nombre)['filas']}
    libro, hoja, columnas = _abrir(contenido, nombre)
    try:
        vinculos = _vinculos_mangueras(hoja, columnas)
        vistos = set()
        for cambio in cambios:
            if not isinstance(cambio, dict):
                raise ValueError('Cambio no válido.')
            fila = cambio.get('fila')
            if type(fila) is not int or fila not in disponibles or fila in vistos:
                raise ValueError('Fila de manguera no válida o repetida.')
            vistos.add(fila)
            valores = (
                serializar_instrucciones(cambio.get('de')),
                serializar_instrucciones(cambio.get('para')),
                _serializar_retractiles(cambio.get('retractil_de')),
                _serializar_retractiles(cambio.get('retractil_para')),
            )
            valores = list(valores)
            for posicion, lado in ((2, 'de'), (3, 'para')):
                raw = _valor(hoja, columnas, fila, PREPARACION_COLUMNAS[posicion])
                if cambio.get('retractil_' + lado) == _parse_retractiles(raw):
                    valores[posicion] = raw
            for cabecera, valor in zip(PREPARACION_COLUMNAS, valores):
                celda = hoja.cell(fila, _columna_escritura(hoja, columnas, cabecera))
                celda.value = valor or None
                celda.data_type = 's'
            if not any(valores[:2]):
                indice_obs = columnas.get(_normalizar_texto_columna('Observaciones'))
                if indice_obs:
                    celda = hoja.cell(fila, indice_obs)
                    obs = _texto(celda.value)
                    if '<-' in obs or '->' in obs:
                        celda.value = ' // '.join(parte.strip() for parte in re.split(r'//|\$', obs)
                                                 if '<-' not in parte and '->' not in parte) or None
        for fila, vinculacion in vinculos.items():
            _actualizar_bloqueos(hoja, columnas, fila, vinculacion)
        salida = io.BytesIO()
        libro.save(salida)
        salida.seek(0)
        return salida
    finally:
        libro.close()