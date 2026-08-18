"""Latencia de las placas: de que depende y que no puede volver a torcerse.

El servidor responde a los endpoints calientes en menos de 1 ms, asi que la
lentitud que se ve en planta no sale de aqui: sale de los intervalos de
sondeo y del enlace WiFi. Estos tests fijan las dos decisiones.
"""
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _leer(rel):
    with open(os.path.join(BASE, rel), encoding='utf-8') as f:
        return f.read()


# ── El servidor no puede ser el cuello de botella ─────────────────────────

def test_el_poll_de_la_pantalla_es_barato(client):
    """Si este endpoint se encarece, subir la frecuencia de sondeo deja de
    ser gratis. Se mide en ms, no en 'parece rapido'."""
    import time
    client.get('/api/esp32/current?id=aabbcc&fw=x')      # calentar
    t0 = time.perf_counter()
    for _ in range(50):
        client.get('/api/esp32/current?id=aabbcc&fw=x')
    media_ms = (time.perf_counter() - t0) / 50 * 1000
    assert media_ms < 25, f'{media_ms:.1f} ms por poll: demasiado para sondear cada segundo'


def test_el_sondeo_de_logins_es_barato(client):
    import time
    client.get('/api/operarios/logins')
    t0 = time.perf_counter()
    for _ in range(50):
        client.get('/api/operarios/logins')
    media_ms = (time.perf_counter() - t0) / 50 * 1000
    assert media_ms < 25, f'{media_ms:.1f} ms por sondeo: demasiado para cada 750 ms'


# ── Intervalos de sondeo ──────────────────────────────────────────────────

def test_la_pantalla_sondea_al_menos_cada_segundo():
    m = re.search(r'^POLL_INTERVAL\s*=\s*(\d+)', _leer('esp32/micropython/main_wifi.py'), re.M)
    assert m and int(m.group(1)) <= 1, 'la pantalla tardaria mas de 1s en pintar un paquete'


def test_el_navegador_sondea_los_logins_al_menos_cada_750ms():
    m = re.search(r'intervalMs\s*\|\|\s*(\d+)', _leer('static/js/shared/rfid-login.js'))
    assert m and int(m.group(1)) <= 750, 'la app tardaria de mas en reaccionar a una tarjeta'


# ── Ahorro de energia WiFi ────────────────────────────────────────────────

def test_las_placas_desactivan_el_ahorro_de_energia_wifi():
    """Con el ahorro por defecto (WIFI_PS_MIN_MODEM) el punto de acceso
    retiene los paquetes hasta que la placa despierta, y eso mete cientos de
    ms en cada respuesta. Es la causa principal de la lentitud percibida."""
    for rel in ('esp32/boot.py', 'esp32/micropython/main_wifi.py'):
        assert 'PM_NONE' in _leer(rel), rel


def test_el_ahorro_se_desactiva_antes_de_conectar():
    """pm se fija sobre la interfaz ya activa y antes del connect, para que
    la primera peticion tras arrancar tampoco pague la espera."""
    boot = _leer('esp32/boot.py')
    assert boot.index('PM_NONE') < boot.index('wlan.connect(')


# ── Reintento rapido, sin duplicar fichajes ───────────────────────────────

def test_solo_se_reintenta_lo_que_es_seguro_reintentar():
    """Un POST que el servidor ya proceso NO puede repetirse: duplicaria la
    entrada del operario. Solo se reintenta si no llego a salir un byte
    (ErrorConexion) o si es un GET, que es idempotente."""
    http = _leer('esp32/http_client.py')
    assert 'class ErrorConexion' in http
    # El reintento generico esta acotado a GET
    cuerpo = http[http.index('def _request_reintentando'):]
    cuerpo = cuerpo[:cuerpo.index('\ndef ', 1)]
    assert 'except ErrorConexion' in cuerpo
    assert 'if method != "GET":' in cuerpo and 'raise' in cuerpo


def test_el_fallo_al_conectar_se_marca_como_reintentable():
    """El connect/getaddrinfo/handshake va envuelto para poder distinguirlo
    de un fallo posterior."""
    http = _leer('esp32/http_client.py')
    cuerpo = http[http.index('def _request('):]
    cuerpo = cuerpo[:cuerpo.index('\ndef ', 1)]
    antes_de_escribir = cuerpo[:cuerpo.index('s.write(')]
    assert 'raise ErrorConexion' in antes_de_escribir
    assert 's.connect(addr)' in antes_de_escribir
