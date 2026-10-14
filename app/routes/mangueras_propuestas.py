import hashlib
import json
import os
import tempfile
from zipfile import BadZipFile
from urllib.parse import urlsplit

from flask import jsonify, render_template, request, session
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from app.auth import requiere_pin_admin, administrador_actual, sesion_admin_valida
from app.excel_manager import invalidar_cache_excel
from app.mangueras_editor import exportar_preparacion, leer_preparacion
from app.routes.base import bp, db, _ahora_iso, _ruta_upload_segura, operario_puede
from app.routes.manguitos import _MANGUERAS_EDITOR_LOCK


def _json_peticion():
    origen = request.headers.get('Origin') or request.headers.get('Referer')
    if origen and urlsplit(origen).netloc != request.host:
        raise PermissionError('Peticion de otro origen no permitida.')
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ValueError('Se requiere una peticion JSON.')
    return datos


def _identidad():
    with db.engine.connect() as conn:
        identidad = conn.execute(text(
            'SELECT o.id, o.nombre FROM operarios o JOIN operario_logins l ON l.operario_nombre=o.nombre '
            'WHERE l.id=:login AND l.activo=1 AND o.activo=1 AND o.nombre=:nombre'
        ), {'login': session.get('operario_login_id'), 'nombre': session.get('operario_actual')}).mappings().first()
    return identidad


@bp.route('/api/operarios/<op_id>/credencial-mangueras', methods=['PUT'])
@bp.route('/api/operarios/<op_id>/credencial-admin', methods=['PUT'])
@requiere_pin_admin
def configurar_credencial_mangueras(op_id):
    try:
        datos = _json_peticion()
        clave = datos.get('clave', '')
        if not isinstance(clave, str) or (clave and not 8 <= len(clave) <= 128):
            raise ValueError('La clave personal debe tener entre 8 y 128 caracteres.')
        with db.engine.begin() as conn:
            operario = conn.execute(text('SELECT clave_personal_hash FROM operarios WHERE id=:id'),
                                    {'id': op_id}).first()
            if not operario:
                return jsonify(success=False, error='Operario no encontrado.'), 404
            clave_hash = generate_password_hash(clave) if clave else operario[0]
            conn.execute(text(
                'UPDATE operarios SET clave_personal_hash=:clave, '
                'clave_intentos=0, clave_bloqueada_hasta=0 WHERE id=:id'
            ), {'id': op_id, 'clave': clave_hash})
        return jsonify(success=True)
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400


@bp.route('/api/mangueras/identificacion', methods=['GET'])
def identificacion_mangueras():
    identidad = _identidad()
    if not identidad:
        return jsonify(success=False, error='Entra al modulo con tu sesion de operario.'), 401
    if not operario_puede(identidad['nombre'], 'mangueras'):
        return jsonify(success=False, error='No tienes permiso de mangueras.'), 403
    return jsonify(success=True, nombre=identidad['nombre'], operario_id=identidad['id'])


@bp.route('/mangueras/propuestas')
def mangueras_propuestas():
    return render_template('mangueras-propuestas.html')


@bp.route('/api/mangueras/propuestas/pendientes')
def contador_propuestas_mangueras():
    with db.engine.connect() as conn:
        pendientes = conn.execute(text(
            "SELECT COUNT(*) FROM mangueras_propuestas WHERE estado='pendiente'"
        )).scalar_one()
    return jsonify(success=True, pendientes=pendientes)


@bp.route('/api/mangueras/propuestas', methods=['GET', 'POST'])
def api_mangueras_propuestas():
    administrador = administrador_actual() if request.method == 'GET' else None
    recuperacion = request.method == 'GET' and not administrador and sesion_admin_valida()
    identidad = administrador or ({'id': None, 'nombre': 'Acceso de recuperacion'} if recuperacion else _identidad())
    if not identidad:
        return jsonify(success=False, error='Entra al modulo con tu sesion de operario o identificate en Admin.'), 401
    if not administrador and not recuperacion and not operario_puede(identidad['nombre'], 'mangueras'):
        return jsonify(success=False, error='No tienes permiso de mangueras.'), 403
    if request.method == 'GET':
        with db.engine.connect() as conn:
            filas = conn.execute(text(
                'SELECT id, archivo, autor_id, autor_nombre, creada_at, motivo, estado, '
                'original_json, sugerido_json, responsable_nombre, resuelta_at, motivo_resolucion '
                'FROM mangueras_propuestas ORDER BY id DESC'
            )).mappings().all()
        propuestas = []
        for fila in filas:
            propuesta = dict(fila)
            propuesta['original'] = json.loads(propuesta.pop('original_json'))
            propuesta['sugerido'] = json.loads(propuesta.pop('sugerido_json'))
            propuestas.append(propuesta)
        return jsonify(success=True, propuestas=propuestas, aprobar=bool(administrador),
                       recuperacion=bool(recuperacion),
                       operario_id=identidad['id'], nombre=identidad['nombre'],
                       pendientes=sum(p['estado'] == 'pendiente' for p in propuestas))
    try:
        datos = _json_peticion()
        categoria = datos.get('motivo_categoria')
        detalle = datos.get('motivo', '')
        if categoria not in ('Informacion de nave cliente', 'Fallo en documentacion', 'Otros'):
            raise ValueError('Selecciona el motivo de la propuesta.')
        if not isinstance(detalle, str) or len(detalle) > 1900 or (categoria == 'Otros' and len(detalle.strip()) < 5):
            raise ValueError('En Otros escribe el motivo (al menos 5 caracteres).')
        motivo = categoria + (': ' + detalle.strip() if detalle.strip() else '')
        archivo = datos.get('archivo')
        ruta = _ruta_upload_segura(archivo)
        if not ruta or not os.path.isfile(ruta):
            raise ValueError('Selecciona un corte existente.')
        cambios = datos.get('cambios')
        if not isinstance(cambios, list) or len(cambios) != 1 or not isinstance(cambios[0], dict):
            raise ValueError('Cada propuesta debe modificar una sola manguera.')
        with _MANGUERAS_EDITOR_LOCK:
            with open(ruta, 'rb') as fichero:
                original = fichero.read()
            antes = leer_preparacion(original, os.path.basename(ruta))
            fila_original = next((fila for fila in antes['filas'] if fila['fila'] == cambios[0].get('fila')), None)
            campos = ('de', 'para', 'retractil_de', 'retractil_para', 'observaciones_mangueras', 'aviso_mangueras')
            if fila_original and all(fila_original.get(campo) == cambios[0].get(campo) for campo in campos):
                raise ValueError('La propuesta no contiene cambios.')
            sugerido = exportar_preparacion(original, os.path.basename(ruta), cambios,
                                           datos.get('revision', ''), solo_modificadas=True).getvalue()
            despues = leer_preparacion(sugerido, os.path.basename(ruta))
            if antes['filas'] == despues['filas']:
                raise ValueError('La propuesta no contiene cambios.')
            with db.engine.begin() as conn:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
                pendientes = conn.execute(text(
                    'SELECT sugerido_json FROM mangueras_propuestas WHERE archivo=:archivo AND estado=\'pendiente\''
                ), {'archivo': archivo}).scalars().all()
                for pendiente in pendientes:
                    if any(fila['fila'] == cambios[0]['fila'] for fila in json.loads(pendiente)['cambios']):
                        return jsonify(success=False, error='Esta manguera ya tiene una propuesta pendiente.'), 409
                resultado = conn.execute(text(
                    'INSERT INTO mangueras_propuestas '
                    '(archivo, revision, autor_id, autor_nombre, creada_at, motivo, original_json, '
                    'sugerido_json, original_excel, sugerido_excel) '
                    'VALUES (:archivo, :revision, :autor, :nombre, :fecha, :motivo, :antes, :despues, :original, :sugerido)'
                ), {'archivo': archivo, 'revision': antes['revision'], 'autor': identidad['id'],
                    'nombre': identidad['nombre'], 'fecha': _ahora_iso(), 'motivo': motivo.strip(),
                    'antes': json.dumps(antes['filas'], ensure_ascii=False),
                    'despues': json.dumps({'filas': despues['filas'], 'cambios': cambios}, ensure_ascii=False),
                    'original': original, 'sugerido': sugerido})
        return jsonify(success=True, id=resultado.lastrowid), 201
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except (ValueError, TypeError, BadZipFile) as exc:
        return jsonify(success=False, error=str(exc)), 400


@bp.route('/api/mangueras/propuestas/<int:propuesta_id>/resolver', methods=['POST'])
def resolver_propuesta_mangueras(propuesta_id):
    temporal = None
    reemplazado = False
    original = None
    ruta = None
    try:
        datos = _json_peticion()
        responsable = administrador_actual()
        if not responsable:
            return jsonify(success=False, error='Entra en Admin con tu operario y contrasena para resolver propuestas.'), 401
        accion = datos.get('accion')
        motivo = datos.get('motivo', '')
        if accion not in ('aprobar', 'rechazar') or not isinstance(motivo, str) or not 5 <= len(motivo.strip()) <= 2000:
            raise ValueError('Indica la decision y su motivo (5 a 2000 caracteres).')
        with _MANGUERAS_EDITOR_LOCK:
            with db.engine.begin() as conn:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
                propuesta = conn.execute(text('SELECT * FROM mangueras_propuestas WHERE id=:id'),
                                         {'id': propuesta_id}).mappings().first()
                if not propuesta:
                    return jsonify(success=False, error='Propuesta no encontrada.'), 404
                if propuesta['estado'] != 'pendiente':
                    return jsonify(success=False, error='La propuesta ya fue resuelta.'), 409
                if propuesta['autor_id'] == responsable['id']:
                    return jsonify(success=False, error='No puedes resolver tu propia propuesta.'), 403
                backup = None
                if accion == 'aprobar':
                    ruta = _ruta_upload_segura(propuesta['archivo'])
                    if not ruta or not os.path.isfile(ruta):
                        return jsonify(success=False, error='El corte ya no existe.'), 409
                    with open(ruta, 'rb') as fichero:
                        original = fichero.read()
                    if hashlib.sha256(original).hexdigest() != propuesta['revision']:
                        return jsonify(success=False, error='El Excel ha cambiado. Rechaza esta propuesta y solicita una nueva revision.'), 409
                    backup = ruta + '.backup_mangueras_propuesta_' + str(propuesta_id)
                    if not os.path.exists(backup):
                        with open(backup, 'xb') as fichero:
                            fichero.write(original)
                            fichero.flush()
                            os.fsync(fichero.fileno())
                    with tempfile.NamedTemporaryFile(dir=os.path.dirname(ruta), delete=False) as fichero:
                        temporal = fichero.name
                        fichero.write(propuesta['sugerido_excel'])
                        fichero.flush()
                        os.fsync(fichero.fileno())
                    with open(backup + '.json', 'w', encoding='utf-8') as fichero:
                        json.dump({'propuesta_id': propuesta_id, 'archivo': propuesta['archivo'],
                                   'autor_id': propuesta['autor_id'], 'autor': propuesta['autor_nombre'],
                                   'responsable_id': responsable['id'], 'responsable': responsable['nombre'],
                                   'fecha_autorizacion': _ahora_iso(), 'motivo': motivo.strip(),
                                   'revision_original': propuesta['revision'],
                                   'revision_autorizada': hashlib.sha256(propuesta['sugerido_excel']).hexdigest()},
                                  fichero, ensure_ascii=False)
                        fichero.flush()
                        os.fsync(fichero.fileno())
                    with open(ruta, 'rb') as fichero:
                        if hashlib.sha256(fichero.read()).hexdigest() != propuesta['revision']:
                            return jsonify(success=False, error='El Excel ha cambiado durante la aprobacion.'), 409
                    os.replace(temporal, ruta)
                    temporal = None
                    reemplazado = True
                    invalidar_cache_excel(ruta)
                conn.execute(text(
                    'UPDATE mangueras_propuestas SET estado=:estado, responsable_id=:responsable, '
                    'responsable_nombre=:nombre, resuelta_at=:fecha, motivo_resolucion=:motivo, backup=:backup '
                    'WHERE id=:id'
                ), {'id': propuesta_id, 'estado': 'aprobada' if accion == 'aprobar' else 'rechazada',
                    'responsable': responsable['id'], 'nombre': responsable['nombre'], 'fecha': _ahora_iso(),
                    'motivo': motivo.strip(), 'backup': os.path.basename(backup) if backup else None})
        return jsonify(success=True)
    except PermissionError as exc:
        return jsonify(success=False, error=str(exc)), 403
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception:
        if reemplazado:
            with tempfile.NamedTemporaryFile(dir=os.path.dirname(ruta), delete=False) as fichero:
                temporal = fichero.name
                fichero.write(original)
            os.replace(temporal, ruta)
            temporal = None
            invalidar_cache_excel(ruta)
        raise
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)