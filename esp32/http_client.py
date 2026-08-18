# http_client.py -- Cliente HTTP/HTTPS minimo para MicroPython (ESP32 clasico).
#
# No depende de 'urequests' (no viene en el firmware base y hay que instalarla
# aparte). Usa sockets crudos + ussl para TLS, igual de ligero que el patron ya
# probado en la pantalla de carro (main_wifi.py), pero con soporte HTTPS.
#
# NO se toca por OTA: main.py se actualiza solo via ota_update.py, que
# depende de este fichero, asi que si algo fallara aqui nunca podria venir de
# una actualizacion remota (solo de una subida manual por USB).
#
# Aviso: ussl en MicroPython no valida el certificado del servidor por
# defecto (cifra la conexion pero no comprueba la identidad). Suficiente para
# este uso (actualizar firmware propio y mandar una lectura RFID), no para
# datos sensibles.

import socket
import time
import json as _json

try:
    import ussl as _ssl
except ImportError:
    import ssl as _ssl


class ErrorConexion(Exception):
    """Fallo ANTES de mandar nada (DNS, socket, connect, handshake TLS).

    Se distingue a proposito del resto: si no llego a salir un byte, el
    servidor no ha visto la peticion y reintentarla es seguro. Un fallo
    POSTERIOR no lo es -- el servidor puede haberla procesado y solo haberse
    perdido la respuesta, y repetir un POST duplicaria el fichaje.
    """


def _request(host, path, port, use_ssl, timeout, method="GET", body_bytes=None):
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(timeout)
        s.connect(addr)
        if use_ssl:
            s = _ssl.wrap_socket(s, server_hostname=host)
    except Exception as e:
        raise ErrorConexion(e)

    headers = "Host: %s\r\nConnection: close\r\n" % host
    if body_bytes is not None:
        headers += "Content-Type: application/json\r\nContent-Length: %d\r\n" % len(body_bytes)
    req = "%s %s HTTP/1.0\r\n%s\r\n" % (method, path, headers)
    s.write(req.encode())
    if body_bytes is not None:
        s.write(body_bytes)

    resp = b""
    while True:
        chunk = s.read(1024)
        if not chunk:
            break
        resp += chunk
    s.close()

    idx = resp.find(b"\r\n\r\n")
    if idx < 0:
        return None, None
    head, raw_body = resp[:idx], resp[idx + 4:]

    status = None
    clen = None
    for i, line in enumerate(head.split(b"\r\n")):
        if i == 0:
            try:
                status = int(line.split(b" ")[1])
            except Exception:
                status = None
        elif line[:15].lower() == b"content-length:":
            try:
                clen = int(line.split(b":", 1)[1].strip())
            except Exception:
                clen = None

    if clen is not None and len(raw_body) != clen:
        return None, None  # cuerpo incompleto: no fiarse de una descarga a medias
    return status, raw_body


# Un socket TCP nuevo por peticion (Connection: close) tiene un punto flojo:
# si el SYN inicial se pierde -- cosa normal en WiFi -- la pila TCP no lo
# reintenta hasta pasados ~3s, y otra vez a los ~6s. Esos son los "a veces
# tarda 5-7 segundos" que no explica el servidor (responde en menos de 1 ms).
# Un reintento propio y rapido convierte esa espera en menos de medio segundo.
REINTENTOS = 2
ESPERA_REINTENTO_MS = 250


def _request_reintentando(host, path, port, use_ssl, timeout, method="GET", body_bytes=None):
    """_request reintentando SOLO lo que es seguro reintentar.

    Un ErrorConexion (no salio ni un byte) se reintenta siempre. Cualquier
    otro fallo solo se reintenta en un GET, que es idempotente: repetir un
    POST cuyo resultado se perdio duplicaria el fichaje en el servidor.
    """
    ultimo = None
    for intento in range(REINTENTOS):
        try:
            return _request(host, path, port, use_ssl, timeout, method, body_bytes)
        except ErrorConexion as e:
            ultimo = e
        except Exception as e:
            if method != "GET":
                raise
            ultimo = e
        if intento + 1 < REINTENTOS:
            time.sleep_ms(ESPERA_REINTENTO_MS)
    raise ultimo


def get_bytes(host, path, port=443, use_ssl=True, timeout=15):
    """GET -> bytes crudos del cuerpo si status 200, o None ante cualquier fallo."""
    try:
        status, body = _request_reintentando(host, path, port, use_ssl, timeout, "GET")
        return body if status == 200 else None
    except Exception as e:
        print("http_client GET error:", e)
        return None


def get_json(host, path, port=443, use_ssl=True, timeout=15):
    """GET -> dict/list parseado de JSON, o None ante cualquier fallo."""
    data = get_bytes(host, path, port, use_ssl, timeout)
    if data is None:
        return None
    try:
        return _json.loads(data)
    except Exception:
        return None


def post_json(host, path, obj, port=443, use_ssl=True, timeout=15):
    """POST de un dict como JSON. Devuelve (status, dict_respuesta_o_None).

    status es None si la peticion no pudo completarse (red caida, timeout).
    """
    try:
        body_bytes = _json.dumps(obj).encode("utf-8")
        status, body = _request_reintentando(host, path, port, use_ssl, timeout, "POST", body_bytes)
        parsed = None
        if body is not None:
            try:
                parsed = _json.loads(body)
            except Exception:
                parsed = None
        return status, parsed
    except Exception as e:
        print("http_client POST error:", e)
        return None, None
