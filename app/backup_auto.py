"""Copia de seguridad automática, periódica y sin intervención.

Con ~18 placas y 10 PCs esto ya es crítico: hasta ahora el único respaldo era
el manual desde Admin → Sistema, que nadie se acuerda de pulsar. Este módulo
lanza un hilo de fondo que cada ``AUTO_BACKUP_HORAS`` (6 por defecto):

* copia ``data/engastado.db`` con la API de backup online de SQLite (segura
  con la base en uso, WAL incluido);
* copia los JSON de estado vivo de ``data/`` (latidos, pick-to-light...);
* deja todo en ``data/backups_auto/backup_AAAAmmdd_HHMMSS/`` y conserva solo
  los últimos ``AUTO_BACKUP_RETENER`` (20).

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
from datetime import datetime

# Mismos ficheros que ignora .gitignore como "estado vivo": se respaldan porque
# reconstruirlos requiere que las placas vuelvan a sondear, y un pick-to-light
# a medias tras un corte es molesto.
_JSON_ESTADO = (
    'esp32_devices.json', 'esp32_rfid_devices.json', 'esp32_eventos.json',
    'esp32_confirmaciones.json', 'esp32_tags.json', 'pcs_vistos.json',
    'rfid_entrada_estado.json', 'pick_to_light_estado.json',
    'pick_to_light_test.json', 'pick_to_light_rfid_armado.json',
    'pick_to_light_correspondencia.json', 'servidor_backend.json',
    'wifi_hotspot.json', 'grupos_etiquetas.json',
)


def _una_copia(data_dir, logger):
    destino_base = os.path.join(data_dir, 'backups_auto')
    os.makedirs(destino_base, exist_ok=True)
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(destino_base, 'backup_' + sello)
    os.makedirs(destino, exist_ok=True)

    db_path = os.path.join(data_dir, 'engastado.db')
    if os.path.exists(db_path):
        # sqlite3.backup(): copia consistente aunque el servidor esté escribiendo.
        with closing(sqlite3.connect(db_path)) as src, \
                closing(sqlite3.connect(os.path.join(destino, 'engastado.db'))) as dst:
            src.backup(dst)

    for nombre in _JSON_ESTADO:
        ruta = os.path.join(data_dir, nombre)
        if os.path.exists(ruta):
            try:
                shutil.copy2(ruta, os.path.join(destino, nombre))
            except OSError:
                pass

    logger.info('Backup automatico -> %s', destino)
    return destino_base


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


def _bucle(app):
    logger = app.logger
    data_dir = app.config['DATA_DIR']
    horas = float(app.config.get('AUTO_BACKUP_HORAS', 6) or 6)
    retener = int(app.config.get('AUTO_BACKUP_RETENER', 20) or 20)
    intervalo_s = max(600, int(horas * 3600))

    # Primera copia a los 2 min de arrancar (deja que el servidor se asiente).
    time.sleep(120)
    while True:
        try:
            base = _una_copia(data_dir, logger)
            _podar(base, retener, logger)
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
    app.logger.info('Backup automatico cada %s h (retiene %s)',
                    app.config.get('AUTO_BACKUP_HORAS', 6),
                    app.config.get('AUTO_BACKUP_RETENER', 20))
