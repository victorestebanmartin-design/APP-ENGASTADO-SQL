"""Observabilidad mínima: peticiones lentas al log y carga por endpoint.

Cuando en planta dicen "va lento" hoy no hay nada que mirar: el log solo tiene
errores. Esto añade, sin dependencias:

* una línea WARNING por cada petición que pasa de ``SLOW_REQUEST_MS`` (1 s por
  defecto), con método, ruta, estado y milisegundos;
* un contador en memoria por endpoint y por minuto, que se consulta en
  ``GET /api/sistema/carga`` (solo admin) para ver de un vistazo qué se está
  sondeando y a qué ritmo.

Todo es best-effort: si algo aquí falla, la petición real no se entera.
"""
import time
from collections import defaultdict, deque

from flask import g, request, jsonify

# Ventana de 5 min: (minuto_epoch -> {endpoint -> nº peticiones, "_lentas" -> n})
_VENTANA_MIN = 5
_por_minuto: "deque" = deque(maxlen=_VENTANA_MIN)
_minuto_actual = [0]
_cuenta_actual: "defaultdict" = defaultdict(int)
# Peor tiempo visto por endpoint en la vida del proceso (ms).
_peor_ms: "defaultdict" = defaultdict(int)


def _rota_minuto(ahora_min):
    if ahora_min != _minuto_actual[0]:
        if _cuenta_actual:
            _por_minuto.append((_minuto_actual[0], dict(_cuenta_actual)))
        _cuenta_actual.clear()
        _minuto_actual[0] = ahora_min


def instalar(app):
    umbral_ms = int(app.config.get('SLOW_REQUEST_MS', 1000))

    @app.before_request
    def _marca_inicio():
        g._obs_t0 = time.monotonic()

    @app.after_request
    def _registra(resp):
        try:
            t0 = g.pop('_obs_t0', None)
            if t0 is None:
                return resp
            ms = int((time.monotonic() - t0) * 1000)
            ep = request.endpoint or request.path or '?'

            ahora_min = int(time.time() // 60)
            _rota_minuto(ahora_min)
            _cuenta_actual[ep] += 1
            if ms > _peor_ms[ep]:
                _peor_ms[ep] = ms

            if ms >= umbral_ms:
                _cuenta_actual['_lentas'] += 1
                app.logger.warning('LENTA %d ms  %s %s -> %s',
                                   ms, request.method, request.full_path.rstrip('?'),
                                   resp.status_code)
        except Exception:
            pass
        return resp

    # Import local para no crear un ciclo con app.routes.
    from app.routes.base import bp
    from app.auth import requiere_pin_admin

    @bp.route('/api/sistema/carga', methods=['GET'])
    @requiere_pin_admin
    def api_sistema_carga():
        _rota_minuto(int(time.time() // 60))
        minutos = list(_por_minuto) + [(_minuto_actual[0], dict(_cuenta_actual))]
        total = defaultdict(int)
        for _m, cuenta in minutos:
            for ep, n in cuenta.items():
                total[ep] += n
        n_min = max(1, len(minutos))
        filas = sorted(
            ({'endpoint': ep, 'total': n, 'req_por_s': round(n / (n_min * 60), 2),
              'peor_ms': _peor_ms.get(ep, 0)}
             for ep, n in total.items() if ep != '_lentas'),
            key=lambda f: f['total'], reverse=True)
        return jsonify({
            'success': True,
            'ventana_min': n_min,
            'req_por_s_total': round(sum(f['total'] for f in filas) / (n_min * 60), 2),
            'lentas': total.get('_lentas', 0),
            'umbral_ms': umbral_ms,
            'endpoints': filas,
        })
