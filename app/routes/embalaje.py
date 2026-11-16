"""
Rutas de Embalaje (la lógica está en app/embalaje.py).

Se entra desde engastado con el botón EMBALAJE: el operario pasa su tarjeta,
elige el bono y, en cada orden terminada, ve en cuántas cajas va y qué lleva
cada una. Los carteles salen por la impresora de red de las etiquetas.

Las identificaciones con tarjeta reutilizan la captura armada del lector
(operario_tag_capturas), como el supervisor de ensayos: no hace falta
firmware nuevo en las placas.
"""
import io
import os
import time
import uuid
from datetime import datetime, timedelta
from html import escape

from flask import request, jsonify, current_app, session, send_file
from sqlalchemy import text

from app import embalaje
from app.auth import verificar_credenciales_personales
from app.routes.base import bp, db, error_interno, operario_puede

TIPO_CAPTURA_OPERARIO = 'operario_embalaje'
TIPO_CAPTURA_SUPERVISOR = 'supervisor_ensayo'   # la misma que ensayos: mismo permiso
SEGUNDOS_TARJETA = 120
MINUTOS_AUTORIZACION = 15
DIAS_BONOS_CERRADOS = 30


def _rechazo(err):
    return jsonify(err.como_json()), err.status


def _ahora():
    return datetime.now()


# ==================== estado de las órdenes ====================

def _carro_key(bono, orden, idx):
    """Mismo número de carro que usan engastado, el report y el ponderado."""
    if bono.get('numeracion_carros') == 'fisica':
        return str(orden.get('carro_numero') or idx + 1)
    return str(idx + 1)


def _ordenes_con_estado(bono, progreso=None):
    """Órdenes del bono con su estado de embalaje, en orden de carro."""
    from repositories.orden_repository import OrdenRepository
    from app.routes.progreso import (leer_progreso, _crimps_por_terminal_archivo,
                                     _terminales_trabajables, _terminales_ignorados,
                                     _terminal_descartado)
    if progreso is None:
        progreso = leer_progreso(bono['nombre'])
    ignorados = _terminales_ignorados()
    cache = {}
    resultado = []
    for idx, orden in enumerate(OrdenRepository(db).obtener_ordenes_por_bono(bono['id'])):
        archivo = orden.get('archivo_excel')
        cerrada = orden.get('estado') == 'completado' or bono.get('estado') == 'completado'
        terminales = None
        if archivo and not cerrada:
            if archivo not in cache:
                lados = None
                if os.path.exists(os.path.join(current_app.config['UPLOAD_FOLDER'], archivo)):
                    lados = _crimps_por_terminal_archivo(archivo)
                cache[archivo] = None if lados is None else _terminales_trabajables(set(lados))
            terminales = cache[archivo]
        carro = _carro_key(bono, orden, idx)
        est = embalaje.estado_orden_desde_progreso(
            terminales, progreso, carro, cerrada,
            descartado=lambda t: _terminal_descartado(t, ignorados))
        if not archivo:
            est = {'estado': 'incompleta', 'motivo': 'La orden no tiene Excel de corte',
                   'faltan': [], 'pendientes': []}
        resultado.append({'orden': orden, 'carro': carro, **est})
    return resultado


def _bono_por_nombre(nombre):
    from repositories.bono_repository import BonoRepository
    bono = BonoRepository(db).obtener_bono_por_nombre(nombre)
    if not bono:
        raise embalaje.EmbalajeError(f'No se encuentra el bono {nombre}',
                                     'Revisa el código del bono', 404)
    return bono


def _bonos_candidatos():
    """Bonos activos y los cerrados hace poco: lo que se puede estar embalando."""
    limite = (_ahora() - timedelta(days=DIAS_BONOS_CERRADOS)).strftime('%Y-%m-%d')
    with db.engine.connect() as conn:
        return [dict(f) for f in conn.execute(text("""
            SELECT b.* FROM bonos b
            WHERE b.estado = 'activo'
               OR EXISTS (SELECT 1 FROM ordenes_produccion o
                          WHERE o.bono_id = b.id AND o.fecha_completado >= :lim)
            ORDER BY b.fecha_creacion DESC
        """), {'lim': limite}).mappings().all()]


def _embalada(conn, orden_id):
    return embalaje.ultimo_embalaje(conn, orden_id)


@bp.route('/api/embalaje/disponible', methods=['GET'])
def api_embalaje_disponible():
    """¿Hay alguna orden terminada que embalar? Enciende el botón EMBALAJE."""
    try:
        for bono in _bonos_candidatos():
            if any(o['estado'] != 'incompleta' for o in _ordenes_con_estado(bono)):
                return jsonify({'success': True, 'disponible': True})
        return jsonify({'success': True, 'disponible': False,
                        'motivo': 'Todavía no hay ninguna orden terminada'})
    except Exception:
        # El botón no puede tumbar engastado: si esto falla, se queda apagado.
        current_app.logger.exception('No se pudo calcular si hay órdenes para embalar')
        return jsonify({'success': True, 'disponible': False,
                        'motivo': 'No se ha podido comprobar'})


@bp.route('/api/embalaje/bonos', methods=['GET'])
def api_embalaje_bonos():
    """Bonos con alguna orden terminada, con el recuento de cada estado."""
    try:
        bonos = []
        with db.engine.connect() as conn:
            for bono in _bonos_candidatos():
                ordenes = _ordenes_con_estado(bono)
                listas = [o for o in ordenes if o['estado'] != 'incompleta']
                if not listas:
                    continue
                bonos.append({
                    'nombre': bono['nombre'],
                    'estado': bono['estado'],
                    'fecha_creacion': bono['fecha_creacion'],
                    'total': len(ordenes),
                    'listas': len(listas),
                    'embaladas': sum(1 for o in listas if _embalada(conn, o['orden']['id'])),
                })
        return jsonify({'success': True, 'bonos': bonos})
    except Exception as e:
        return error_interno(e)


def _resumen_orden(conn, item):
    orden = item['orden']
    reparto = embalaje.reparto_activo(conn, orden.get('codigo_corte') or '')
    return {
        'id': orden['id'],
        'numero': orden.get('numero') or '',
        'codigo_corte': orden.get('codigo_corte') or '',
        'descripcion': _denominacion(conn, orden),
        'cantidad': orden.get('cantidad'),
        'carro': item['carro'],
        'estado': item['estado'],
        'motivo': item['motivo'],
        'embalada': _embalada(conn, orden['id']),
        'reparto': ({'num_cajas': reparto['num_cajas'], 'cantidad_ref': reparto['cantidad_ref']}
                    if reparto else None),
    }


@bp.route('/api/embalaje/bono/<path:nombre>', methods=['GET'])
def api_embalaje_bono(nombre):
    try:
        bono = _bono_por_nombre(nombre)
        with db.engine.connect() as conn:
            ordenes = [_resumen_orden(conn, o) for o in _ordenes_con_estado(bono)]
        return jsonify({'success': True, 'bono': {'nombre': bono['nombre'], 'estado': bono['estado']},
                        'ordenes': ordenes})
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


# ==================== una orden ====================

def _denominacion(conn, orden):
    """Lo que se lee en el cartel bajo el código de corte."""
    for campo in ('descripcion', 'proyecto'):
        valor = (orden.get(campo) or '').strip()
        if valor:
            return valor
    fila = conn.execute(text("SELECT proyecto_nombre FROM codigos_cortes WHERE codigo = :c"),
                        {'c': orden.get('codigo_corte') or ''}).fetchone()
    return (fila[0] or '').strip() if fila else ''


def _orden_y_estado(orden_id):
    """(bono, item de _ordenes_con_estado) de esa orden."""
    from repositories.orden_repository import OrdenRepository
    from repositories.bono_repository import BonoRepository
    orden = OrdenRepository(db).obtener_orden(orden_id)
    if not orden:
        raise embalaje.EmbalajeError('No se encuentra la orden', 'Vuelve a la lista de órdenes', 404)
    bono = BonoRepository(db).obtener_bono(orden['bono_id']) if orden.get('bono_id') else None
    if not bono:
        raise embalaje.EmbalajeError('La orden no está en ningún bono',
                                     'Solo se embalan órdenes de un bono', 409)
    item = next(o for o in _ordenes_con_estado(bono) if o['orden']['id'] == orden_id)
    return bono, item


def _asegurar_paquetes(orden):
    """Paquetes del Excel de la orden. Si sus etiquetas aún no se han
    generado, se generan (como al abrir el archivo en Etiquetas)."""
    archivo = orden.get('archivo_excel') or ''
    with db.engine.connect() as conn:
        paquetes = embalaje.paquetes_de_archivo(conn, archivo)
    if not paquetes and archivo:
        from app.routes.base import _ruta_upload_segura
        from app.routes.etiquetas import _regenerar_etiquetas_archivo
        ruta = _ruta_upload_segura(archivo)
        if not ruta or not os.path.exists(ruta):
            raise embalaje.EmbalajeError('No se encuentra el Excel de la orden',
                                         'Avisa a oficina: falta el archivo de corte', 409)
        _regenerar_etiquetas_archivo(archivo, ruta)
        with db.engine.connect() as conn:
            paquetes = embalaje.paquetes_de_archivo(conn, archivo)
    if not paquetes:
        raise embalaje.EmbalajeError('La orden no tiene paquetes', 'Revisa el Excel de la orden', 409)
    with db.engine.connect() as conn:
        obs = embalaje.observaciones(conn, orden.get('codigo_corte') or '')
    for p in paquetes:
        p['observacion'] = obs.get(p['clave'], '')
    return paquetes


def _exigir_embalable(item, orden_id, ya_embalada=False):
    """La orden tiene que estar terminada; con pendientes, con supervisor."""
    if item['estado'] == 'incompleta':
        raise embalaje.EmbalajeError(f"La orden aún no está terminada: {item['motivo'].lower()}",
                                     'Termina de engastarla antes de embalar', 409)
    if item['estado'] == 'pendientes' and not ya_embalada and not _autorizacion(orden_id):
        raise embalaje.EmbalajeError(
            f"La orden tiene paquetes pendientes ({item['motivo']})",
            'Para embalarla así, que la autorice un supervisor', 403, supervisor_requerido=True)


@bp.route('/api/embalaje/orden/<orden_id>', methods=['GET'])
def api_embalaje_orden(orden_id):
    """Todo lo que necesita la pantalla de una orden: paquetes y reparto."""
    try:
        bono, item = _orden_y_estado(orden_id)
        orden = item['orden']
        paquetes = _asegurar_paquetes(orden)
        with db.engine.connect() as conn:
            resumen = _resumen_orden(conn, item)
            reparto = embalaje.reparto_activo(conn, orden.get('codigo_corte') or '')
            nombres = embalaje.nombres_cajas(conn, orden.get('codigo_corte') or '')
        nuevos = []
        if reparto:
            nuevos = [p['clave'] for p in paquetes if p['clave'] not in reparto['asignaciones']]
        return jsonify({
            'success': True,
            'bono': bono['nombre'],
            'orden': resumen,
            'paquetes': paquetes,
            'reparto': ({'num_cajas': reparto['num_cajas'],
                         'cantidad_ref': reparto['cantidad_ref'],
                         'asignaciones': reparto['asignaciones'],
                         'creado_por': reparto['creado_por'],
                         'fecha': reparto['created_at']} if reparto else None),
            'paquetes_nuevos': nuevos,
            'nombres_cajas': {str(k): v for k, v in nombres.items()},
            'cantidad_distinta': bool(reparto) and reparto['cantidad_ref'] is not None
                                  and reparto['cantidad_ref'] != orden.get('cantidad'),
            'autorizado_por': (_autorizacion(orden_id) or {}).get('supervisor'),
        })
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/embalaje/orden/<orden_id>/reparto', methods=['POST'])
def api_embalaje_reparto(orden_id):
    """Guarda en qué caja va cada paquete (para todo el código de corte)."""
    datos = request.get_json(silent=True) or {}
    try:
        _bono, item = _orden_y_estado(orden_id)
        orden = item['orden']
        with db.engine.connect() as conn:
            ya = bool(_embalada(conn, orden_id))
        _exigir_embalable(item, orden_id, ya_embalada=ya)
        paquetes = _asegurar_paquetes(orden)
        aut = _autorizacion(orden_id) or {}
        with db.engine.begin() as conn:
            reparto, cambio = embalaje.guardar_reparto(
                conn, orden.get('codigo_corte') or '', paquetes,
                datos.get('num_cajas'), datos.get('asignaciones'),
                cantidad=orden.get('cantidad'), operario=_operario(datos), orden_id=orden_id,
                supervisor=aut.get('supervisor'), supervisor_via=aut.get('via'))
        return jsonify({'success': True, 'cambio': cambio,
                        'reparto': {'num_cajas': reparto['num_cajas'],
                                    'asignaciones': reparto['asignaciones']}})
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/embalaje/orden/<orden_id>/observacion', methods=['POST'])
def api_embalaje_observacion(orden_id):
    """Pone o quita la observación de un paquete ({clave, texto}). Es una
    instrucción para quien embala: la autoriza un supervisor."""
    datos = request.get_json(silent=True) or {}
    try:
        _bono, item = _orden_y_estado(orden_id)
        orden = item['orden']
        clave = (datos.get('clave') or '').strip()
        if clave not in {p['clave'] for p in _asegurar_paquetes(orden)}:
            raise embalaje.EmbalajeError('Ese paquete no es de esta orden', 'Vuelve a abrir la orden', 400)
        aut = _exigir_supervisor(orden_id, 'Poner o cambiar una observación necesita un supervisor')
        with db.engine.begin() as conn:
            texto = embalaje.guardar_observacion(conn, orden.get('codigo_corte') or '', clave,
                                                 datos.get('texto'), _operario(datos), aut['supervisor'])
        return jsonify({'success': True, 'clave': clave, 'observacion': texto})
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/embalaje/orden/<orden_id>/caja_nombre', methods=['POST'])
def api_embalaje_caja_nombre(orden_id):
    """Pone o quita el nombre de una caja ({caja, nombre}). Lo autoriza un
    supervisor, como las observaciones."""
    datos = request.get_json(silent=True) or {}
    try:
        _bono, item = _orden_y_estado(orden_id)
        codigo = item['orden'].get('codigo_corte') or ''
        aut = _exigir_supervisor(orden_id, 'Poner o cambiar el nombre de una caja necesita un supervisor')
        with db.engine.begin() as conn:
            nombre = embalaje.guardar_nombre_caja(conn, codigo, datos.get('caja'),
                                                  datos.get('nombre'), _operario(datos), aut['supervisor'])
        return jsonify({'success': True, 'caja': int(datos.get('caja')), 'nombre': nombre})
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


def _exigir_supervisor(orden_id, motivo):
    aut = _autorizacion(orden_id)
    if not aut:
        raise embalaje.EmbalajeError(motivo, 'Que un supervisor pase su tarjeta o ponga su clave',
                                     403, supervisor_requerido=True)
    return aut


def _operario(datos):
    return ((datos.get('operario') or '').strip() or session.get('operario_actual') or '')[:80]


# ==================== carteles ====================

# Hoja A4 apaisada con 10 mm de margen: 277 x 190 mm útiles. Cabecera y
# datos tienen alto fijo (61 mm con sus márgenes) para que la cuenta sea
# exacta; lo demás es para la rejilla y las observaciones, con margen de
# sobra. Cada paquete es una "etiqueta" de 24x32 mm a escala 1 (como la
# pegatina real): se encoge para que entren todos, pero nunca crece, para
# que todas las cajas salgan iguales.
_REJILLA_ANCHO_MM = 277
_REJILLA_ALTO_MM = 122
_ETQ_ANCHO_MM = 24
_ETQ_ALTO_MM = 32
_ESCALA_MAX = 1.0
_ESCALA_MIN = 0.45

_OBS_FIJO_MM = 13    # recuadro de observaciones: borde, título y márgenes
_OBS_FILA_MM = 6     # cada fila de texto dentro
_OBS_CHARS_ETQ = 26  # caben en la columna de números de etiqueta
_OBS_CHARS_TEXTO = 80


def _grupos_obs(con_obs):
    """[(texto, [paquete, ...])]: la misma observación en varios paquetes va
    en una sola línea, en el orden en que salen en la caja."""
    grupos = {}
    for p in con_obs:
        grupos.setdefault(p['observacion'], []).append(p)
    return list(grupos.items())


def _alto_obs(grupos):
    """mm que ocupa el recuadro de observaciones (por lo alto, con margen)."""
    if not grupos:
        return 0
    filas = 0
    for texto, ps in grupos:
        numeros = ' · '.join(p['etiqueta'] for p in ps)
        filas += max(-(-len(numeros) // _OBS_CHARS_ETQ), -(-len(texto) // _OBS_CHARS_TEXTO), 1)
    return _OBS_FIJO_MM + _OBS_FILA_MM * filas


def _rejilla(n, alto=_REJILLA_ALTO_MM):
    """(columnas, escala) que hace caber n etiquetas en la rejilla lo más
    grandes posible. Por debajo de 0,45 ya no se leen: se deja pasar a otra hoja."""
    mejor = (1, 0)
    for cols in range(1, max(n, 1) + 1):
        filas = -(-n // cols)
        escala = min(_REJILLA_ANCHO_MM / cols / _ETQ_ANCHO_MM,
                     alto / filas / _ETQ_ALTO_MM)
        if escala > mejor[1]:
            mejor = (cols, escala)
    cols, escala = mejor
    if escala >= _ESCALA_MAX:
        # Cabe a tamaño real: las columnas justas para que no sobre una fila
        # casi vacía, sin agrandar las etiquetas.
        escala = _ESCALA_MAX
        cols = min(max(n, 1), int(_REJILLA_ANCHO_MM // _ETQ_ANCHO_MM))
    elif escala < _ESCALA_MIN:
        escala = _ESCALA_MIN
        cols = int(_REJILLA_ANCHO_MM // (_ETQ_ANCHO_MM * escala))
    return cols, escala


def _colores_cable():
    try:
        with db.engine.connect() as conn:
            filas = conn.execute(text("SELECT cod_cable, color_hex, color_texto FROM cable_colores")).fetchall()
        return {r[0]: r[1] for r in filas}, {r[0]: r[2] for r in filas if r[2]}
    except Exception:
        return {}, {}


def _etiqueta_cartel(p, color_map, texto_map):
    """Una celda con la misma cara que la etiqueta pegada al paquete."""
    from app.routes.etiquetas import _get_cable_color
    from app.routes.cable_colores import _text_color_for_bg
    obs = (f"<div class='etq-obs' title='{escape(p['observacion'])}'>*</div>"
           if p.get('observacion') else '')
    if p['es_serie']:
        hijos = [h['etiqueta'] for h in p['contenido']]
        # Con muchos no caben en la etiqueta: de la primera a la última.
        hijos = escape(f'{hijos[0]} → {hijos[-1]}' if len(hijos) > 4 else ' · '.join(hijos))
        return (f"<div class='etq serie'>{obs}"
                f"<div class='etq-top'><div class='etq-num' style='background:#f59e0b;color:#000'>"
                f"★ {escape(p['etiqueta'])}</div>"
                f"<div class='etq-el una'>Serie {escape(p['serie'])}</div></div>"
                f"<div class='etq-bot'><div class='etq-cable'>{len(p['contenido'])} paquetes</div>"
                f"<div class='etq-hijos'>{hijos}</div></div></div>")
    fondo = _get_cable_color(p['cod_cable'], color_map=color_map)
    letra = texto_map.get(str(p['cod_cable']).strip().upper()) or _text_color_for_bg(fondo)
    seccion = f"<div class='etq-sec'>{escape(p['seccion'])}</div>" if p['seccion'] else ''
    return (f"<div class='etq{' con-obs' if obs else ''}'>{obs}"
            f"<div class='etq-top'><div class='etq-num' style='background:{fondo};color:{letra}'>"
            f"{escape(p['etiqueta'])}</div>"
            f"<div class='etq-el'>{escape(p['elemento'])}</div></div>"
            f"<div class='etq-bot'><div class='etq-cable'>{escape(p['cod_cable'])}</div>{seccion}</div></div>")


def _html_carteles(bono, orden, denominacion, paquetes, reparto, cajas_a_imprimir, nombres=None):
    cajas = embalaje.cajas_de(paquetes, reparto)
    nombres = nombres or {}
    total = len(cajas)
    color_map, texto_map = _colores_cable()
    hojas = []
    for n in cajas_a_imprimir:
        contenido = cajas[n - 1]
        grupos = _grupos_obs([p for p in contenido if p.get('observacion')])
        alto = max(_REJILLA_ALTO_MM - _alto_obs(grupos), 40)
        cols, escala = _rejilla(len(contenido), alto)
        lista_obs = ''
        if grupos:
            lista_obs = ('<div class="obs"><h3>* Antes de meterlos en la caja</h3>' + ''.join(
                f"<div class='obs-linea'><b>* {' · '.join(escape(p['etiqueta']) for p in ps)}</b>"
                f"<span>{escape(texto)}</span></div>" for texto, ps in grupos) + '</div>')
        etiquetas = ''.join(_etiqueta_cartel(p, color_map, texto_map) for p in contenido)
        hojas.append(f"""
<section class="hoja">
  <header>
    <div class="ident">
      <div class="corte">{escape(orden.get('codigo_corte') or '')}</div>
      <div class="denominacion">{escape(denominacion)}</div>
    </div>
    <div class="caja"><div>CAJA <b>{n}</b> de {total}</div>{f'<div class="caja-nombre">{escape(nombres[n])}</div>' if nombres.get(n) else ''}</div>
  </header>
  <div class="datos">
    <div><span>Orden</span><b>{escape(str(orden.get('numero') or ''))}</b></div>
    <div><span>Cantidad</span><b>{escape(str(orden.get('cantidad') or ''))}</b></div>
    <div><span>Paquetes en esta caja</span><b>{len(contenido)}</b></div>
    <div class="pie">Bono {escape(bono['nombre'])}<br>{_ahora().strftime('%d/%m/%Y %H:%M')}</div>
  </div>
  <div class="rejilla" style="--s:{escala:.3f};grid-template-columns:repeat({cols}, calc({_ETQ_ANCHO_MM}mm * var(--s)))">{etiquetas}</div>
  {lista_obs}
</section>""")
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Carteles {escape(str(orden.get('numero') or ''))}</title>
<style>
  @page {{ size: A4 landscape; margin: 10mm; }}
  * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #000; }}
  .hoja {{ width: 277mm; page-break-after: always; break-after: page; }}
  .hoja:last-child {{ page-break-after: auto; break-after: auto; }}
  /* Alturas fijas: _REJILLA_ALTO_MM cuenta con ellas (36 + 3 + 3 + 16 + 3 mm). */
  header {{ display: flex; align-items: stretch; gap: 6mm; height: 36mm; overflow: hidden;
            border-bottom: 3px solid #000; padding-bottom: 2mm; }}
  .ident {{ flex: 1; min-width: 0; overflow: hidden; }}
  .corte {{ font-size: 50pt; font-weight: bold; line-height: 1; letter-spacing: 1px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .denominacion {{ font-size: 18pt; line-height: 1.15; margin-top: 2mm; overflow: hidden;
                   display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
  .caja {{ border: 4px solid #000; padding: 1mm 6mm; font-size: 24pt; white-space: nowrap; line-height: 1;
           display: flex; flex-direction: column; align-items: center; justify-content: center;
           gap: 1.5mm; max-width: 120mm; }}
  .caja b {{ font-size: 54pt; }}
  .caja-nombre {{ font-size: 20pt; font-weight: bold; text-align: center; border-top: 2px solid #000;
                  padding-top: 1.5mm; width: 100%; overflow: hidden; text-overflow: ellipsis; }}
  .datos {{ display: flex; gap: 5mm; margin: 3mm 0; height: 16mm; align-items: stretch; }}
  .datos > div {{ border: 2px solid #000; padding: 1.5mm 4mm; line-height: 1; }}
  .datos span {{ display: block; font-size: 10pt; text-transform: uppercase; margin-bottom: 1mm; }}
  .datos b {{ font-size: 24pt; }}
  .datos .pie {{ margin-left: auto; border: none; font-size: 10pt; color: #333; text-align: right; align-self: end; }}
  .rejilla {{ display: grid; gap: 0; justify-content: start; }}
  .etq {{ width: calc({_ETQ_ANCHO_MM}mm * var(--s)); height: calc({_ETQ_ALTO_MM}mm * var(--s));
          border: calc(2px * var(--s) + 0.5px) solid #333; display: flex; flex-direction: column;
          overflow: hidden; break-inside: avoid; page-break-inside: avoid; }}
  .etq.serie {{ border-color: #f59e0b; }}
  .etq-top {{ height: 55%; display: flex; flex-direction: column; justify-content: center; align-items: center;
              gap: calc(0.8mm * var(--s)); background: #eef7fd; border-bottom: calc(2px * var(--s) + 0.5px) solid #0ea5e9;
              padding: calc(1mm * var(--s)); }}
  .etq.serie .etq-top {{ border-bottom-color: #f59e0b; }}
  .etq-num {{ font-size: calc(15pt * var(--s)); font-weight: bold; padding: calc(1.2mm * var(--s)) calc(3mm * var(--s));
              border-radius: calc(3mm * var(--s)); white-space: nowrap; }}
  .etq-el {{ font-size: calc(8pt * var(--s)); font-weight: bold; color: #1e40af; text-align: center; line-height: 1.1;
             max-width: 100%; overflow: hidden; word-break: break-word; display: -webkit-box;
             -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
  .etq-el.una {{ -webkit-line-clamp: 1; white-space: nowrap; text-overflow: ellipsis; display: block; }}
  .etq-bot {{ flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center;
              gap: calc(0.5mm * var(--s)); padding: calc(1mm * var(--s)); text-align: center; }}
  .etq-cable {{ font-size: calc(8pt * var(--s)); font-weight: bold; color: #2563eb; word-break: break-all; }}
  .etq-sec {{ font-size: calc(7pt * var(--s)); color: #475569; background: #f1f5f9;
              padding: 0 calc(1.5mm * var(--s)); border-radius: calc(1.5mm * var(--s)); }}
  .etq {{ position: relative; }}
  .etq.con-obs {{ border-color: #dc2626; }}
  .etq-obs {{ position: absolute; top: 0; right: 0; background: #dc2626; color: #fff; font-weight: bold;
              font-size: calc(16pt * var(--s)); line-height: 1; padding: calc(0.6mm * var(--s)) calc(1.4mm * var(--s)) 0;
              border-bottom-left-radius: calc(2mm * var(--s)); }}
  .obs {{ margin-top: 3mm; border: 2px solid #dc2626; padding: 1.5mm 3mm; break-inside: avoid; }}
  .obs h3 {{ margin: 0 0 1mm; font-size: 11pt; color: #dc2626; text-transform: uppercase; }}
  .obs-linea {{ display: grid; grid-template-columns: 62mm 1fr; gap: 4mm; font-size: 12pt; line-height: 6mm; }}
  .obs-linea b {{ color: #dc2626; }}
  .etq-hijos {{ font-size: calc(6.5pt * var(--s)); color: #333; line-height: 1.15; }}
</style></head><body>{''.join(hojas)}</body></html>"""


def _preparar_carteles(orden_id, datos):
    """(bono, item, paquetes, reparto, cajas, html) o EmbalajeError."""
    bono, item = _orden_y_estado(orden_id)
    orden = item['orden']
    paquetes = _asegurar_paquetes(orden)
    with db.engine.connect() as conn:
        reparto = embalaje.reparto_activo(conn, orden.get('codigo_corte') or '')
        denominacion = _denominacion(conn, orden)
        nombres = embalaje.nombres_cajas(conn, orden.get('codigo_corte') or '')
        ya = bool(_embalada(conn, orden_id))
    _exigir_embalable(item, orden_id, ya_embalada=ya)
    if not reparto:
        raise embalaje.EmbalajeError('Esta orden todavía no tiene reparto en cajas',
                                     'Elige el número de cajas y reparte los paquetes', 409)
    sin_caja = [p['etiqueta'] for p in paquetes if p['clave'] not in reparto['asignaciones']]
    if sin_caja:
        raise embalaje.EmbalajeError(
            f'Hay {len(sin_caja)} paquete{"s" if len(sin_caja) > 1 else ""} nuevo{"s" if len(sin_caja) > 1 else ""} sin caja',
            'Asígnalos a una caja antes de imprimir', 409, sin_caja=sin_caja)
    total = int(reparto['num_cajas'])
    pedidas = datos.get('cajas') or list(range(1, total + 1))
    try:
        cajas = sorted({int(c) for c in pedidas if 1 <= int(c) <= total})
    except (TypeError, ValueError):
        cajas = []
    if not cajas:
        raise embalaje.EmbalajeError('No hay cajas que imprimir', '', 400)
    html = _html_carteles(bono, orden, denominacion, paquetes, reparto, cajas, nombres)
    return bono, item, reparto, cajas, html, ya


@bp.route('/api/embalaje/orden/<orden_id>/carteles', methods=['POST'])
def api_embalaje_carteles(orden_id):
    """Imprime los carteles (todos, o las cajas que se pidan para reponer uno)
    y apunta el embalaje. Responde 200 con motivo si la impresora falla."""
    from app import impresion_planchas as ip_
    datos = request.get_json(silent=True) or {}
    try:
        bono, item, reparto, cajas, html, ya = _preparar_carteles(orden_id, datos)
        respuesta = None
        if datos.get('pdf'):
            pdf = ip_.html_a_pdf(html)
            respuesta = send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True,
                                  download_name=f"carteles_{item['orden'].get('numero') or 'orden'}.pdf")
            mensaje = ''
        else:
            ip = ip_.imprimir_plancha(html, current_app.config['DATA_DIR'])
            mensaje = (f"{len(cajas)} cartel{'es' if len(cajas) > 1 else ''} "
                       f"enviado{'s' if len(cajas) > 1 else ''} a la impresora ({ip}).")
        aut = _autorizacion(orden_id) or {}
        with db.engine.begin() as conn:
            embalaje.registrar_embalaje(
                conn, item['orden'], bono, reparto, cajas,
                operario=_operario(datos), operario_via=(datos.get('operario_via') or '')[:20] or None,
                supervisor=aut.get('supervisor') if item['estado'] == 'pendientes' else None,
                supervisor_via=aut.get('via') if item['estado'] == 'pendientes' else None,
                con_pendientes=item['estado'] == 'pendientes')
        return respuesta or jsonify({'success': True, 'message': mensaje, 'cajas': cajas})
    except ip_.ErrorImpresion as e:
        return jsonify({'success': False, 'sin_impresora': 'configurada' in str(e),
                        'message': str(e), 'motivo': str(e),
                        'consejo': 'Puedes ver los carteles e imprimirlos desde el navegador'})
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e, 'Error al imprimir los carteles', status=200)


@bp.route('/api/embalaje/orden/<orden_id>/carteles.html', methods=['GET'])
def api_embalaje_carteles_html(orden_id):
    """Los mismos carteles para verlos o imprimirlos desde el navegador
    (sin impresora de red). No apunta el embalaje."""
    try:
        cajas = [c for c in (request.args.get('cajas') or '').split(',') if c.strip()]
        *_, html, _ya = _preparar_carteles(orden_id, {'cajas': cajas})
        return html
    except embalaje.EmbalajeError as err:
        return f"<p style='font:20px sans-serif'>{escape(err.motivo)}. {escape(err.consejo)}</p>", err.status
    except Exception as e:
        return error_interno(e)


# ==================== identificación: operario ====================

def _lector_listo(puesto_id):
    """device_id del lector del puesto si está conectado y con el firmware
    actual (con uno viejo no atiende capturas), o None."""
    from app.routes.pick_to_light import _placa_del_puesto
    from app.routes.sistema import _rfid_load_devices, _rfid_firmware_version
    device_id, _ = _placa_del_puesto(puesto_id)
    if not device_id:
        return None
    lector = (_rfid_load_devices() or {}).get(device_id) or {}
    try:
        online = (_ahora() - datetime.fromisoformat(lector.get('last_seen', ''))).total_seconds() < 90
    except (TypeError, ValueError):
        online = False
    version = _rfid_firmware_version()
    if not online or not version or lector.get('fw') != version:
        return None
    return device_id


def _puesto_peticion(datos):
    puesto_id = (datos.get('puesto_id') or '').strip()
    if puesto_id:
        return puesto_id
    try:
        from app.routes.puestos import _pc_identidad
        return _pc_identidad()[1]
    except Exception:
        return None


def _armar_captura(datos, tipo, ref):
    device_id = _lector_listo(_puesto_peticion(datos))
    if not device_id:
        raise embalaje.EmbalajeError('Este puesto no tiene lector de tarjetas conectado',
                                     'Elige tu nombre en la lista', 409, sin_lector=True)
    token = uuid.uuid4().hex
    expira_at = (_ahora() + timedelta(seconds=SEGUNDOS_TARJETA)).isoformat()
    with db.engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO operario_tag_capturas
                (device_id, operario_id, token, estado, uid, mensaje, expira_at, tipo, ref)
            VALUES (:d, '', :t, 'armada', NULL, NULL, :e, :tipo, :ref)
            ON CONFLICT(device_id) DO UPDATE SET
                operario_id = '', token = excluded.token, estado = 'armada',
                uid = NULL, mensaje = NULL, expira_at = excluded.expira_at,
                tipo = excluded.tipo, ref = excluded.ref, created_at = datetime('now')
        """), {'d': device_id, 't': token, 'e': expira_at, 'tipo': tipo, 'ref': ref})
    return token


def _estado_captura(token, tipo):
    with db.engine.connect() as conn:
        fila = conn.execute(text("""
            SELECT estado, mensaje, expira_at FROM operario_tag_capturas
            WHERE token = :t AND tipo = :tipo
        """), {'t': token, 'tipo': tipo}).mappings().first()
    if not fila:
        return {'estado': 'caducada', 'mensaje': 'El lector ya no espera la tarjeta'}
    estado = fila['estado']
    if estado == 'armada':
        try:
            if datetime.fromisoformat(fila['expira_at']) <= _ahora():
                estado = 'caducada'
        except (TypeError, ValueError):
            estado = 'caducada'
    return {'estado': estado, 'mensaje': fila['mensaje']}


@bp.route('/api/embalaje/operario/tarjeta', methods=['POST'])
def api_embalaje_operario_tarjeta():
    """Arma el lector del puesto: la siguiente tarjeta identifica a quien embala."""
    try:
        token = _armar_captura(request.get_json(silent=True) or {}, TIPO_CAPTURA_OPERARIO, 'embalaje')
        return jsonify({'success': True, 'token': token, 'segundos': SEGUNDOS_TARJETA})
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/embalaje/operario/tarjeta/<token>', methods=['GET'])
def api_embalaje_operario_tarjeta_estado(token):
    try:
        est = _estado_captura(token, TIPO_CAPTURA_OPERARIO)
        return jsonify({'success': True, **est,
                        'operario': est['mensaje'] if est['estado'] == 'asignada' else None})
    except Exception as e:
        return error_interno(e)


def resolver_tarjeta_operario(conn, fila, uid):
    """La placa ha leído una tarjeta con la captura de embalaje armada.
    Lo llama operarios.py:api_esp32_operario_captura_resultado.
    Si no vale, la captura sigue armada para que pase otra."""
    from app.routes.operarios import _operario_por_tag, _captura_tag_resultado
    op = _operario_por_tag(conn, uid)
    if not op or not operario_puede(op[1], 'engastado'):
        mensaje = ('Tarjeta no registrada' if not op
                   else f'{op[1]} no tiene permiso de engastado')
        conn.execute(text("UPDATE operario_tag_capturas SET mensaje = :m "
                          "WHERE device_id = :d AND token = :t"),
                     {'m': mensaje, 'd': fila['device_id'], 't': fila['token']})
        return {'success': False, 'error': 'SIN PERMISO' if op else 'TARJETA NO REGISTRADA'}, 409
    _captura_tag_resultado(conn, fila, 'asignada', op[1], uid)
    return {'success': True, 'uid': uid, 'operario': op[1]}, 200


# ==================== identificación: supervisor ====================

def _autorizacion(orden_id):
    """Supervisor que ha autorizado esta orden en esta sesión, si aún vale."""
    aut = (session.get('embalaje_autorizaciones') or {}).get(orden_id)
    if not aut or time.time() - aut.get('ts', 0) > MINUTOS_AUTORIZACION * 60:
        return None
    return aut


@bp.route('/api/embalaje/supervisor/tarjeta', methods=['POST'])
def api_embalaje_supervisor_tarjeta():
    datos = request.get_json(silent=True) or {}
    orden_id = (datos.get('orden_id') or '').strip()
    if not orden_id:
        return jsonify({'success': False, 'message': 'Falta la orden'}), 400
    try:
        token = _armar_captura(datos, TIPO_CAPTURA_SUPERVISOR, f'embalaje:{orden_id}')
        return jsonify({'success': True, 'token': token, 'segundos': SEGUNDOS_TARJETA})
    except embalaje.EmbalajeError as err:
        err.consejo = 'El supervisor puede identificarse con su usuario y clave'
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/embalaje/supervisor/tarjeta/<token>', methods=['GET'])
def api_embalaje_supervisor_tarjeta_estado(token):
    try:
        est = _estado_captura(token, TIPO_CAPTURA_SUPERVISOR)
        return jsonify({'success': True, **est,
                        'supervisor': est['mensaje'] if est['estado'] == 'asignada' else None})
    except Exception as e:
        return error_interno(e)


@bp.route('/api/embalaje/supervisor', methods=['POST'])
def api_embalaje_supervisor():
    """El supervisor se identifica (tarjeta ya leída, o usuario y clave) y
    queda autorizada esta orden en esta pantalla durante unos minutos."""
    datos = request.get_json(silent=True) or {}
    orden_id = (datos.get('orden_id') or '').strip()
    token = (datos.get('token') or '').strip()
    try:
        if not orden_id:
            raise embalaje.EmbalajeError('Falta la orden', '', 400)
        if token:
            with db.engine.begin() as conn:
                cap = conn.execute(text("""
                    SELECT device_id, token, mensaje FROM operario_tag_capturas
                    WHERE token = :t AND tipo = :tipo AND ref = :ref AND estado = 'asignada'
                """), {'t': token, 'tipo': TIPO_CAPTURA_SUPERVISOR,
                       'ref': f'embalaje:{orden_id}'}).mappings().first()
                if not cap:
                    raise embalaje.EmbalajeError('La tarjeta del supervisor ya no es válida',
                                                 'Que vuelva a pasar la tarjeta', 403)
                # Un solo uso: la misma lectura no autoriza dos veces.
                conn.execute(text("UPDATE operario_tag_capturas SET estado = 'usada' "
                                  "WHERE device_id = :d AND token = :t"),
                             {'d': cap['device_id'], 't': cap['token']})
            supervisor, via = cap['mensaje'], 'tarjeta'
        else:
            op = verificar_credenciales_personales((datos.get('usuario') or '').strip(),
                                                   datos.get('clave') or '')
            if not op:
                raise embalaje.EmbalajeError('Usuario o clave incorrectos',
                                             'Revisa la clave personal del supervisor', 403)
            supervisor, via = op['nombre'], 'clave'
        if not operario_puede(supervisor, embalaje.PERMISO_SUPERVISOR):
            raise embalaje.EmbalajeError(f'{supervisor} no tiene permiso de supervisor',
                                         'Admin → Operarios → Módulos permitidos', 403)
        auts = dict(session.get('embalaje_autorizaciones') or {})
        auts = {k: v for k, v in auts.items() if time.time() - v.get('ts', 0) <= MINUTOS_AUTORIZACION * 60}
        auts[orden_id] = {'supervisor': supervisor, 'via': via, 'ts': time.time()}
        session['embalaje_autorizaciones'] = auts
        return jsonify({'success': True, 'supervisor': supervisor})
    except embalaje.EmbalajeError as err:
        return _rechazo(err)
    except Exception as e:
        return error_interno(e)
