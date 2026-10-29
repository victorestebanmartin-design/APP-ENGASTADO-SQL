"""
Asistente «Generar bono» para operarios.

El operario escanea con la pistola el carro (carro1..carro6) y la orden que
lleva (corte-orden-cantidad, el mismo código que en Mangueras) y, al confirmar,
nace el bono. Un carro lleva una sola orden; el bono junta varios carros.

Aquí no se pide el PIN de admin: se pide sesión de operario con el permiso
«bonos», que se habilita a mano en Admin -> Operarios.
"""
import re
from datetime import datetime

from flask import current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth import sesion_admin_valida
from app.fases_orden import motivo_fases_pendientes
from app.routes.carros import liberar_carro_en_conn
from app.routes.base import bp, db, error_interno, operario_puede, _es_error_nombre_bono_duplicado
from app.routes.mangueras_propuestas import _identidad, _json_peticion

_CODIGO_ORDEN = re.compile(r'([A-Za-z0-9_]+)-(\d+)-([1-9]\d*)')
_NOMBRE_BONO_NUEVO = re.compile(r'^(\d{7})_(\d{4})$')
_MAX_CARROS = 6


def nombre_sugerido_bono(conn):
    """Siguiente NNNNNNN_AAAA libre, leído en la misma conexión que va a crear
    el bono para que dos operarios a la vez no saquen el mismo nombre."""
    anio = str(datetime.now().year)
    ultimo = 0
    for (nombre,) in conn.execute(text('SELECT nombre FROM bonos')):
        m = _NOMBRE_BONO_NUEVO.match(nombre)
        if m and m.group(2) == anio:
            ultimo = max(ultimo, int(m.group(1)))
    return f'{ultimo + 1:07d}_{anio}'


def _quien():
    """(nombre, None) si puede generar bonos; (None, respuesta) si no."""
    identidad = _identidad()
    if identidad:
        if operario_puede(identidad['nombre'], 'bonos'):
            return identidad['nombre'], None
        return None, (jsonify(
            success=False, error='No tienes permiso para generar bonos.',
            consejo='Pídele a un administrador que lo habilite en Admin → Operarios → Módulos permitidos.'), 403)
    if sesion_admin_valida():
        return 'Administración', None
    return None, (jsonify(
        success=False, error='Entra con tu sesión de operario para generar bonos.',
        consejo='Pasa tu tarjeta por el lector.'), 401)


def _carros_libres(conn):
    """{numero: (libre, motivo)} de los seis carros."""
    ocupados_proyecto = {r[0] for r in conn.execute(text(
        'SELECT carro_asignado FROM proyectos WHERE carro_asignado IS NOT NULL'))}
    resultado = {}
    for c in conn.execute(text('SELECT c.numero, c.estado, c.bono_id, b.nombre AS bono '
                               'FROM carros c LEFT JOIN bonos b ON b.id = c.bono_id '
                               'ORDER BY c.numero')).mappings():
        if c['bono_id'] or c['estado'] != 'disponible':
            motivo = f"Ocupado por el bono {c['bono']}" if c['bono'] else 'Ocupado'
            resultado[c['numero']] = (False, motivo)
        elif c['numero'] in ocupados_proyecto:
            resultado[c['numero']] = (False, 'Tiene una orden asignada desde Gestión de proyectos')
        else:
            resultado[c['numero']] = (True, None)
    return resultado


def _problema_orden(conn, orden):
    """Motivo por el que una orden no puede entrar a un bono, o None."""
    if not orden:
        return 'La orden no está registrada. Pásala primero por Mangueras.'
    if orden['bono_id'] or orden['estado'] == 'en_bono':
        return f"La orden {orden['numero']} ya está en un bono."
    if orden['estado'] != 'pendiente':
        return f"La orden {orden['numero']} está en estado «{orden['estado']}», no pendiente."
    if not orden['archivo_excel']:
        return f"La orden {orden['numero']} no tiene Excel asociado."
    return motivo_fases_pendientes(conn, orden)


@bp.route('/api/bonos/asistente/estado', methods=['GET'])
def asistente_bono_estado():
    _, error = _quien()
    if error:
        return error
    try:
        with db.engine.connect() as conn:
            carros = [{'numero': n, 'libre': libre, 'motivo': motivo}
                      for n, (libre, motivo) in _carros_libres(conn).items()]
            nombre = nombre_sugerido_bono(conn)
        return jsonify(success=True, carros=carros, nombre_sugerido=nombre)
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/asistente/orden', methods=['POST'])
def asistente_bono_orden():
    """Resuelve el código escaneado de una orden y dice si puede entrar a un bono."""
    _, error = _quien()
    if error:
        return error
    try:
        datos = _json_peticion()
        codigo = datos.get('codigo')
        coincidencia = _CODIGO_ORDEN.fullmatch(codigo.strip() if isinstance(codigo, str) else '')
        if not coincidencia:
            return jsonify(success=False, error='Código de orden no válido.',
                           consejo='Escanea la etiqueta de la orden, por ejemplo H0174891-60238442-1.'), 400
        corte, numero, cantidad = coincidencia.groups()
        with db.engine.connect() as conn:
            orden = conn.execute(text('SELECT * FROM ordenes_produccion WHERE numero = :n'),
                                 {'n': numero}).mappings().first()
            problema = _problema_orden(conn, orden)
        if problema:
            return jsonify(success=False, error=problema), 409
        if orden['codigo_corte'].upper() != corte.upper() or orden['cantidad'] != int(cantidad):
            return jsonify(success=False,
                           error='El código no coincide con la orden registrada (corte o cantidad distintos).',
                           consejo='Revisa que has escaneado la etiqueta correcta.'), 409
        return jsonify(success=True, orden={
            'id': orden['id'], 'numero': orden['numero'], 'codigo_corte': orden['codigo_corte'],
            'cantidad': orden['cantidad'], 'proyecto': orden['proyecto']})
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/asistente/liberar-carro', methods=['POST'])
def asistente_bono_liberar_carro():
    """Salida para un carro atascado (bono abandonado, carro vaciado a mano…).

    Pide `confirmar: true`: el operario tiene que haber comprobado que el carro
    está físicamente vacío. Solo libera el carro; el bono sigue existiendo."""
    operario, error = _quien()
    if error:
        return error
    try:
        datos = _json_peticion()
        carro = datos.get('carro')
        if type(carro) is not int or not 1 <= carro <= _MAX_CARROS:
            raise ValueError('Carro no válido.')
        if datos.get('confirmar') is not True:
            return jsonify(success=False, error='Confirma que el carro está vacío.'), 400
        with db.engine.begin() as conn:
            cuerpo, estado = liberar_carro_en_conn(conn, carro, True)
        if estado != 200:
            return jsonify(success=False, error=cuerpo.get('message', 'No se pudo liberar el carro.')), estado
        current_app.logger.info(f'Carro {carro} liberado a mano por {operario}')
        return jsonify(success=True, message=cuerpo['message'])
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception as e:
        return error_interno(e)


@bp.route('/api/bonos/asistente/crear', methods=['POST'])
def asistente_bono_crear():
    """Crea el bono con {carros: [{carro, orden_id}, ...]}.

    Todo en una transacción y revalidando contra la BD: entre que el operario
    escaneó y confirmó, otro puede haber ocupado un carro o una orden."""
    operario, error = _quien()
    if error:
        return error
    try:
        datos = _json_peticion()
        items = datos.get('carros')
        if not isinstance(items, list) or not 1 <= len(items) <= _MAX_CARROS:
            raise ValueError(f'Añade entre uno y {_MAX_CARROS} carros al bono.')
        for item in items:
            if (not isinstance(item, dict) or type(item.get('carro')) is not int
                    or not 1 <= item['carro'] <= _MAX_CARROS or not isinstance(item.get('orden_id'), str)):
                raise ValueError('Datos de carro u orden no válidos.')
        if len({i['carro'] for i in items}) != len(items) or len({i['orden_id'] for i in items}) != len(items):
            raise ValueError('Hay un carro o una orden repetidos.')
        items = sorted(items, key=lambda i: i['carro'])

        import uuid
        with db.engine.begin() as conn:
            conn.exec_driver_sql('BEGIN IMMEDIATE')
            libres = _carros_libres(conn)
            for item in items:
                libre, motivo = libres.get(item['carro'], (False, 'Carro no encontrado'))
                if not libre:
                    return jsonify(success=False, error=f"Carro {item['carro']}: {motivo}.",
                                   consejo='Actualiza la pantalla y elige otro carro.'), 409
                orden = conn.execute(text('SELECT * FROM ordenes_produccion WHERE id = :id'),
                                     {'id': item['orden_id']}).mappings().first()
                problema = _problema_orden(conn, orden)
                if problema:
                    return jsonify(success=False, error=problema), 409
                item['numero'] = orden['numero']

            nombre = nombre_sugerido_bono(conn)
            bono_id = str(uuid.uuid4())
            conn.execute(text(
                "INSERT INTO bonos (id, nombre, descripcion, estado, numeracion_carros) "
                "VALUES (:id, :nombre, :descripcion, 'activo', 'fisica')"
            ), {'id': bono_id, 'nombre': nombre,
                'descripcion': f'Bono con {len(items)} carros (creado por {operario})'})
            for item in items:
                conn.execute(text(
                    "UPDATE ordenes_produccion SET bono_id = :bono, estado = 'en_bono', "
                    "carro_numero = :carro, fecha_inicio_bono = datetime('now') WHERE id = :id"
                ), {'bono': bono_id, 'carro': item['carro'], 'id': item['orden_id']})
                conn.execute(text("UPDATE carros SET bono_id = :bono, estado = 'en_proceso' WHERE numero = :n"),
                             {'bono': bono_id, 'n': item['carro']})
        return jsonify(success=True, bono={
            'id': bono_id, 'nombre': nombre,
            'carros': [{'carro': i['carro'], 'orden': i['numero']} for i in items]})
    except IntegrityError as e:
        if _es_error_nombre_bono_duplicado(e):
            return jsonify(success=False, error='Ya existe un bono con ese nombre.',
                           consejo='Inténtalo de nuevo.'), 409
        return error_interno(e, 'Error al generar bono')
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception as e:
        return error_interno(e, 'Error al generar bono')
