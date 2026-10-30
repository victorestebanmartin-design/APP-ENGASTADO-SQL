"""
El bloqueo de un paquete solo vale dentro de su orden.

Dos bonos pueden llevar un paquete con el mismo cable y elemento (el mismo Excel
incluso); un operario trabajando en uno no puede bloquear al del otro. Solo
bloquea quien está en el MISMO paquete de la MISMA orden.
"""
from app.routes.base import db
from repositories.sesion_trabajo_repository import SesionTrabajoRepository

PAQ = [{'cod_cable': 'C1', 'elemento': 'TB1'}]


def _repo(app):
    return SesionTrabajoRepository(db)


def _sesion(repo, maquina, orden_id, archivo='corte.xlsx', paquetes=PAQ):
    sid = repo.crear_sesion(maquina, 'T1', archivo, '1', [], orden_id=orden_id)
    repo.actualizar_paquetes_sesion(sid, paquetes)
    return sid


def test_misma_orden_bloquea(app):
    with app.app_context():
        repo = _repo(app)
        _sesion(repo, 'M1', 'orden-A')
        propia = _sesion(repo, 'M2', 'orden-A')
        bloqueos = repo.verificar_bloqueos(PAQ, sesion_id_excluir=propia)
        assert ('C1', 'TB1') in bloqueos
        assert bloqueos[('C1', 'TB1')]['maquina_id'] == 'M1'


def test_otra_orden_con_el_mismo_excel_no_bloquea(app):
    with app.app_context():
        repo = _repo(app)
        _sesion(repo, 'M1', 'orden-A', archivo='mismo.xlsx')
        propia = _sesion(repo, 'M2', 'orden-B', archivo='mismo.xlsx')
        assert repo.verificar_bloqueos(PAQ, sesion_id_excluir=propia) == {}


def test_consulta_sin_sesion_usa_la_orden_indicada(app):
    with app.app_context():
        repo = _repo(app)
        _sesion(repo, 'M1', 'orden-A')
        assert ('C1', 'TB1') in repo.verificar_bloqueos(PAQ, orden_id='orden-A')
        assert repo.verificar_bloqueos(PAQ, orden_id='orden-B') == {}


def test_misma_orden_otro_paquete_no_bloquea(app):
    with app.app_context():
        repo = _repo(app)
        _sesion(repo, 'M1', 'orden-A', paquetes=[{'cod_cable': 'C1', 'elemento': 'TB2'}])
        assert repo.verificar_bloqueos(PAQ, orden_id='orden-A') == {}


def test_sesion_sin_orden_solo_se_cruza_por_archivo(app):
    """Sesiones antiguas (sin orden) no bloquean a una orden concreta."""
    with app.app_context():
        repo = _repo(app)
        _sesion(repo, 'M1', None, archivo='a.xlsx')
        assert repo.verificar_bloqueos(PAQ, orden_id='orden-A', archivo='a.xlsx') == {}
        assert ('C1', 'TB1') in repo.verificar_bloqueos(PAQ, archivo='a.xlsx')
        assert repo.verificar_bloqueos(PAQ, archivo='b.xlsx') == {}


def test_sin_ambito_conserva_el_comportamiento_antiguo(app):
    with app.app_context():
        repo = _repo(app)
        _sesion(repo, 'M1', 'orden-A')
        assert ('C1', 'TB1') in repo.verificar_bloqueos(PAQ)


def test_endpoint_verificar_pendientes_por_orden(app, client):
    with app.app_context():
        repo = _repo(app)
        _sesion(repo, 'M1', 'orden-A')
        propia_b = _sesion(repo, 'M2', 'orden-B')
        propia_a = _sesion(repo, 'M3', 'orden-A')

    r = client.post('/api/sesion/verificar-pendientes',
                    json={'paquetes': PAQ, 'sesion_id_excluir': propia_b}).get_json()
    assert r['num_bloqueados'] == 0 and r['num_libres'] == 1

    r = client.post('/api/sesion/verificar-pendientes',
                    json={'paquetes': PAQ, 'sesion_id_excluir': propia_a}).get_json()
    assert r['num_bloqueados'] == 1 and r['bloqueados'][0]['bloqueado_por']

    r = client.post('/api/sesion/verificar-pendientes',
                    json={'paquetes': PAQ, 'orden_id': 'orden-C'}).get_json()
    assert r['num_bloqueados'] == 0
