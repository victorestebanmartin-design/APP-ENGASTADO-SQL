"""Grabar la pantalla grande del carro (ESP32-P4 de 10,1") desde Admin.

Las placas de MicroPython reciben el .py tal cual; la P4 lleva un sketch de
Arduino (esp32/pantalla_p4_101/pantalla_p4_101.ino) que hay que COMPILAR antes
de grabarlo. Esto hace lo mismo que `compilar.sh COM6`, pero desde el
navegador: compila el .ino del codigo desplegado con arduino-cli y lo sube por
USB al puerto elegido.

- Solo funciona en el PC que tenga arduino-cli + core esp32 + librerias
  (el de fabrica). Sin ellos se dice que falta, no se rompe nada.
- Siempre se compila antes de subir: arduino-cli reutiliza lo ya compilado en
  la carpeta de build, asi que si el .ino no ha cambiado tarda segundos, y si
  ha cambiado nunca se graba un binario viejo. La primera vez (LVGL entera)
  tarda varios minutos, por eso va en un hilo y el navegador consulta el
  estado.
- Una sola grabacion a la vez: dos arduino-cli sobre la misma carpeta de build
  o el mismo puerto se pisarian.
- La P4 no tiene WiFi propia (habla con el carro por UART): no hay OTA, siempre
  es por USB.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque

# Las placas que se pueden grabar desde aqui. 'notouch' = paneles sin GT911
# (mismo interruptor que `compilar.sh ... notouch`).
VARIANTES = {
    'tactil':  {'nombre': 'Con táctil',  'flags': ''},
    'notouch': {'nombre': 'Sin táctil', 'flags': '-DHAS_TOUCH=0'},
}

# Tiempos maximos. Constantes de modulo para que los tests puedan bajarlas.
TIMEOUT_COMPILAR_S = 30 * 60   # LVGL desde cero ronda 7 min en el PC de fabrica
TIMEOUT_SUBIR_S = 5 * 60
LINEAS_LOG = 60

_SIN_VENTANA = 0x08000000 if sys.platform == 'win32' else 0   # CREATE_NO_WINDOW

_lock = threading.Lock()
_hilo = None
_estado = {'fase': 'libre'}   # libre | compilando | subiendo | ok | error


# ---------------------------------------------------------------- rutas y config

def dir_sketch(proyecto):
    return os.path.join(proyecto, 'esp32', 'pantalla_p4_101')


def fqbn(proyecto):
    """El FQBN sale de compilar.sh, que es la referencia (una sola verdad).

    Si no se encuentra se devuelve None y no se graba: un FQBN equivocado
    (otra particion, otro modelo de panel) deja la pantalla en negro.
    """
    try:
        with open(os.path.join(dir_sketch(proyecto), 'compilar.sh'), encoding='utf-8') as f:
            m = re.search(r'^FQBN="([^"]+)"', f.read(), re.M)
        return m.group(1) if m else None
    except OSError:
        return None


def version_firmware(proyecto):
    """'v13' del banner de arranque del .ino, o '' si no se encuentra."""
    try:
        with open(os.path.join(dir_sketch(proyecto), 'pantalla_p4_101.ino'), encoding='utf-8') as f:
            m = re.search(r'pantalla_p4_101 (v\d+)', f.read())
        return m.group(1) if m else ''
    except OSError:
        return ''


def buscar_arduino_cli():
    """Ruta de arduino-cli, o None.

    run.bat no hereda el PATH de Git Bash (~/bin), asi que ademas del PATH se
    miran los sitios donde se instala en Windows.
    """
    propio = os.environ.get('ARDUINO_CLI')
    if propio and os.path.isfile(propio):
        return propio
    en_path = shutil.which('arduino-cli')
    if en_path:
        return en_path
    casa = os.path.expanduser('~')
    candidatos = [
        os.path.join(casa, 'bin', 'arduino-cli.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'arduino-cli', 'arduino-cli.exe'),
        r'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe',
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Arduino IDE', 'resources',
                     'app', 'lib', 'backend', 'resources', 'arduino-cli.exe'),
    ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    return None


# ---------------------------------------------------------------- ejecucion

def _ejecutar(comando, timeout, al_linea):
    """Lanza un comando volcando cada linea de salida. -> (codigo, agotado).

    Es el unico punto que arranca procesos: los tests lo sustituyen.
    """
    proc = subprocess.Popen(
        comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace', creationflags=_SIN_VENTANA)
    agotado = {'si': False}

    def matar():
        agotado['si'] = True
        proc.kill()

    reloj = threading.Timer(timeout, matar)
    reloj.start()
    try:
        for linea in proc.stdout:
            al_linea(linea.rstrip())
        codigo = proc.wait()
    finally:
        reloj.cancel()
    return codigo, agotado['si']


def estado():
    with _lock:
        e = dict(_estado)
        e['log'] = list(_estado.get('log') or [])
    if e.get('inicio') and e['fase'] in ('compilando', 'subiendo'):
        e['segundos'] = int(time.time() - e['inicio'])
    return e


def ocupado():
    with _lock:
        return _estado['fase'] in ('compilando', 'subiendo')


def _poner(**cambios):
    with _lock:
        _estado.update(cambios)


def _apuntar(linea):
    if not linea:
        return
    with _lock:
        _estado['log'].append(linea)


def _consejo_subida(log):
    texto = '\n'.join(log).lower()
    if 'could not open port' in texto or 'access is denied' in texto or 'acceso denegado' in texto \
            or 'permissionerror' in texto:
        return ('El puerto está cogido por otro programa. Cierra el monitor serie, el Arduino IDE '
                'o cualquier otra ventana que lo use y vuelve a intentarlo.')
    if 'no serial data' in texto or 'failed to connect' in texto or 'timed out waiting' in texto:
        return ('La placa no contesta. Desconecta los cables UART del carro, prueba otro cable USB '
                '(que sea de datos) y, si sigue igual, mantén pulsado BOOT, pulsa y suelta RESET, '
                'suelta BOOT y vuelve a grabar.')
    return 'Revisa el registro de abajo. Comprueba el puerto y que la placa sigue enchufada.'


def _trabajo(cli, proyecto, data_dir, puerto, variante, solo_compilar):
    flags = VARIANTES[variante]['flags']
    placa = fqbn(proyecto)
    build = os.path.join(data_dir, 'p4_build', variante)
    sketch = dir_sketch(proyecto)
    try:
        os.makedirs(build, exist_ok=True)
        _poner(fase='compilando', mensaje='Compilando el firmware...')
        cmd = [cli, 'compile', '--fqbn', placa, '--build-path', build]
        if flags:
            cmd += ['--build-property', f'compiler.cpp.extra_flags={flags}']
        codigo, agotado = _ejecutar(cmd + [sketch], TIMEOUT_COMPILAR_S, _apuntar)
        if agotado or codigo != 0:
            _poner(fase='error', fin=time.time(),
                   mensaje=('La compilación ha tardado demasiado y se ha cortado.' if agotado else
                            'No compila: no se ha tocado la pantalla. El error está en el registro.'))
            return
        if solo_compilar:
            _poner(fase='ok', fin=time.time(), mensaje='Compila bien. No se ha grabado ninguna pantalla.')
            return

        _poner(fase='subiendo', mensaje=f'Grabando la pantalla por {puerto}... (no la desenchufes)')
        cmd = [cli, 'upload', '-p', puerto, '--fqbn', placa, '--input-dir', build, sketch]
        codigo, agotado = _ejecutar(cmd, TIMEOUT_SUBIR_S, _apuntar)
        if agotado or codigo != 0:
            with _lock:
                log = list(_estado['log'])
            _poner(fase='error', fin=time.time(),
                   mensaje='No se ha podido grabar la pantalla.', consejo=_consejo_subida(log))
            return
        _poner(fase='ok', fin=time.time(),
               mensaje=(f'Pantalla grabada ({version_firmware(proyecto) or "firmware"}, '
                        f'{VARIANTES[variante]["nombre"].lower()}). Vuelve a conectar los cables '
                        'UART del carro: en unos segundos le reenvía los datos.'))
    except FileNotFoundError:
        _poner(fase='error', fin=time.time(), mensaje='No se encuentra arduino-cli en este PC.')
    except Exception as e:   # el hilo no puede morir callado: el navegador esperaria para siempre
        _poner(fase='error', fin=time.time(), mensaje=f'Error inesperado: {e}')


def lanzar(proyecto, data_dir, puerto, variante, solo_compilar=False):
    """Arranca la compilacion (y la subida) en un hilo. -> (ok, mensaje)."""
    global _hilo
    cli = buscar_arduino_cli()
    if not cli:
        return False, ('En este PC no está instalado arduino-cli, así que no se puede compilar la '
                       'pantalla grande. Solo se puede desde el PC de fábrica.')
    if not fqbn(proyecto):
        return False, 'No se encuentra la configuración de la placa (FQBN en compilar.sh).'
    with _lock:
        if _estado['fase'] in ('compilando', 'subiendo'):
            return False, 'Ya hay una grabación en marcha. Espera a que termine.'
        _estado.clear()
        _estado.update(fase='compilando', inicio=time.time(), puerto=puerto, variante=variante,
                       solo_compilar=solo_compilar, mensaje='Empezando...',
                       log=deque(maxlen=LINEAS_LOG))
    _hilo = threading.Thread(target=_trabajo, name='grabar-p4', daemon=True,
                             args=(cli, proyecto, data_dir, puerto, variante, solo_compilar))
    _hilo.start()
    return True, 'Empezado'
