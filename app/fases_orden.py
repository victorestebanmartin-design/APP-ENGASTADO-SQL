"""Fases previas de una orden: preparación de mangueras y colocación de manguitos.

Una orden solo puede ir a un carro (y de ahí a un bono) cuando las dos están
terminadas: el operario pulsó «Terminar» en Mangueras y en Manguitos, lo que
pone ``fin`` en ``mangueras_preparaciones`` y ``manguitos_colocaciones``.
"""
from sqlalchemy import text

_FASES = (
    ('mangueras', 'mangueras_preparaciones', 'la preparación de mangueras'),
    ('manguitos', 'manguitos_colocaciones', 'la colocación de manguitos'),
)


def fases_terminadas(conn, orden_ids):
    """{orden_id: {'mangueras': bool, 'manguitos': bool}} para esas órdenes."""
    ids = list(orden_ids)
    resultado = {i: {nombre: False for nombre, _, _ in _FASES} for i in ids}
    for nombre, tabla, _ in _FASES:
        for (orden_id,) in conn.execute(text(f'SELECT orden_id FROM {tabla} WHERE fin IS NOT NULL')):
            if orden_id in resultado:
                resultado[orden_id][nombre] = True
    return resultado


def motivo_fases_pendientes(conn, orden):
    """Texto con lo que falta por terminar en la orden, o None si está todo."""
    estado = fases_terminadas(conn, [orden['id']])[orden['id']]
    faltan = [texto for nombre, _, texto in _FASES if not estado[nombre]]
    if not faltan:
        return None
    return (f"La orden {orden['numero']} aún no tiene terminada {' ni '.join(faltan)}. "
            'Termínala antes de asignarle un carro.')
