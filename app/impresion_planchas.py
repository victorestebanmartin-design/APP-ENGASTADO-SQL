"""
Impresión de la plancha de etiquetas desde el servidor.

Los PCs cliente solo ven la red local; la impresora (HP en red) la ve el
servidor. El cliente pide la impresión y es el servidor quien convierte la
plancha a PDF y se la manda a la impresora.

Garantías de "nada sale al exterior" (el servidor SÍ tiene internet):
  * La impresora se identifica solo por IP privada (RFC1918). Nunca por nombre
    de host, así que no hay DNS, y una IP pública se rechaza.
  * El navegador que genera el PDF se lanza sin red: todo nombre de host se
    resuelve a "no encontrado", sin actualizaciones ni servicios en segundo
    plano, y solo abre un fichero local con HTML sin recursos externos.
  * El PDF se envía por un socket TCP directo al puerto de la impresora.
"""
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time

PUERTO_DEFECTO = 9100
_candado = threading.Lock()  # una plancha cada vez: no se mezclan dos impresiones


class ErrorImpresion(Exception):
    """Fallo esperable (sin impresora, sin navegador...). El mensaje es legible."""


def _fichero_config(data_dir):
    return os.path.join(data_dir, 'impresora.json')


def leer_config(data_dir):
    try:
        with open(_fichero_config(data_dir), encoding='utf-8') as f:
            datos = json.load(f)
    except (OSError, ValueError):
        datos = {}
    return {'ip': str(datos.get('ip') or ''),
            'puerto': int(datos.get('puerto') or PUERTO_DEFECTO)}


def validar_ip_privada(valor):
    """Devuelve la IP normalizada o lanza ErrorImpresion si no es de la red local."""
    try:
        ip = ipaddress.ip_address(str(valor).strip())
    except ValueError:
        raise ErrorImpresion('Escribe la IP de la impresora (por ejemplo 192.168.1.50), no un nombre.')
    if not ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_multicast:
        raise ErrorImpresion('Por seguridad solo se admiten IPs de la red local (192.168.x.x, 10.x.x.x, 172.16-31.x.x).')
    return str(ip)


def guardar_config(data_dir, ip, puerto=PUERTO_DEFECTO):
    ip = validar_ip_privada(ip)
    with open(_fichero_config(data_dir), 'w', encoding='utf-8') as f:
        json.dump({'ip': ip, 'puerto': int(puerto)}, f)
    return ip


def _buscar_navegador():
    candidatos = [
        os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('ProgramFiles', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('ProgramFiles', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ]
    for ruta in candidatos:
        if os.path.isfile(ruta):
            return ruta
    for nombre in ('msedge', 'microsoft-edge', 'google-chrome', 'chromium', 'chromium-browser'):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    raise ErrorImpresion('Este servidor no tiene Edge ni Chrome para generar el PDF de la plancha.')


def _esperar_fichero(ruta, segundos):
    """True cuando el fichero existe y su tamaño ya no cambia (PDF terminado)."""
    limite = time.time() + segundos
    ultimo = -1
    while time.time() < limite:
        if os.path.isfile(ruta):
            tam = os.path.getsize(ruta)
            if tam > 0 and tam == ultimo:
                return True
            ultimo = tam
        time.sleep(0.5)
    return False


def html_a_pdf(html, timeout=60):
    """Convierte la plancha (HTML autocontenido) a PDF con el navegador, sin red."""
    navegador = _buscar_navegador()
    with tempfile.TemporaryDirectory(prefix='plancha_', ignore_cleanup_errors=True) as tmp:
        fichero_html = os.path.join(tmp, 'plancha.html')
        fichero_pdf = os.path.join(tmp, 'plancha.pdf')
        with open(fichero_html, 'w', encoding='utf-8') as f:
            f.write(html)
        base = [
            navegador,
            '{modo}',
            '--disable-gpu',
            '--no-first-run',
            '--no-default-browser-check',
            '--user-data-dir=' + os.path.join(tempfile.gettempdir(), 'plancha_perfil'),
            # Sin red: cualquier nombre de host no se resuelve.
            '--host-resolver-rules=MAP * ~NOTFOUND',
            '--disable-background-networking',
            '--disable-component-update',
            '--disable-sync',
            '--disable-features=OptimizationHints,MediaRouter,Translate',
            '--no-pdf-header-footer',
            '--print-to-pdf=' + fichero_pdf,
            'file:///' + fichero_html.replace('\\', '/'),
        ]
        # Según la versión, solo uno de los dos modos headless escribe el PDF
        # (Edge/Chrome recientes quitaron el "old"), así que se prueban ambos.
        # El lanzador de Edge devuelve el control antes de terminar el PDF:
        # no basta con esperar al proceso, hay que esperar al fichero.
        for modo in ('--headless=old', '--headless=new'):
            cmd = [modo if a == '{modo}' else a for a in base]
            subprocess.run(cmd, capture_output=True, timeout=timeout, check=False,
                           stdin=subprocess.DEVNULL)
            if _esperar_fichero(fichero_pdf, 20):
                break
        else:
            raise ErrorImpresion('No se pudo generar el PDF de la plancha.')
        with open(fichero_pdf, 'rb') as f:
            return f.read()


def enviar_a_impresora(pdf, ip, puerto=PUERTO_DEFECTO):
    ip = validar_ip_privada(ip)
    try:
        with socket.create_connection((ip, int(puerto)), timeout=8) as s:
            s.settimeout(60)
            s.sendall(pdf)
    except OSError as e:
        raise ErrorImpresion(
            f'No se pudo contactar con la impresora en {ip}:{puerto} ({e.__class__.__name__}). '
            'Comprueba que está encendida y conectada a la red.')


def imprimir_plancha(html, data_dir):
    """Genera el PDF y lo manda a la impresora configurada. Devuelve la IP usada."""
    cfg = leer_config(data_dir)
    if not cfg['ip']:
        raise ErrorImpresion('Todavía no hay impresora configurada.')
    if not _candado.acquire(blocking=False):
        raise ErrorImpresion('Ya se está imprimiendo otra plancha; espera unos segundos.')
    try:
        pdf = html_a_pdf(html)
        enviar_a_impresora(pdf, cfg['ip'], cfg['puerto'])
        return cfg['ip']
    finally:
        _candado.release()
