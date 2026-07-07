"""Tests de imágenes y gavetas de terminales, y del report por carro."""

# data URL mínima válida (PNG 1x1 transparente)
IMG_OK = ('data:image/png;base64,'
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


# ── Imágenes de terminal ──────────────────────────────────────────────────────

def test_imagen_terminal_ciclo_completo(admin_client):
    # Sin imagen aún
    r = admin_client.get('/api/terminal-imagen/640204')
    assert r.status_code == 200 and r.get_json()['imagen_data'] is None

    # Guardar
    r = admin_client.put('/api/terminal-imagen/640204', json={'imagen_data': IMG_OK})
    assert r.status_code == 200 and r.get_json()['success']

    # Leer
    r = admin_client.get('/api/terminal-imagen/640204')
    assert r.get_json()['imagen_data'] == IMG_OK

    # Borrar
    r = admin_client.delete('/api/terminal-imagen/640204')
    assert r.get_json()['success']
    assert admin_client.get('/api/terminal-imagen/640204').get_json()['imagen_data'] is None


def test_imagen_terminal_rechaza_formato_no_imagen(admin_client):
    r = admin_client.put('/api/terminal-imagen/T1', json={'imagen_data': 'no-soy-una-imagen'})
    assert r.status_code == 400


def test_imagen_terminal_rechaza_demasiado_grande(admin_client):
    grande = 'data:image/png;base64,' + ('A' * 500_000)
    r = admin_client.put('/api/terminal-imagen/T1', json={'imagen_data': grande})
    assert r.status_code == 400


def test_imagen_terminal_escritura_requiere_pin(client):
    # Sin sesión de admin: PUT y DELETE deben dar 401; GET sigue siendo público
    assert client.put('/api/terminal-imagen/T1', json={'imagen_data': IMG_OK}).status_code == 401
    assert client.delete('/api/terminal-imagen/T1').status_code == 401
    assert client.get('/api/terminal-imagen/T1').status_code == 200


# ── Gavetas de terminal ───────────────────────────────────────────────────────

def test_gaveta_terminal_ciclo_completo(admin_client):
    r = admin_client.get('/api/terminal-gaveta/640204')
    assert r.status_code == 200 and r.get_json()['gaveta'] is None

    r = admin_client.put('/api/terminal-gaveta/640204', json={'gaveta': 'Estante 3-B'})
    assert r.status_code == 200 and r.get_json()['gaveta'] == 'Estante 3-B'

    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['gaveta'] == 'Estante 3-B'

    r = admin_client.delete('/api/terminal-gaveta/640204')
    assert r.get_json()['success']
    assert admin_client.get('/api/terminal-gaveta/640204').get_json()['gaveta'] is None


def test_gaveta_vacia_se_rechaza(admin_client):
    r = admin_client.put('/api/terminal-gaveta/T1', json={'gaveta': '   '})
    assert r.status_code == 400


def test_gaveta_escritura_requiere_pin(client):
    assert client.put('/api/terminal-gaveta/T1', json={'gaveta': 'X'}).status_code == 401
    assert client.delete('/api/terminal-gaveta/T1').status_code == 401


# ── Escritura de máquinas/terminales ahora protegida ──────────────────────────

def test_maquinas_escritura_requiere_pin(client):
    assert client.post('/api/maquinas', json={'nombre': 'X', 'puesto_id': 'puesto_4'}).status_code == 401
    assert client.put('/api/maquinas/xyz', json={'nombre': 'X'}).status_code == 401
    assert client.delete('/api/maquinas/xyz').status_code == 401
    assert client.post('/api/asignar-terminal', json={}).status_code == 401
    assert client.post('/api/desasignar-terminal', json={}).status_code == 401


def test_maquinas_lectura_sigue_publica(client):
    assert client.get('/api/maquinas').status_code == 200
    assert client.get('/api/terminales-disponibles').status_code == 200


# ── Report por carro ──────────────────────────────────────────────────────────

def test_report_carros_bono_inexistente(client):
    assert client.get('/report/bono/NO_EXISTE/carros').status_code == 404


def test_report_carros_bono_responde(client):
    client.post('/api/bonos', json={'nombre': 'B_REPORT', 'ordenes_ids': []})
    r = client.get('/report/bono/B_REPORT/carros')
    assert r.status_code == 200
    assert 'B_REPORT' in r.get_data(as_text=True)


# ── El schema crea las tablas nuevas en una BD limpia ─────────────────────────

def test_tablas_nuevas_existen_en_bd_nueva(app):
    from sqlalchemy import text
    db = app.extensions['db']
    with db.engine.connect() as conn:
        for tabla in ('terminales_imagenes', 'terminales_gavetas', 'cable_colores'):
            n = conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:t"
            ), {'t': tabla}).scalar()
            assert n == 1, f'falta la tabla {tabla}'
