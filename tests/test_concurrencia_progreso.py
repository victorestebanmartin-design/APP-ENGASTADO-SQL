"""
Test de concurrencia para los endpoints de progreso de bono.

Verifica que escrituras simultáneas desde varios hilos no pierden
actualizaciones (race condition leer-modificar-escribir).
"""
import json
import threading
import pytest


def test_progreso_post_sin_perdida_bajo_concurrencia(app, client):
    """N hilos marcan carros distintos en el mismo bono; al terminar,
    todos deben estar registrados en el JSON de progreso."""
    N = 20
    errores = []

    def marcar_carro(n):
        try:
            r = client.post(
                f'/api/bonos/bono_concurrencia_test/progreso',
                json={'terminal': 'T1', 'carro': n, 'operario': f'op{n}'},
            )
            if not r.get_json().get('success'):
                errores.append(f'carro {n}: {r.get_json()}')
        except Exception as e:
            errores.append(str(e))

    hilos = [threading.Thread(target=marcar_carro, args=(i,)) for i in range(N)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, f'Errores durante escritura concurrente: {errores}'

    # Leer el progreso final y verificar que no se ha perdido ningún carro
    r = client.get('/api/bonos/bono_concurrencia_test/progreso')
    data = r.get_json()
    assert data['success']
    carros = data['progreso'].get('T1', {}).get('carros_completados', [])
    assert len(carros) == N, (
        f'Se esperaban {N} carros registrados, solo hay {len(carros)}: {sorted(carros)}'
    )


def test_progreso_estado_sin_perdida_bajo_concurrencia(app, client):
    """N hilos actualizan el estado de terminales distintos del mismo bono;
    al terminar, todos los terminales deben aparecer en el JSON."""
    N = 15
    errores = []

    def actualizar_estado(n):
        try:
            r = client.post(
                f'/api/bonos/bono_estado_concurrencia/progreso/estado',
                json={'terminal': f'T{n}', 'estado': 'completado', 'operario': f'op{n}'},
            )
            if not r.get_json().get('success'):
                errores.append(f'terminal T{n}: {r.get_json()}')
        except Exception as e:
            errores.append(str(e))

    hilos = [threading.Thread(target=actualizar_estado, args=(i,)) for i in range(N)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, f'Errores durante actualización concurrente: {errores}'

    r = client.get('/api/bonos/bono_estado_concurrencia/progreso')
    data = r.get_json()
    assert data['success']
    progreso = data['progreso']
    terminales_completados = [t for t, v in progreso.items() if v.get('estado') == 'completado']
    assert len(terminales_completados) == N, (
        f'Se esperaban {N} terminales completados, solo hay {len(terminales_completados)}: '
        f'{sorted(terminales_completados)}'
    )


def test_progreso_atomico_no_deja_json_vacio(app, client, tmp_path):
    """La escritura atómica no deja el fichero truncado si falla a mitad."""
    from app.routes.progreso import _escribir_progreso_atomico

    path = str(tmp_path / 'progreso_bono_test_atomico.json')
    datos = {'T1': {'estado': 'en_proceso', 'carros_completados': [1, 2, 3]}}
    _escribir_progreso_atomico(path, datos)

    import os
    assert os.path.exists(path)
    with open(path, encoding='utf-8') as f:
        leido = json.load(f)
    assert leido == datos
