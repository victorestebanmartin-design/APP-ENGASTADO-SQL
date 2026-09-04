"""
Test de concurrencia para _esp32_write_channel (sistema.py).

Verifica que escrituras simultáneas desde varios puestos del mismo carro
no se pierden (race condition leer-modificar-escribir sobre esp32_canal_*.json).
"""
import json
import threading
import pytest


def test_push_canal_sin_perdida_bajo_concurrencia(app, client):
    """N puestos distintos hacen push al mismo carro simultáneamente;
    al terminar, todas sus entradas deben estar en el canal.
    N <= ESP32_MAX_OPS (8) para que ninguna quede descartada por el límite."""
    N = 8
    errores = []

    def push_puesto(n):
        try:
            r = client.post(
                '/api/esp32/push',
                json={
                    'carro': 'CARRO_TEST',
                    'puesto_id': f'P{n:02d}',
                    'operario': f'op{n}',
                    'lote': 'L1',
                },
            )
            data = r.get_json()
            if not (data and data.get('ok')):
                errores.append(f'puesto P{n:02d}: {data}')
        except Exception as e:
            errores.append(str(e))

    hilos = [threading.Thread(target=push_puesto, args=(i,)) for i in range(N)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, f'Errores durante push concurrente: {errores}'

    # Leer el canal del carro y verificar que no se ha perdido ningún puesto.
    # La API devuelve ops como lista de {'operario': clave, 'data': {...}, 'ts': ...}
    r = client.get('/api/esp32/current?carro=CARRO_TEST')
    data = r.get_json()
    ops = data.get('ops', [])
    puestos_registrados = {item['operario'] for item in ops}
    puestos_esperados = {f'P{n:02d}' for n in range(N)}
    perdidos = puestos_esperados - puestos_registrados
    assert not perdidos, (
        f'Se perdieron {len(perdidos)} puestos bajo concurrencia: {sorted(perdidos)}'
    )


def test_push_canal_global_sin_perdida_bajo_concurrencia(app, client):
    """N puestos distintos hacen push al canal global simultáneamente;
    todas sus entradas deben conservarse.
    N <= ESP32_MAX_OPS (8) para que ninguna quede descartada por el límite."""
    N = 8
    errores = []

    def push_puesto(n):
        try:
            r = client.post(
                '/api/esp32/push',
                json={
                    'puesto_id': f'G{n:02d}',
                    'operario': f'opg{n}',
                    'lote': 'LG',
                },
            )
            data = r.get_json()
            if not (data and data.get('ok')):
                errores.append(f'puesto G{n:02d}: {data}')
        except Exception as e:
            errores.append(str(e))

    hilos = [threading.Thread(target=push_puesto, args=(i,)) for i in range(N)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, f'Errores durante push global concurrente: {errores}'

    r = client.get('/api/esp32/current')
    data = r.get_json()
    ops = data.get('ops', [])
    puestos_registrados = {item['operario'] for item in ops}
    puestos_esperados = {f'G{n:02d}' for n in range(N)}
    perdidos = puestos_esperados - puestos_registrados
    assert not perdidos, (
        f'Se perdieron {len(perdidos)} puestos en canal global: {sorted(perdidos)}'
    )


def test_write_channel_atomico(app, tmp_path):
    """_esp32_write_channel escribe de forma atómica: el fichero nunca queda truncado."""
    from app.routes.sistema import _esp32_write_channel
    import os

    path = str(tmp_path / 'esp32_canal_atomico.json')
    data = {'puesto_id': 'P01', 'operario': 'op1', 'lote': 'L1'}
    ts = '2024-01-01T00:00:00'

    with app.app_context():
        _esp32_write_channel(path, data, ts)

    assert os.path.exists(path)
    with open(path, encoding='utf-8') as f:
        payload = json.load(f)
    assert 'ops' in payload
    assert 'P01' in payload['ops']
