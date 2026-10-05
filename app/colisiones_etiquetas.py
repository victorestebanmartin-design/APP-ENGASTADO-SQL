"""
Etiquetas que la máquina de corte junta en un solo paquete.

La máquina agrupa por (código de cable, elemento) sin mirar la serie. Si el
mismo elemento con el mismo cable está en dos etiquetas (en la serie 1 y en la
serie 2, o en una serie y suelto), sale un único paquete físico para todas.

Solución: una etiqueta «principal» se queda en la zona normal de la hoja (la
que pega el cortador) y las demás pasan a «reserva», al final de la hoja, para
reetiquetar antes del guiado de manguitos. La hoja de etiquetas y el aviso del
guiado usan esta misma función: tienen que coincidir siempre en cuál es la
principal.
"""

COD_GRUPO_SERIE = 'GRUPO_SERIE'


def etiqueta_texto(numero, sub_numero):
    """'1.07' para una sub-etiqueta de serie, '24' para una suelta."""
    try:
        sub = int(sub_numero or 0)
    except (TypeError, ValueError):
        sub = 0
    return f"{numero}.{str(sub).zfill(2)}" if sub > 0 else str(numero)


def _orden(e):
    try:
        return (int(e.get('numero_etiqueta') or 0), int(e.get('sub_numero') or 0))
    except (TypeError, ValueError):
        return (0, 0)


def _num_cables(e):
    try:
        return int(e.get('num_cables') or 0)
    except (TypeError, ValueError):
        return 0


def _en_serie(e):
    return bool(str(e.get('grupo_serie') or '').strip())


def detectar_colisiones(etiquetas):
    """
    etiquetas: dicts con numero_etiqueta, sub_numero, cod_cable, elemento,
    num_cables (las filas de etiquetas_elementos).

    Devuelve [{'cod_cable', 'elemento', 'principal', 'reservas'}] solo para los
    grupos (cable, elemento) con más de una etiqueta, ordenados por la
    principal. La principal es la que está fuera de toda serie (la etiqueta
    suelta predomina); si no hay, la que lleva más cables (así se reetiqueta
    lo mínimo) y, a igualdad, la de número más bajo. Las etiquetas-cabecera
    de serie (GRUPO_SERIE) no son un paquete de cable y no cuentan.
    """
    grupos = {}
    for e in etiquetas:
        cod = str(e.get('cod_cable') or '').strip().upper()
        elem = str(e.get('elemento') or '').strip()
        if not cod or cod == COD_GRUPO_SERIE or not elem:
            continue
        grupos.setdefault((cod, elem), []).append(e)

    colisiones = []
    for (cod, elem), miembros in grupos.items():
        if len(miembros) < 2:
            continue
        ordenados = sorted(miembros, key=lambda e: (1 if _en_serie(e) else 0, -_num_cables(e)) + _orden(e))
        principal = ordenados[0]
        reservas = sorted(ordenados[1:], key=_orden)
        colisiones.append({'cod_cable': cod, 'elemento': elem,
                           'principal': principal, 'reservas': reservas})
    colisiones.sort(key=lambda c: _orden(c['principal']))
    return colisiones
