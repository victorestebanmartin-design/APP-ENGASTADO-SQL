"""Propuestas de engastado: "este terminal no se pone en este cable".

El operario marca, desde el paquete abierto en engastado, los cables en los
que el terminal no va. Un admin con su usuario personal (como en las
propuestas de mangueras) lo aprueba y entonces se escribe el '*' en el Excel:
desde ese momento el terminal no se pide ni se cuenta. Mientras está
pendiente, nada cambia.

Lo aprobado se hereda cuando llega una ED nueva del corte (heredar_bloqueos,
llamado desde archivos.py) y se puede revertir desde la misma pantalla.
"""
import os
import tempfile
from zipfile import BadZipFile

from flask import jsonify, render_template, request
from sqlalchemy import text

from app.auth import administrador_actual, sesion_admin_valida
from app.engastado_bloqueos import aplicar_bloqueos, leer_cable, quitar_bloqueos, LADOS
from app.excel_manager import invalidar_cache_excel
from app.routes.base import bp, db, _ahora_iso, _ruta_upload_segura, operario_puede
from app.routes.mangueras_propuestas import _identidad, _json_peticion, numeros_paquete
from app.routes.manguitos import _MANGUERAS_EDITOR_LOCK

MOTIVOS = ('Plano / documentacion', 'Indicacion del cliente', 'Error listado terminal no corresponde con seccion (fallo IFA)', 'Otros')
_CAMPOS_REGLA = ('lado', 'terminal', 'cod_cable', 'cable_marca', 'elemento', 'serie', 'fila')


def _escribir_excel(ruta, contenido, sufijo_backup):
    """Sustituye el Excel de forma atómica guardando antes el que había."""
    with open(ruta, 'rb') as fichero:
        anterior = fichero.read()
    backup = ruta + sufijo_backup
    if not os.path.exists(backup):
        with open(backup, 'xb') as fichero:
            fichero.write(anterior)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(ruta), delete=False) as fichero:
            temporal = fichero.name
            fichero.write(contenido)
            fichero.flush()
            os.fsync(fichero.fileno())
        os.replace(temporal, ruta)
        temporal = None
        invalidar_cache_excel(ruta)
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)
    return os.path.basename(backup)


def _reglas(filas, propuesta_id=None):
    return [dict({campo: fila[campo] for campo in _CAMPOS_REGLA},
                 propuesta_id=propuesta_id or fila['propuesta_id']) for fila in filas]


@bp.route('/engastado/propuestas')
def engastado_propuestas():
    return render_template('engastado-propuestas.html')


@bp.route('/api/engastado/propuestas/pendientes')
def contador_propuestas_engastado():
    with db.engine.connect() as conn:
        pendientes = conn.execute(text(
            "SELECT COUNT(*) FROM engastado_propuestas WHERE estado='pendiente'"
        )).scalar_one()
    return jsonify(success=True, pendientes=pendientes)


@bp.route('/api/engastado/propuestas/cables-pendientes')
def cables_pendientes_engastado():
    """Cables de ese terminal que ya tienen una propuesta abierta, para que
    otro operario no la repita. Sin identidad: solo dice qué está pedido."""
    with db.engine.connect() as conn:
        filas = conn.execute(text(
            "SELECT c.fila, c.lado FROM engastado_propuestas_cables c "
            "JOIN engastado_propuestas p ON p.id=c.propuesta_id "
            "WHERE p.estado='pendiente' AND c.archivo=:archivo AND UPPER(c.terminal)=UPPER(:terminal)"
        ), {'archivo': request.args.get('archivo', ''),
            'terminal': request.args.get('terminal', '').strip()}).mappings().all()
    return jsonify(success=True, cables=[dict(fila) for fila in filas])


@bp.route('/api/engastado/propuestas', methods=['GET', 'POST'])
def api_engastado_propuestas():
    administrador = administrador_actual() if request.method == 'GET' else None
    recuperacion = request.method == 'GET' and not administrador and sesion_admin_valida()
    identidad = administrador or ({'id': None, 'nombre': 'Acceso de recuperacion'} if recuperacion else _identidad())
    if not identidad:
        return jsonify(success=False, error='Pasa tu tarjeta para identificarte antes de avisar.'), 401
    if not administrador and not recuperacion and not operario_puede(identidad['nombre'], 'engastado'):
        return jsonify(success=False, error='No tienes permiso de engastado.'), 403
    if request.method == 'GET':
        with db.engine.connect() as conn:
            propuestas = [dict(fila) for fila in conn.execute(text(
                'SELECT * FROM engastado_propuestas ORDER BY id DESC LIMIT 500'
            )).mappings().all()]
            cables = conn.execute(text(
                'SELECT * FROM engastado_propuestas_cables WHERE propuesta_id IN '
                '(SELECT id FROM engastado_propuestas ORDER BY id DESC LIMIT 500) ORDER BY id'
            )).mappings().all()
            buscadores = numeros_paquete(conn, [cable['archivo'] for cable in cables])
        por_propuesta = {}
        for cable in cables:
            cable = dict(cable, paquete=buscadores[cable['archivo']](
                cable['cod_cable'], cable['elemento'], cable['serie']))
            por_propuesta.setdefault(cable['propuesta_id'], []).append(cable)
        for propuesta in propuestas:
            propuesta['cables'] = por_propuesta.get(propuesta['id'], [])
        return jsonify(success=True, propuestas=propuestas, aprobar=bool(administrador),
                       recuperacion=bool(recuperacion), operario_id=identidad['id'],
                       nombre=identidad['nombre'],
                       pendientes=sum(p['estado'] == 'pendiente' for p in propuestas))
    try:
        datos = _json_peticion()
        categoria = datos.get('motivo_categoria')
        detalle = datos.get('motivo', '')
        if categoria not in MOTIVOS:
            raise ValueError('Selecciona el motivo del aviso.')
        if not isinstance(detalle, str) or len(detalle) > 1900 or (categoria == 'Otros' and len(detalle.strip()) < 5):
            raise ValueError('En Otros escribe el motivo (al menos 5 caracteres).')
        motivo = categoria + (': ' + detalle.strip() if detalle.strip() else '')
        archivo = datos.get('archivo')
        ruta = _ruta_upload_segura(archivo)
        if not ruta or not os.path.isfile(ruta):
            raise ValueError('El corte de este paquete ya no existe.')
        terminal = datos.get('terminal')
        paquete = datos.get('paquete')
        if not isinstance(terminal, str) or not terminal.strip() or not isinstance(paquete, str) or len(paquete) > 200:
            raise ValueError('Falta el terminal o el paquete.')
        marcados = datos.get('cables')
        if not isinstance(marcados, list) or not 1 <= len(marcados) <= 500 or \
                any(not isinstance(c, dict) or c.get('lado') not in LADOS for c in marcados):
            raise ValueError('Marca al menos un cable.')
        claves = {(c.get('fila'), c['lado']) for c in marcados}
        if len(claves) != len(marcados):
            raise ValueError('Hay cables repetidos en el aviso.')
        with _MANGUERAS_EDITOR_LOCK:
            with open(ruta, 'rb') as fichero:
                contenido = fichero.read()
            cables = [leer_cable(contenido, os.path.basename(ruta), c.get('fila'), c['lado'], terminal)
                      for c in marcados]
            with db.engine.begin() as conn:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
                ya_pedidos = {(fila['fila'], fila['lado']) for fila in conn.execute(text(
                    "SELECT c.fila, c.lado FROM engastado_propuestas_cables c "
                    "JOIN engastado_propuestas p ON p.id=c.propuesta_id "
                    "WHERE p.estado='pendiente' AND c.archivo=:archivo"
                ), {'archivo': archivo}).mappings()}
                repetidos = [c['cable_marca'] for c in cables if (c['fila'], c['lado']) in ya_pedidos]
                if repetidos:
                    return jsonify(success=False, error='Ya hay un aviso pendiente para: ' +
                                   ', '.join(repetidos)), 409
                resultado = conn.execute(text(
                    'INSERT INTO engastado_propuestas (archivo, terminal, paquete, autor_id, autor_nombre, '
                    'creada_at, motivo) VALUES (:archivo, :terminal, :paquete, :autor, :nombre, :fecha, :motivo)'
                ), {'archivo': archivo, 'terminal': terminal.strip(), 'paquete': paquete.strip(),
                    'autor': identidad['id'], 'nombre': identidad['nombre'], 'fecha': _ahora_iso(),
                    'motivo': motivo})
                propuesta_id = resultado.lastrowid
                for cable in cables:
                    conn.execute(text(
                        'INSERT INTO engastado_propuestas_cables (propuesta_id, archivo, fila, lado, terminal, '
                        'cod_cable, cable_marca, elemento, serie) VALUES '
                        '(:propuesta, :archivo, :fila, :lado, :terminal, :cod_cable, :cable_marca, :elemento, :serie)'
                    ), dict(cable, propuesta=propuesta_id, archivo=archivo))
        return jsonify(success=True, id=propuesta_id), 201
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except (ValueError, TypeError, BadZipFile) as exc:
        return jsonify(success=False, error=str(exc)), 400


def _decision(datos):
    motivo = datos.get('motivo', '')
    if not isinstance(motivo, str) or not 5 <= len(motivo.strip()) <= 2000:
        raise ValueError('Indica el motivo (5 a 2000 caracteres).')
    return motivo.strip()


@bp.route('/api/engastado/propuestas/<int:propuesta_id>/resolver', methods=['POST'])
def resolver_propuesta_engastado(propuesta_id):
    try:
        datos = _json_peticion()
        responsable = administrador_actual()
        if not responsable:
            return jsonify(success=False, error='Entra en Admin con tu operario y contrasena para resolver propuestas.'), 401
        accion = datos.get('accion')
        if accion not in ('aprobar', 'rechazar'):
            raise ValueError('Indica la decision.')
        motivo = _decision(datos)
        aplicados = 0
        with _MANGUERAS_EDITOR_LOCK:
            with db.engine.begin() as conn:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
                propuesta = conn.execute(text('SELECT * FROM engastado_propuestas WHERE id=:id'),
                                         {'id': propuesta_id}).mappings().first()
                if not propuesta:
                    return jsonify(success=False, error='Propuesta no encontrada.'), 404
                if propuesta['estado'] != 'pendiente':
                    return jsonify(success=False, error='La propuesta ya fue resuelta.'), 409
                if propuesta['autor_id'] == responsable['id']:
                    return jsonify(success=False, error='No puedes resolver tu propia propuesta.'), 403
                if accion == 'aprobar':
                    ruta = _ruta_upload_segura(propuesta['archivo'])
                    if not ruta or not os.path.isfile(ruta):
                        return jsonify(success=False, error='El corte ya no existe.'), 409
                    cables = conn.execute(text(
                        'SELECT * FROM engastado_propuestas_cables WHERE propuesta_id=:id ORDER BY id'
                    ), {'id': propuesta_id}).mappings().all()
                    with open(ruta, 'rb') as fichero:
                        original = fichero.read()
                    nuevo, resultados = aplicar_bloqueos(original, os.path.basename(ruta),
                                                         _reglas(cables, propuesta_id))
                    aplicados = sum(r['resultado'] in ('aplicado', 'ya_bloqueado') for r in resultados)
                    if not aplicados:
                        return jsonify(success=False, error='Ningun cable de la propuesta cuadra ya con el Excel. '
                                       'Rechazala y que se vuelva a avisar.'), 409
                    for cable, resultado in zip(cables, resultados):
                        conn.execute(text(
                            'UPDATE engastado_propuestas_cables SET fila=COALESCE(:fila, fila), activo=:activo, '
                            'resultado=:resultado WHERE id=:id'
                        ), {'id': cable['id'], 'fila': resultado['fila'], 'resultado': resultado['resultado'],
                            'activo': int(resultado['resultado'] in ('aplicado', 'ya_bloqueado'))})
                conn.execute(text(
                    'UPDATE engastado_propuestas SET estado=:estado, responsable_id=:responsable, '
                    'responsable_nombre=:nombre, resuelta_at=:fecha, motivo_resolucion=:motivo WHERE id=:id'
                ), {'id': propuesta_id, 'estado': 'aprobada' if accion == 'aprobar' else 'rechazada',
                    'responsable': responsable['id'], 'nombre': responsable['nombre'],
                    'fecha': _ahora_iso(), 'motivo': motivo})
                # El Excel se escribe lo último: si falla, la transacción se
                # deshace y la propuesta sigue pendiente con el Excel intacto.
                if accion == 'aprobar' and nuevo != original:
                    _escribir_excel(ruta, nuevo, f'.backup_engastado_propuesta_{propuesta_id}')
        return jsonify(success=True, aplicados=aplicados)
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except (ValueError, BadZipFile) as exc:
        return jsonify(success=False, error=str(exc)), 400


@bp.route('/api/engastado/propuestas/<int:propuesta_id>/revertir', methods=['POST'])
def revertir_propuesta_engastado(propuesta_id):
    """Vuelve a pedir el terminal: quita los '*' que puso la propuesta en los
    Excels donde sigue activa y deja de heredarse en las ED siguientes."""
    try:
        datos = _json_peticion()
        responsable = administrador_actual()
        if not responsable:
            return jsonify(success=False, error='Entra en Admin con tu operario y contrasena para revertir.'), 401
        motivo = _decision(datos)
        with _MANGUERAS_EDITOR_LOCK:
            with db.engine.begin() as conn:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
                propuesta = conn.execute(text('SELECT * FROM engastado_propuestas WHERE id=:id'),
                                         {'id': propuesta_id}).mappings().first()
                if not propuesta:
                    return jsonify(success=False, error='Propuesta no encontrada.'), 404
                if propuesta['estado'] != 'aprobada':
                    return jsonify(success=False, error='Solo se puede revertir una propuesta aprobada.'), 409
                activos = conn.execute(text(
                    'SELECT * FROM engastado_propuestas_cables WHERE propuesta_id=:id AND activo=1 ORDER BY id'
                ), {'id': propuesta_id}).mappings().all()
                escrituras = []
                por_archivo = {}
                for cable in activos:
                    por_archivo.setdefault(cable['archivo'], []).append(cable)
                for archivo, cables in por_archivo.items():
                    ruta = _ruta_upload_segura(archivo)
                    resultados = [{'resultado': 'no_encontrado'}] * len(cables)
                    if ruta and os.path.isfile(ruta):
                        with open(ruta, 'rb') as fichero:
                            original = fichero.read()
                        nuevo, resultados = quitar_bloqueos(original, os.path.basename(ruta),
                                                            _reglas(cables, propuesta_id))
                        if nuevo != original:
                            escrituras.append((ruta, nuevo))
                    for cable, resultado in zip(cables, resultados):
                        conn.execute(text(
                            'UPDATE engastado_propuestas_cables SET activo=0, resultado=:resultado WHERE id=:id'
                        ), {'id': cable['id'], 'resultado': resultado['resultado']})
                conn.execute(text(
                    "UPDATE engastado_propuestas SET estado='revertida', revertida_por=:nombre, "
                    'revertida_at=:fecha, motivo_reversion=:motivo WHERE id=:id'
                ), {'id': propuesta_id, 'nombre': responsable['nombre'], 'fecha': _ahora_iso(),
                    'motivo': motivo})
                for ruta, nuevo in escrituras:
                    _escribir_excel(ruta, nuevo, f'.backup_engastado_reversion_{propuesta_id}')
        return jsonify(success=True)
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except (ValueError, BadZipFile) as exc:
        return jsonify(success=False, error=str(exc)), 400


def heredar_bloqueos(archivo_anterior, archivo_nuevo, contenido, nombre):
    """Pone en una ED nueva los '*' aprobados de la anterior.

    Devuelve (contenido, resumen, registrar). Llama a registrar() después de
    guardar el Excel, para que la BD no apunte a un '*' que no llegó a disco.
    Los cables que no cuadran en la ED nueva se quedan sin heredar y salen en
    el resumen: el admin los ve en Propuestas de engastado.
    """
    with db.engine.connect() as conn:
        reglas = conn.execute(text(
            'SELECT * FROM engastado_propuestas_cables WHERE archivo=:archivo AND activo=1 ORDER BY id'
        ), {'archivo': archivo_anterior}).mappings().all()
    resumen = {'heredados': 0, 'no_heredados': 0}
    if not reglas:
        return contenido, resumen, lambda: None
    nuevo, resultados = aplicar_bloqueos(contenido, nombre, _reglas(reglas))
    for resultado in resultados:
        ok = resultado['resultado'] in ('aplicado', 'ya_bloqueado')
        resumen['heredados' if ok else 'no_heredados'] += 1

    def registrar():
        with db.engine.begin() as conn:
            for regla, resultado in zip(reglas, resultados):
                activo = int(resultado['resultado'] in ('aplicado', 'ya_bloqueado'))
                estado = ('heredado' if activo else 'no_heredado_' + resultado['resultado'])
                if archivo_anterior == archivo_nuevo:
                    conn.execute(text(
                        'UPDATE engastado_propuestas_cables SET fila=COALESCE(:fila, fila), activo=:activo, '
                        'resultado=:resultado WHERE id=:id'
                    ), {'id': regla['id'], 'fila': resultado['fila'], 'activo': activo, 'resultado': estado})
                else:
                    conn.execute(text(
                        'INSERT INTO engastado_propuestas_cables (propuesta_id, archivo, fila, lado, terminal, '
                        'cod_cable, cable_marca, elemento, serie, activo, resultado) VALUES '
                        '(:propuesta_id, :archivo, :fila, :lado, :terminal, :cod_cable, :cable_marca, '
                        ':elemento, :serie, :activo, :resultado)'
                    ), dict(regla, archivo=archivo_nuevo, fila=resultado['fila'] or regla['fila'],
                            activo=activo, resultado=estado))
    return nuevo, resumen, registrar
