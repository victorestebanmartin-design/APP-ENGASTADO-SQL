"""Tiempos de mangueras y manguitos por orden, y su media.

Lee lo que fichan mangueras_trabajo.py y manguitos_trabajo.py. Una fase cuenta
para la media solo si esta acabada:

- el operario la dio por terminada (``fin``), o
- la orden ya ha empezado el engastado (se engasto el primer terminal, sea cual
  sea): si hay terminales hechos, mangueras y manguitos tienen que estar hechos
  aunque nadie pulsara «Terminar».

Las ordenes sin ninguna fila (de antes de poner el sistema) no salen, y las
fases a medias no entran en la media.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from flask import jsonify, render_template
from sqlalchemy import text

from app.routes.base import _ruta_progreso_bono, bp, db, error_interno

_FASES = (
    ('mangueras', 'mangueras_preparaciones', 'mangueras_tramos'),
    ('manguitos', 'manguitos_colocaciones', 'manguitos_tramos'),
)


def _carros_con_actividad(progreso):
    """Claves de carro (str) en las que algun terminal ya se ha tocado."""
    carros = set()
    for datos in progreso.values():
        if not isinstance(datos, dict):
            continue
        carros.update(str(c) for c in datos.get('carros_completados') or [])
        for campo in ('carros_registro', 'carros_con_pendientes', 'paquetes_saltados_por_carro'):
            carros.update(str(c) for c in (datos.get(campo) or {}))
    return carros


def _ordenes_con_engastado_iniciado(conn):
    """Ids de las ordenes en las que ya se ha engastado algun terminal.

    La clave de carro sigue la misma regla que el report de trazabilidad
    (app/routes/reports.py:report_carros_bono): el puesto del carro en el bono,
    o su numero fisico si el bono numera asi.
    """
    iniciadas = set(conn.execute(text(
        "SELECT id FROM ordenes_produccion WHERE estado IN ('completado', 'finalizado')"
    )).scalars())
    for bono in conn.execute(text('SELECT id, nombre, numeracion_carros FROM bonos')).mappings().all():
        ruta = _ruta_progreso_bono(bono['nombre'])
        if not os.path.exists(ruta):
            continue
        try:
            with open(ruta, 'r', encoding='utf-8') as fichero:
                carros = _carros_con_actividad(json.load(fichero))
        except (OSError, ValueError):
            continue
        ordenes = conn.execute(text(
            'SELECT id, carro_numero FROM ordenes_produccion WHERE bono_id=:bono ORDER BY fecha_creacion'
        ), {'bono': bono['id']}).mappings().all()
        for posicion, orden in enumerate(ordenes, start=1):
            clave = (orden['carro_numero'] or posicion) if bono['numeracion_carros'] == 'fisica' else posicion
            if str(clave) in carros:
                iniciadas.add(orden['id'])
    return iniciadas


def _fase_por_orden(conn, tabla_fase, tabla_tramos, engastadas):
    """{orden_id: datos de la fase} para las ordenes que tienen fila."""
    ahora = datetime.now(timezone.utc)
    limite = (ahora - timedelta(minutes=2)).isoformat()
    fases = {fila['orden_id']: {'inicio': fila['inicio'], 'fin': fila['fin'], 'segundos': 0,
                                'operarios': [], 'abierto': False}
             for fila in conn.execute(text(f'SELECT orden_id, inicio, fin FROM {tabla_fase}')).mappings()}
    for tramo in conn.execute(text(
        f'SELECT orden_id, operario_nombre, inicio, fin, ultimo_latido FROM {tabla_tramos} ORDER BY inicio, id'
    )).mappings():
        fase = fases.get(tramo['orden_id'])
        if fase is None:
            continue
        if tramo['fin']:
            final = datetime.fromisoformat(tramo['fin'])
        elif tramo['ultimo_latido'] < limite:
            final = datetime.fromisoformat(tramo['ultimo_latido'])
        else:
            final = ahora
            fase['abierto'] = True
        fase['segundos'] += max(0, int((final - datetime.fromisoformat(tramo['inicio'])).total_seconds()))
        if tramo['operario_nombre'] not in fase['operarios']:
            fase['operarios'].append(tramo['operario_nombre'])
    for orden_id, fase in fases.items():
        if fase['fin']:
            fase['estado'] = 'terminada'
        elif orden_id in engastadas:
            fase['estado'] = 'terminada_auto'
        else:
            fase['estado'] = 'en_curso' if fase['abierto'] else 'pausada'
        fase['cuenta'] = fase['estado'] in ('terminada', 'terminada_auto') and fase['segundos'] > 0
        del fase['abierto']
    return fases


def _media(filas, fase):
    contadas = [(fila[fase]['segundos'], fila['cantidad']) for fila in filas if fila[fase] and fila[fase]['cuenta']]
    if not contadas:
        return {'ordenes': 0, 'media_segundos': None, 'segundos_por_unidad': None}
    segundos = sum(s for s, _ in contadas)
    unidades = sum(c for _, c in contadas)
    return {'ordenes': len(contadas), 'media_segundos': round(segundos / len(contadas)),
            'segundos_por_unidad': round(segundos / unidades) if unidades else None}


@bp.route('/ordenes/tiempos')
def tiempos_ordenes():
    return render_template('ordenes-tiempos.html')


@bp.route('/api/ordenes/tiempos', methods=['GET'])
def api_tiempos_ordenes():
    try:
        with db.engine.connect() as conn:
            engastadas = _ordenes_con_engastado_iniciado(conn)
            fases = {nombre: _fase_por_orden(conn, tabla, tramos, engastadas) for nombre, tabla, tramos in _FASES}
            ordenes = conn.execute(text(
                'SELECT o.id, o.numero, o.codigo_corte, o.proyecto, o.cantidad, o.estado, b.nombre AS bono '
                'FROM ordenes_produccion o LEFT JOIN bonos b ON b.id=o.bono_id'
            )).mappings().all()
        filas = []
        for orden in ordenes:
            fila = {'id': orden['id'], 'numero': orden['numero'], 'codigo_corte': orden['codigo_corte'],
                    'proyecto': orden['proyecto'], 'cantidad': orden['cantidad'] or 1,
                    'estado': orden['estado'], 'bono': orden['bono'],
                    'engastado_iniciado': orden['id'] in engastadas}
            for nombre in fases:
                fila[nombre] = fases[nombre].get(orden['id'])
            if fila['mangueras'] or fila['manguitos']:
                filas.append(fila)
        filas.sort(key=lambda f: (f['mangueras'] or f['manguitos'])['inicio'], reverse=True)
        completas = [f for f in filas if f['mangueras'] and f['mangueras']['cuenta']
                     and f['manguitos'] and f['manguitos']['cuenta']]
        total = {'ordenes': len(completas),
                 'media_segundos': round(sum(f['mangueras']['segundos'] + f['manguitos']['segundos']
                                             for f in completas) / len(completas)) if completas else None}
        return jsonify(success=True, ordenes=filas, medias={
            'mangueras': _media(filas, 'mangueras'), 'manguitos': _media(filas, 'manguitos'), 'total': total})
    except Exception as exc:
        return error_interno(exc)
