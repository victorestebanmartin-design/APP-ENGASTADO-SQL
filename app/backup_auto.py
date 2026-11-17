"""Copia de seguridad automática, periódica y sin intervención.

Con ~18 placas y 10 PCs esto ya es crítico: hasta ahora el único respaldo era
el manual desde Admin → Sistema, que nadie se acuerda de pulsar. Este módulo
lanza un hilo de fondo que cada ``AUTO_BACKUP_HORAS`` (6 por defecto):

* copia ``data/engastado.db`` con la API de backup online de SQLite (segura
  con la base en uso, WAL incluido) y la **verifica** (``integrity_check``);
* copia los JSON de estado vivo de ``data/`` (latidos, pick-to-light...);
* copia el avance de cada bono (``progreso_bono_*.json``, que es además el
  report de trazabilidad), los Excel de ``data/cortes``, los PDF de las
  máquinas y los datos de manguitos: nada de eso vive en la base de datos, y
  sin ello una copia no devuelve la planta a como estaba. De esas carpetas
  solo se copia lo que ha cambiado desde la copia anterior; el resto se
  enlaza al fichero que ya había en ella (ver ``_copiar_carpeta``);
* deja todo en ``data/backups_auto/backup_AAAAmmdd_HHMMSS/`` y conserva solo
  los últimos ``AUTO_BACKUP_RETENER`` (20).

**Disco externo.** Una copia en el mismo disco que el servidor no sirve el
día que se estropea ese disco. Si en Admin → Sistema se indica una carpeta de
otro disco (o en el ``.env``, ``AUTO_BACKUP_DESTINO``), cada ronda hace además
otra copia completa allí. La del servidor se sigue haciendo siempre: si el
disco externo no está enchufado, o falla a mitad, se apunta el aviso y la
planta sigue teniendo su copia local. La carpeta no se crea sola: si no
existe es que el disco no está (o le han cambiado la letra), y crearla
repartiría las copias por otro disco sin que nadie lo sepa.

Cómo fue la última ronda queda en ``data/backup_auto_estado.json`` y se ve
en Admin → Sistema (``resumen_estado``).

Se arranca desde ``run_sql.py`` (el proceso local de planta), NO desde
``create_app``: así no corre en los tests ni en el ``wsgi.py`` de pruebas.
Todo es best-effort y con ``try`` de sobra: un fallo aquí nunca puede tumbar
el servidor.
"""
import os
import shutil
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta

from app.estado_json import cargar as _json_cargar, guardar as _json_guardar

CARPETA_LOCAL = 'backups_auto'
FICHERO_CONFIG = 'backup_auto.json'
FICHERO_ESTADO = 'backup_auto_estado.json'

# Una copia que no se renueva en este tiempo se avisa en Admin aunque la
# última saliera bien: o el hilo no está corriendo, o el servidor ha estado
# apagado. Nunca menos de un día, para no avisar de noche con copias cada 6 h.
_AVISO_SIN_COPIA_MIN_H = 24

# Mismos ficheros que ignora .gitignore como "estado vivo": se respaldan porque
# reconstruirlos requiere que las placas vuelvan a sondear, y un pick-to-light
# a medias tras un corte es molesto.
_JSON_ESTADO = (
    'esp32_devices.json', 'esp32_rfid_devices.json', 'esp32_eventos.json',
    'esp32_confirmaciones.json', 'esp32_tags.json', 'pcs_vistos.json',
    'rfid_entrada_estado.json', 'pick_to_light_estado.json',
    'pick_to_light_test.json', 'pick_to_light_rfid_armado.json',
    'pick_to_light_correspondencia.json', 'servidor_backend.json',
    'wifi_hotspot.json', 'grupos_etiquetas.json', FICHERO_CONFIG,
)

# Carpetas de data/ que se copian enteras: (subcarpeta, extensiones o None).
_CARPETAS = (
    ('cortes', ('.xlsx', '.xls')),
    ('maquinas_pdf', None),
    ('manguitos', None),
)

# Una sola ronda a la vez: la del hilo y la del botón «Hacer copia ahora» no
# pueden pisarse escribiendo en la misma carpeta.
_RONDA = threading.Lock()


# ── Configuración del disco externo ─────────────────────────────────────────

def _config_file(data_dir):
    return os.path.join(data_dir, FICHERO_CONFIG)


def destino_externo(app):
    """Carpeta del disco externo configurada, o '' si no hay.

    ``AUTO_BACKUP_DESTINO`` del .env manda sobre lo guardado desde Admin."""
    env = str(app.config.get('AUTO_BACKUP_DESTINO') or '').strip()
    if env:
        return env
    datos = _json_cargar(_config_file(app.config['DATA_DIR']), {})
    return str(datos.get('destino') or '').strip()


def destino_fijado_por_env(app):
    return bool(str(app.config.get('AUTO_BACKUP_DESTINO') or '').strip())


def _mismo_disco(a, b):
    """True si las dos rutas están en la misma unidad de Windows (C:, D:...).

    En Linux no hay letras de unidad y no se puede saber así: se da por bueno."""
    unidad_a = os.path.splitdrive(os.path.abspath(a))[0].lower()
    unidad_b = os.path.splitdrive(os.path.abspath(b))[0].lower()
    return bool(unidad_a) and unidad_a == unidad_b


def error_destino(ruta, data_dir):
    """Motivo por el que esa carpeta no vale como disco externo, o None."""
    if not os.path.isabs(ruta):
        return 'Escribe la ruta completa de la carpeta, por ejemplo E:\\CopiasCOJOsw'
    if not os.path.isdir(ruta):
        return ('Esa carpeta no existe. Comprueba que el disco está enchufado y crea la '
                'carpeta en él antes de indicarla aquí.')
    if _mismo_disco(ruta, data_dir):
        return ('Esa carpeta está en el mismo disco que el servidor: si ese disco se '
                'estropea se pierden las dos copias. Elige una carpeta del disco externo.')
    prueba = os.path.join(ruta, '.cojosw_prueba_escritura')
    try:
        with open(prueba, 'w', encoding='utf-8') as f:
            f.write('ok')
        os.remove(prueba)
    except OSError as e:
        return f'No se puede escribir en esa carpeta ({e.strerror or e}). Revisa los permisos con IT.'
    return None


def guardar_destino(app, ruta):
    """Guarda (o quita, con '') la carpeta del disco externo."""
    _json_guardar(_config_file(app.config['DATA_DIR']), {'destino': ruta})


# ── Una copia ───────────────────────────────────────────────────────────────

def _copia_anterior(destino_base, destino):
    """Carpeta de la copia inmediatamente anterior a ``destino``, o None."""
    actual = os.path.basename(destino)
    try:
        previas = sorted(
            d for d in os.listdir(destino_base)
            if d.startswith('backup_') and d < actual
            and os.path.isdir(os.path.join(destino_base, d))
        )
    except OSError:
        return None
    return os.path.join(destino_base, previas[-1]) if previas else None


def _sin_cambios(origen, copia):
    """True si ``copia`` es el mismo fichero que ``origen``: mismo tamaño y misma
    fecha de modificación (copy2 la conserva; se dejan 2 s de margen porque no
    todos los discos la guardan con la misma precisión)."""
    try:
        a, b = os.stat(origen), os.stat(copia)
    except OSError:
        return False
    return a.st_size == b.st_size and abs(a.st_mtime - b.st_mtime) < 2


def _copiar_carpeta(origen_dir, destino, anterior, subcarpeta, logger, extensiones=None):
    """Deja en ``destino/subcarpeta`` todos los ficheros de ``origen_dir``,
    copiando solo los que han cambiado desde la copia anterior. Devuelve la
    lista de los que no se pudieron copiar.

    Los Excel y los PDF casi nunca cambian y hay 20 copias: copiarlos todos
    cada 6 h multiplicaba por 20 lo que ocupan. El que no ha cambiado se
    enlaza (enlace duro) al que ya está en la copia anterior: no ocupa sitio
    otra vez, y cada carpeta de copia sigue teniendo dentro todos sus
    ficheros, así que restaurar es igual que antes y purgar una copia vieja
    no rompe las siguientes. Se enlaza contra la copia, nunca contra el
    fichero vivo de data/, que puede reescribirse.

    Si el disco no admite enlaces (FAT, algunas unidades de red), se copia.
    """
    try:
        nombres = sorted(
            n for n in os.listdir(origen_dir)
            if os.path.isfile(os.path.join(origen_dir, n))
            and (extensiones is None or n.lower().endswith(extensiones))
        )
    except OSError:
        return []
    if not nombres:
        return []
    destino_sub = os.path.join(destino, subcarpeta)
    os.makedirs(destino_sub, exist_ok=True)
    copiados = enlazados = 0
    fallos = []
    for nombre in nombres:
        origen = os.path.join(origen_dir, nombre)
        nuevo = os.path.join(destino_sub, nombre)
        previo = os.path.join(anterior, subcarpeta, nombre) if anterior else None
        if previo and _sin_cambios(origen, previo):
            try:
                os.link(previo, nuevo)
                enlazados += 1
                continue
            except OSError:
                pass  # sin enlaces en este disco: se copia como siempre
        try:
            shutil.copy2(origen, nuevo)
            copiados += 1
        except OSError:
            fallos.append(f'{subcarpeta}/{nombre}')
    logger.info('Backup automatico: %s, %d copiados, %d sin cambios',
                subcarpeta, copiados, enlazados)
    return fallos


def _copiar_excels(cortes, destino, anterior, logger):
    """Los Excel de corte (ver ``_copiar_carpeta``)."""
    return _copiar_carpeta(cortes, destino, anterior, 'cortes', logger, ('.xlsx', '.xls'))


def _verificar_db(ruta):
    """None si la base de datos copiada está sana, o el motivo si no."""
    try:
        with closing(sqlite3.connect(f'file:{ruta}?mode=ro', uri=True)) as conn:
            resultado = conn.execute('PRAGMA integrity_check').fetchall()
    except sqlite3.Error as e:
        return f'no se puede abrir la base de datos copiada: {e}'
    if resultado != [('ok',)]:
        return 'la base de datos copiada no supera la comprobación de integridad'
    return None


def _una_copia(data_dir, logger, destino_base=None):
    """Hace una copia completa en ``destino_base`` (por defecto, la carpeta
    local de data/). Devuelve ``(destino_base, carpeta, problemas)``: la
    copia está bien si ``problemas`` está vacía."""
    destino_base = destino_base or os.path.join(data_dir, CARPETA_LOCAL)
    os.makedirs(destino_base, exist_ok=True)
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(destino_base, 'backup_' + sello)
    os.makedirs(destino, exist_ok=True)
    problemas = []

    db_path = os.path.join(data_dir, 'engastado.db')
    if os.path.exists(db_path):
        copia_db = os.path.join(destino, 'engastado.db')
        # sqlite3.backup(): copia consistente aunque el servidor esté escribiendo.
        with closing(sqlite3.connect(db_path)) as src, closing(sqlite3.connect(copia_db)) as dst:
            src.backup(dst)
        motivo = _verificar_db(copia_db)
        if motivo:
            problemas.append(motivo)

    try:
        progresos = [n for n in os.listdir(data_dir)
                     if n.startswith('progreso_bono_') and n.endswith('.json')]
    except OSError:
        progresos = []
    for nombre in list(_JSON_ESTADO) + progresos:
        ruta = os.path.join(data_dir, nombre)
        if os.path.isfile(ruta):
            try:
                shutil.copy2(ruta, os.path.join(destino, nombre))
            except OSError:
                problemas.append(f'no se pudo copiar {nombre}')

    anterior = _copia_anterior(destino_base, destino)
    for subcarpeta, extensiones in _CARPETAS:
        fallos = _copiar_carpeta(os.path.join(data_dir, subcarpeta), destino, anterior,
                                 subcarpeta, logger, extensiones)
        if fallos:
            problemas.append(f'no se pudieron copiar {len(fallos)} ficheros de {subcarpeta}')

    if problemas:
        logger.warning('Backup automatico -> %s CON PROBLEMAS: %s', destino, '; '.join(problemas))
    else:
        logger.info('Backup automatico -> %s (verificada)', destino)
    return destino_base, destino, problemas


def _podar(destino_base, retener, logger):
    try:
        carpetas = sorted(
            d for d in os.listdir(destino_base)
            if d.startswith('backup_') and os.path.isdir(os.path.join(destino_base, d))
        )
    except OSError:
        return
    for vieja in carpetas[:-retener] if retener > 0 else []:
        try:
            shutil.rmtree(os.path.join(destino_base, vieja))
            logger.info('Backup automatico: purgado %s', vieja)
        except OSError:
            pass


# ── Una ronda: servidor + disco externo, y su estado ────────────────────────

def _ahora():
    return datetime.now().isoformat(timespec='seconds')


def _retener(app):
    try:
        return int(app.config.get('AUTO_BACKUP_RETENER', 20) or 20)
    except (TypeError, ValueError):
        return 20


def _copiar_en(app, destino_base):
    """Una copia en ``destino_base`` y su resultado para el estado."""
    data_dir, logger = app.config['DATA_DIR'], app.logger
    try:
        base, carpeta, problemas = _una_copia(data_dir, logger, destino_base)
        _podar(base, _retener(app), logger)
    except Exception as e:
        logger.exception('Backup automatico: fallo copiando en %s', destino_base)
        return {'fecha': _ahora(), 'ok': False, 'carpeta': None,
                'detalle': f'La copia ha fallado: {e}'}
    return {'fecha': _ahora(), 'ok': not problemas, 'carpeta': carpeta,
            'detalle': '; '.join(problemas) if problemas else 'Copia completa y verificada'}


def hacer_ronda(app):
    """Copia en el servidor y, si está configurado, en el disco externo.

    Devuelve el estado guardado, o None si ya había una ronda en marcha."""
    if not _RONDA.acquire(blocking=False):
        return None
    try:
        data_dir = app.config['DATA_DIR']
        ruta_estado = os.path.join(data_dir, FICHERO_ESTADO)
        estado = _json_cargar(ruta_estado, {})

        previo_local = estado.get('local') or {}
        local = _copiar_en(app, os.path.join(data_dir, CARPETA_LOCAL))
        local['ultima_ok'] = local['fecha'] if local['ok'] else previo_local.get('ultima_ok')
        estado['local'] = local

        externo = destino_externo(app)
        if not externo:
            estado.pop('externo', None)
        elif not os.path.isdir(externo):
            # El disco no está (o ha cambiado de letra): se avisa y se guarda
            # cuándo fue la última copia buena allí, que es lo que importa.
            previo = estado.get('externo') or {}
            estado['externo'] = {
                'fecha': _ahora(), 'ok': False, 'carpeta': None,
                'detalle': f'No se encuentra {externo}: ¿está enchufado el disco externo?',
                'ultima_ok': previo.get('ultima_ok'),
            }
            app.logger.warning('Backup automatico: disco externo no disponible (%s)', externo)
        else:
            previo = estado.get('externo') or {}
            resultado = _copiar_en(app, externo)
            resultado['ultima_ok'] = resultado['fecha'] if resultado['ok'] else previo.get('ultima_ok')
            estado['externo'] = resultado

        _json_guardar(ruta_estado, estado)
        return estado
    finally:
        _RONDA.release()


def _intervalo_horas(app):
    try:
        return float(app.config.get('AUTO_BACKUP_HORAS', 6) or 6)
    except (TypeError, ValueError):
        return 6.0


def _vieja(fecha_iso, limite_h, ahora):
    if not fecha_iso:
        return True
    try:
        return ahora - datetime.fromisoformat(fecha_iso) > timedelta(hours=limite_h)
    except ValueError:
        return True


def resumen_estado(app, ahora=None):
    """Lo que enseña Admin → Sistema: cómo fue la última ronda y los avisos."""
    ahora = ahora or datetime.now()
    estado = _json_cargar(os.path.join(app.config['DATA_DIR'], FICHERO_ESTADO), {})
    desactivada = str(app.config.get('AUTO_BACKUP_HORAS', 6)) == '0'
    horas = _intervalo_horas(app)
    limite = max(_AVISO_SIN_COPIA_MIN_H, 2 * horas)
    externo = destino_externo(app)
    avisos = []

    local = estado.get('local')
    if desactivada:
        avisos.append('La copia automática está desactivada (AUTO_BACKUP_HORAS=0).')
    elif not local:
        avisos.append('Todavía no se ha hecho ninguna copia automática. La primera sale a '
                      'los 2 minutos de arrancar el servidor, o pulsa «Hacer copia ahora».')
    else:
        if not local.get('ok'):
            avisos.append(f'La última copia en el servidor tuvo problemas: {local.get("detalle")}')
        if _vieja(local.get('ultima_ok'), limite, ahora):
            avisos.append(f'No hay una copia buena en el servidor desde hace más de {int(limite)} h.')

    ext = estado.get('externo') if externo else None
    if externo and not desactivada:
        if not ext:
            avisos.append('Aún no se ha copiado en el disco externo: pulsa «Hacer copia ahora» '
                          'para probarlo.')
        else:
            if not ext.get('ok'):
                avisos.append(ext.get('detalle') or 'La última copia en el disco externo falló.')
            if _vieja(ext.get('ultima_ok'), limite, ahora):
                avisos.append(f'No hay una copia buena en el disco externo desde hace más de '
                              f'{int(limite)} h.')
    elif not desactivada:
        avisos.append('Las copias solo están en el disco del servidor: si ese disco se estropea '
                      'se pierden con él. Indica una carpeta de un disco externo.')

    return {
        'activa': not desactivada,
        'cada_horas': horas,
        'retiene': _retener(app),
        'local': local,
        'externo': ext,
        'destino_externo': externo,
        'destino_por_env': destino_fijado_por_env(app),
        'avisos': avisos,
    }


def _bucle(app):
    logger = app.logger
    horas = _intervalo_horas(app)
    if horas <= 0:
        logger.warning('AUTO_BACKUP_HORAS no es valido: se usan 6 h')
        horas = 6.0
    intervalo_s = max(600, int(horas * 3600))

    # Primera copia a los 2 min de arrancar (deja que el servidor se asiente).
    time.sleep(120)
    while True:
        try:
            if hacer_ronda(app) is None:
                logger.info('Backup automatico: ya habia una copia en marcha, se salta esta ronda')
        except Exception:
            logger.exception('Backup automatico: fallo en esta ronda (se reintenta)')
        time.sleep(intervalo_s)


def arrancar(app):
    """Lanza el hilo de backup (daemon). Se llama una vez, desde run_sql.py."""
    if str(app.config.get('AUTO_BACKUP_HORAS', 6)) == '0':
        app.logger.info('Backup automatico DESACTIVADO (AUTO_BACKUP_HORAS=0)')
        return
    hilo = threading.Thread(target=_bucle, args=(app,), name='backup-auto', daemon=True)
    hilo.start()
    app.logger.info('Backup automatico cada %s h (retiene %s)%s',
                    app.config.get('AUTO_BACKUP_HORAS', 6),
                    app.config.get('AUTO_BACKUP_RETENER', 20),
                    f', tambien en {destino_externo(app)}' if destino_externo(app) else '')
