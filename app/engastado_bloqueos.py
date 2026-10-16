"""Terminales que el operario dice que no se ponen en un cable.

El '*' al final de De Elemento / Para Elemento ya hace que todo el sistema
deje de pedir y contar ese terminal (ver excel_manager.agrupar_por_cable_elemento).
Aquí solo se escribe o se quita ese '*' en la fila y el lado de un cable, y se
anota en 'Bloqueo Engastado DE/PARA' el id de la propuesta que lo puso: así se
distingue de los '*' que trae el Excel de origen o pone Mangueras, y revertir
solo quita los suyos.

Cada bloqueo se identifica por lo que el operario ve (código, marca, elemento,
serie, terminal y lado), no por la fila: la fila es una pista que deja de
valer en cuanto llega una ED nueva con filas insertadas.
"""
import io

from app.excel_manager import _serie_str
from app.mangueras_editor import _abrir, _columna_escritura, _texto, _valor

LADOS = {
    'de': ('De Elemento', 'De Terminal', 'Bloqueo Engastado DE'),
    'para': ('Para Elemento', 'Para Terminal', 'Bloqueo Engastado PARA'),
}
CAMPOS_IDENTIDAD = ('terminal', 'cod_cable', 'cable_marca', 'elemento', 'serie')


def _normalizar(valor):
    texto = _texto(valor)
    return '' if texto.lower() in ('nan', 'none') else ' '.join(texto.split()).upper()


def _identidad_fila(hoja, columnas, fila, lado):
    cabecera_elemento, cabecera_terminal, _ = LADOS[lado]
    return {
        'lado': lado,
        'terminal': _normalizar(_valor(hoja, columnas, fila, cabecera_terminal)),
        'cod_cable': _normalizar(_valor(hoja, columnas, fila, 'Cod. cable')),
        'cable_marca': _normalizar(_valor(hoja, columnas, fila, 'Cable / Marca') or
                                   _valor(hoja, columnas, fila, 'De Marca')),
        'elemento': _normalizar((_valor(hoja, columnas, fila, 'De Elemento Etiquetas') or
                                 _valor(hoja, columnas, fila, 'De Elemento')).rstrip('*')),
        'serie': _normalizar(_serie_str(_valor(hoja, columnas, fila, 'Series'))),
        'elemento_lado': _valor(hoja, columnas, fila, cabecera_elemento),
    }


def _coincide(identidad, regla):
    return identidad['lado'] == regla['lado'] and \
        all(identidad[campo] == _normalizar(regla.get(campo)) for campo in CAMPOS_IDENTIDAD)


def _localizar(hoja, columnas, regla):
    """Fila del cable de la regla: la pista si sigue cuadrando, si no la única
    que cuadre. Devuelve (fila, None) o (None, 'no_encontrado' | 'ambiguo')."""
    lado = regla['lado']
    pista = regla.get('fila')
    if type(pista) is int and 2 <= pista <= hoja.max_row and \
            _coincide(_identidad_fila(hoja, columnas, pista, lado), regla):
        return pista, None
    candidatas = [fila for fila in range(2, hoja.max_row + 1)
                  if _coincide(_identidad_fila(hoja, columnas, fila, lado), regla)]
    if len(candidatas) == 1:
        return candidatas[0], None
    return None, 'ambiguo' if candidatas else 'no_encontrado'


def leer_cable(contenido, nombre, fila, lado, terminal):
    """Identidad del cable que el operario ha marcado, leída del Excel y no del
    navegador. ValueError si la fila ya no lleva ese terminal en ese lado."""
    if lado not in LADOS:
        raise ValueError('Lado no válido.')
    libro, hoja, columnas = _abrir(contenido, nombre)
    try:
        if type(fila) is not int or not 2 <= fila <= hoja.max_row:
            raise ValueError('El cable ya no está en el Excel. Vuelve a abrir el paquete.')
        identidad = _identidad_fila(hoja, columnas, fila, lado)
        if not identidad['terminal'] or identidad['terminal'] != _normalizar(terminal):
            raise ValueError('El Excel ha cambiado. Vuelve a abrir el paquete.')
        if identidad.pop('elemento_lado').endswith('*'):
            raise ValueError(f"El cable {identidad['cable_marca']} ya no lleva este terminal.")
        if not identidad['cod_cable'] or not identidad['cable_marca']:
            raise ValueError('Ese cable no tiene código o marca en el Excel.')
        identidad['fila'] = fila
        return identidad
    finally:
        libro.close()


def aplicar_bloqueos(contenido, nombre, reglas):
    """Pone el '*' de cada regla (dict con identidad, 'fila' y 'propuesta_id').

    Devuelve (bytes, resultados): un dict por regla con 'fila' y 'resultado'
    ('aplicado', 'ya_bloqueado', 'no_encontrado' o 'ambiguo'). 'ya_bloqueado'
    cuenta como aplicado: el terminal ya no se pide, lo haya puesto quien sea.
    """
    libro, hoja, columnas = _abrir(contenido, nombre)
    try:
        resultados = []
        for regla in reglas:
            fila, fallo = _localizar(hoja, columnas, regla)
            if fallo:
                resultados.append({'fila': None, 'resultado': fallo})
                continue
            cabecera_elemento, _, cabecera_marca = LADOS[regla['lado']]
            elemento = _valor(hoja, columnas, fila, cabecera_elemento)
            if elemento.endswith('*'):
                resultados.append({'fila': fila, 'resultado': 'ya_bloqueado'})
                continue
            if regla['lado'] == 'de' and not elemento:
                elemento = _valor(hoja, columnas, fila, 'De Elemento Etiquetas')
            hoja.cell(fila, _columna_escritura(hoja, columnas, cabecera_elemento), elemento + '*')
            celda = hoja.cell(fila, _columna_escritura(hoja, columnas, cabecera_marca))
            celda.value = str(regla['propuesta_id'])
            celda.data_type = 's'
            resultados.append({'fila': fila, 'resultado': 'aplicado'})
        salida = io.BytesIO()
        libro.save(salida)
        return salida.getvalue(), resultados
    finally:
        libro.close()


def quitar_bloqueos(contenido, nombre, reglas):
    """Quita el '*' de cada regla, pero solo si lo puso su propuesta.

    Devuelve (bytes, resultados) con 'revertido', 'no_aplicable' (el '*' ya no
    está o lo puso otro), 'no_encontrado' o 'ambiguo'.
    """
    libro, hoja, columnas = _abrir(contenido, nombre)
    try:
        resultados = []
        for regla in reglas:
            fila, fallo = _localizar(hoja, columnas, regla)
            if fallo:
                resultados.append({'fila': None, 'resultado': fallo})
                continue
            cabecera_elemento, _, cabecera_marca = LADOS[regla['lado']]
            elemento = _valor(hoja, columnas, fila, cabecera_elemento)
            marca = _valor(hoja, columnas, fila, cabecera_marca)
            if not elemento.endswith('*') or marca != str(regla['propuesta_id']):
                resultados.append({'fila': fila, 'resultado': 'no_aplicable'})
                continue
            hoja.cell(fila, _columna_escritura(hoja, columnas, cabecera_elemento), elemento[:-1].rstrip())
            hoja.cell(fila, _columna_escritura(hoja, columnas, cabecera_marca)).value = None
            resultados.append({'fila': fila, 'resultado': 'revertido'})
        salida = io.BytesIO()
        libro.save(salida)
        return salida.getvalue(), resultados
    finally:
        libro.close()
