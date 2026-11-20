"""Admin -> Diagnóstico ESP32: grabar la pantalla grande (P4) por USB.

La lógica está en app/pantalla_p4.py; aquí solo las rutas.
"""
import os
import re

from flask import current_app, jsonify, request

from app import pantalla_p4
from app.auth import requiere_pin_admin
from app.routes.base import bp, error_interno


def _proyecto():
    return os.path.dirname(current_app.root_path)


@bp.route('/api/pantalla_p4/estado', methods=['GET'])
@requiere_pin_admin
def api_pantalla_p4_estado():
    try:
        proyecto = _proyecto()
        return jsonify({
            'success': True,
            'disponible': bool(pantalla_p4.buscar_arduino_cli()),
            'version': pantalla_p4.version_firmware(proyecto),
            'variantes': [{'id': k, 'nombre': v['nombre']} for k, v in pantalla_p4.VARIANTES.items()],
            'trabajo': pantalla_p4.estado(),
        })
    except Exception as e:
        return error_interno(e)


@bp.route('/api/pantalla_p4/grabar', methods=['POST'])
@requiere_pin_admin
def api_pantalla_p4_grabar():
    """Compila el .ino desplegado y, salvo solo_compilar, lo sube al puerto.

    Responde al momento; el progreso se consulta en /api/pantalla_p4/estado.
    """
    try:
        data = request.get_json(force=True) or {}
        solo_compilar = bool(data.get('solo_compilar'))
        puerto = str(data.get('puerto', '')).strip()
        if not solo_compilar and (not puerto or not re.fullmatch(r'[A-Za-z0-9/._:-]+', puerto)):
            return jsonify({'success': False, 'message': 'Puerto no válido'}), 400
        variante = str(data.get('variante', 'tactil')).strip()
        if variante not in pantalla_p4.VARIANTES:
            return jsonify({'success': False, 'message': 'Variante no válida'}), 400

        if pantalla_p4.ocupado():
            return jsonify({'success': False,
                            'message': 'Ya hay una grabación en marcha. Espera a que termine.'}), 409
        ok, mensaje = pantalla_p4.lanzar(_proyecto(), current_app.config['DATA_DIR'],
                                         puerto, variante, solo_compilar=solo_compilar)
        if not ok:
            return jsonify({'success': False, 'message': mensaje})
        return jsonify({'success': True, 'trabajo': pantalla_p4.estado()})
    except Exception as e:
        return error_interno(e)
