"""
Tests para la restricción UNIQUE en proyectos.carro_asignado.

Verifica que la BD y la API impiden asignar el mismo carro a dos proyectos,
mientras siguen permitiendo múltiples proyectos sin carro (NULL).
"""
import threading
import pytest


def _crear_proyecto(client, nombre, archivo='test.xlsx', carro=None):
    """Helper: crea un proyecto y devuelve su ID."""
    r = client.post('/api/proyectos', json={
        'nombre': nombre,
        'archivo': archivo,
        'carro_asignado': carro,
    })
    data = r.get_json()
    assert data['success'], f'No se pudo crear proyecto {nombre!r}: {data}'
    return data['proyecto']['id']


def _asignar_carro(client, proyecto_id, carro_numero):
    """Helper: llama al endpoint de asignación de carro."""
    return client.put(
        f'/api/proyectos/{proyecto_id}/carro',
        json={'carro_numero': carro_numero},
    )


# ── Test 1: asignar un carro libre → OK ──────────────────────────────────────

def test_asignar_carro_libre_ok(client):
    """Un carro libre puede asignarse sin problema."""
    pid = _crear_proyecto(client, 'Proyecto A')
    r = _asignar_carro(client, pid, 3)
    assert r.status_code == 200
    data = r.get_json()
    assert data['success']
    assert data['proyecto']['carro_asignado'] == 3


# ── Test 2: dos proyectos sin carro → OK ─────────────────────────────────────

def test_dos_proyectos_sin_carro_ok(client):
    """Dos proyectos con carro_asignado = NULL coexisten sin problema."""
    pid1 = _crear_proyecto(client, 'Sin carro 1')
    pid2 = _crear_proyecto(client, 'Sin carro 2')

    # Liberar carro de ambos (deberían estar ya en NULL, pero forzamos)
    r1 = client.put(f'/api/proyectos/{pid1}/carro', json={'carro_numero': None})
    r2 = client.put(f'/api/proyectos/{pid2}/carro', json={'carro_numero': None})
    assert r1.get_json()['success']
    assert r2.get_json()['success']

    # Verificar que ambos existen y tienen carro_asignado = null
    info1 = client.get(f'/api/proyectos').get_json()
    ids_obtenidos = {p['id'] for p in info1['proyectos']}
    assert pid1 in ids_obtenidos
    assert pid2 in ids_obtenidos


# ── Test 3: asignar NULL (liberar carro) → OK ─────────────────────────────────

def test_asignar_null_libera_carro(client):
    """Liberar un carro (asignar NULL) funciona correctamente."""
    pid = _crear_proyecto(client, 'Proyecto B')
    _asignar_carro(client, pid, 2)

    # Liberar
    r = client.put(f'/api/proyectos/{pid}/carro', json={'carro_numero': None})
    assert r.status_code == 200
    assert r.get_json()['success']
    assert r.get_json()['proyecto']['carro_asignado'] is None


# ── Test 4: intentar asignar un carro ya utilizado → 409 ─────────────────────

def test_asignar_carro_duplicado_devuelve_409(client):
    """Asignar un carro ya ocupado debe devolver 409 con código CARRO_DUPLICADO."""
    pid1 = _crear_proyecto(client, 'Proyecto C')
    pid2 = _crear_proyecto(client, 'Proyecto D')

    _asignar_carro(client, pid1, 5)  # Carro 5 → proyecto C

    # Intentar asignar el mismo carro al proyecto D
    r = _asignar_carro(client, pid2, 5)
    assert r.status_code == 409
    data = r.get_json()
    assert data['success'] is False
    assert data.get('code') == 'CARRO_DUPLICADO'

    # Verificar que el proyecto D no tiene carro asignado
    r_lista = client.get('/api/proyectos').get_json()
    proyecto_d = next(p for p in r_lista['proyectos'] if p['id'] == pid2)
    assert proyecto_d['carro_asignado'] is None


# ── Test 5: dos peticiones simultáneas al mismo carro → solo una triunfa ─────

def test_asignacion_simultanea_solo_una_gana(client):
    """Dos hilos intentan asignar el carro 4 a distintos proyectos al mismo tiempo.
    La BD garantiza que exactamente uno de ellos tiene éxito (el otro recibe 409).
    """
    pid1 = _crear_proyecto(client, 'Concurrente E')
    pid2 = _crear_proyecto(client, 'Concurrente F')

    resultados = {}

    def asignar(pid, etiqueta):
        r = _asignar_carro(client, pid, 4)
        resultados[etiqueta] = r.status_code

    h1 = threading.Thread(target=asignar, args=(pid1, 'E'))
    h2 = threading.Thread(target=asignar, args=(pid2, 'F'))
    h1.start()
    h2.start()
    h1.join()
    h2.join()

    codigos = list(resultados.values())
    assert 200 in codigos, f'Ninguno tuvo éxito: {resultados}'
    assert 409 in codigos, f'Ambos tuvieron éxito (debería ser imposible): {resultados}'

    # Confirmar que solo uno de los proyectos tiene el carro asignado
    lista = client.get('/api/proyectos').get_json()['proyectos']
    con_carro_4 = [p for p in lista if p.get('carro_asignado') == 4]
    assert len(con_carro_4) == 1, (
        f'Se esperaba exactamente 1 proyecto con carro 4, hay {len(con_carro_4)}'
    )
