"""Limpieza prudente de órdenes con el número repetido.

Hasta la 1.31.1 se podían crear dos órdenes con el mismo número, y al montar un
bono (que asigna por número) se iban las dos a él. Crear ya lo impide; esto
arregla las que quedaron, al arrancar el servidor.

Solo se borra lo que es claramente una copia sobrante. Una orden se borra si:

* hay otra con el **mismo número y el mismo código de corte** que se queda, y
* está ``pendiente``, sin bono y sin carro, y
* nada cuelga de ella: ni proyecto en un carro, ni etiquetas, ni trabajo de
  mangueras o manguitos, ni sesiones de engastado, ni ensayos.

Si todas las copias de un grupo están así de vacías, se queda la más antigua.
Lo demás (mismo número con distinto corte, o copias con trabajo hecho) no se
toca: decidir cuál vale es cosa de una persona, y aquí solo se deja escrito en
el log. Antes de borrar se guarda una copia de la base de datos en ``data/``,
con un nombre que Admin → Sistema reconoce para restaurarla.
"""
import os
import sqlite3
from contextlib import closing
from datetime import datetime

# Tablas con una columna orden_id: si alguna tiene filas de la orden, esa orden
# ya ha servido para algo y no se borra sola.
_DEPENDIENTES = (
    'proyectos', 'etiquetas_elementos', 'mangueras_preparaciones', 'mangueras_tramos',
    'manguitos_colocaciones', 'manguitos_tramos', 'sesiones_trabajo', 'ensayos_traccion',
)


def _tablas_con_orden_id(conn):
    tablas = []
    for tabla in _DEPENDIENTES:
        columnas = {fila[1] for fila in conn.execute(f'PRAGMA table_info({tabla})')}
        if 'orden_id' in columnas:
            tablas.append(tabla)
    return tablas


def _esta_vacia(conn, orden, tablas):
    """True si la orden no ha llegado a usarse para nada."""
    if orden['estado'] != 'pendiente' or orden['bono_id'] or orden['carro_numero'] is not None:
        return False
    for tabla in tablas:
        if conn.execute(f'SELECT 1 FROM {tabla} WHERE orden_id = ? LIMIT 1', (orden['id'],)).fetchone():
            return False
    return True


def analizar(conn):
    """Devuelve (a_borrar, a_revisar): las órdenes sobrantes que se pueden
    borrar sin perder nada, y los números que siguen repetidos y necesitan que
    alguien decida. No modifica nada."""
    conn.row_factory = sqlite3.Row
    filas = conn.execute("""
        SELECT rowid AS fila, id, TRIM(numero) AS numero, TRIM(codigo_corte) AS codigo_corte,
               estado, bono_id, carro_numero, fecha_creacion
        FROM ordenes_produccion
        WHERE TRIM(numero) IN (SELECT TRIM(numero) FROM ordenes_produccion
                               GROUP BY TRIM(numero) HAVING COUNT(*) > 1)
        ORDER BY fecha_creacion, rowid
    """).fetchall()
    if not filas:
        return [], []

    tablas = _tablas_con_orden_id(conn)
    por_numero = {}
    for orden in filas:
        por_numero.setdefault(orden['numero'], []).append(orden)

    a_borrar, a_revisar = [], []
    for numero, ordenes in por_numero.items():
        quedan = len(ordenes)
        por_corte = {}
        for orden in ordenes:
            por_corte.setdefault(orden['codigo_corte'], []).append(orden)
        for copias in por_corte.values():
            if len(copias) < 2:
                continue
            vacias = [o for o in copias if _esta_vacia(conn, o, tablas)]
            # Si todas están vacías, la más antigua (la primera) se queda.
            sobrantes = vacias[1:] if len(vacias) == len(copias) else vacias
            a_borrar.extend(sobrantes)
            quedan -= len(sobrantes)
        if quedan > 1:
            a_revisar.append((numero, quedan))
    return a_borrar, a_revisar


def _copia_previa(db_path):
    """Copia de la BD antes de borrar, junto a ella. El nombre empieza por
    'engastado' y lleva 'backup' para que salga en Admin → Sistema."""
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(os.path.dirname(os.path.abspath(db_path)),
                           f'engastado_backup_antes_duplicadas_{sello}.db')
    with closing(sqlite3.connect(db_path)) as src, closing(sqlite3.connect(destino)) as dst:
        src.backup(dst)
    return destino


def limpiar(db_path, logger):
    """Borra las órdenes duplicadas sobrantes y deja en el log las que hay que
    revisar a mano. Devuelve cuántas ha borrado. Se puede llamar en cada
    arranque: sin duplicadas no hace nada."""
    with closing(sqlite3.connect(db_path)) as conn:
        a_borrar, a_revisar = analizar(conn)
        if a_borrar:
            copia = _copia_previa(db_path)
            with conn:
                for orden in a_borrar:
                    conn.execute('DELETE FROM ordenes_produccion WHERE id = ?', (orden['id'],))
            logger.warning(
                'Ordenes duplicadas: borradas %d copias sobrantes (pendientes y sin usar): %s. '
                'Copia previa de la base de datos: %s',
                len(a_borrar),
                ', '.join(sorted({o['numero'] for o in a_borrar})),
                copia)
        for numero, cuantas in a_revisar:
            logger.warning(
                'Ordenes duplicadas: el numero %s sigue en %d ordenes con trabajo hecho o '
                'distinto codigo de corte. No se tocan: revisalas en la pantalla de Ordenes '
                '(borrar la que sobre o cambiarle el numero).', numero, cuantas)
    return len(a_borrar)
