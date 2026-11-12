"""El historial que abre la insignia de version (CAMBIOS.md).

Si falla el primero: has subido VERSION sin anadir su entrada arriba del todo
en CAMBIOS.md. Escribela en palabras de planta (que cambia para quien usa la
app), no la saltes.
"""
from app import version


def test_la_version_actual_esta_arriba_del_historial():
    hist = version.historial()
    assert hist, 'CAMBIOS.md no existe o no tiene entradas'
    assert hist[0]['version'] == version.actual()
    assert hist[0]['cambios'], 'la entrada de la version actual no dice que cambia'


def test_versiones_sin_repetir():
    vistas = [e['version'] for e in version.historial()]
    assert len(vistas) == len(set(vistas))


def test_endpoint_sin_login(client):
    r = client.get('/api/version/cambios')
    assert r.status_code == 200
    datos = r.get_json()
    assert datos['version'] == version.actual()
    assert datos['historial'][0]['version'] == datos['version']
