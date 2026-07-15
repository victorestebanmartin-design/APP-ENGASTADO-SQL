"""
config_manager.py
-----------------
Exportación e importación de la BD completa como archivo .db dentro de un ZIP.

Filosofía: copia directa del archivo SQLite — sin JSON, sin tablas, sin FK.
Lo que ves en una instalación es exactamente lo que llega a la otra.
"""
import os
import sqlite3
import zipfile as _zipfile
import io
import tempfile
from datetime import datetime
from sqlalchemy import text

DATA_DIR_NAME = 'data'
DB_FILE_NAME  = 'engastado.db'


class ConfigManager:

    def __init__(self, db, base_dir):
        """
        Args:
            db:       SQLAlchemy database instance
            base_dir: directorio raíz del proyecto (donde está la carpeta data/)
        """
        self.db       = db
        self.base_dir = base_dir
        self.data_dir = os.path.join(base_dir, DATA_DIR_NAME)
        self.db_path  = os.path.join(self.data_dir, DB_FILE_NAME)

    # ------------------------------------------------------------------
    #  EXPORTAR — descarga el archivo .db como ZIP
    # ------------------------------------------------------------------

    def exportar_db(self):
        """
        Exporta la BD completa como ZIP que contiene 'engastado.db'.

        Hace un WAL checkpoint antes de exportar para asegurar que
        todos los datos pendientes están escritos en el archivo principal.

        Returns:
            (bytes, str): (contenido ZIP, nombre_archivo sugerido)
        """
        # Vaciar el WAL al archivo principal antes de leer el fichero
        try:
            with self.db.engine.connect() as conn:
                conn.execute(text("PRAGMA wal_checkpoint(FULL)"))
                conn.commit()
        except Exception:
            pass

        # Copiar la BD a un archivo temporal usando sqlite3.backup()
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            tmp_path = tmp.name

        src_con = sqlite3.connect(self.db_path)
        tmp_con = sqlite3.connect(tmp_path)
        src_con.backup(tmp_con)
        tmp_con.close()
        src_con.close()

        with open(tmp_path, 'rb') as f:
            db_bytes = f.read()
        os.unlink(tmp_path)

        # Empaquetar en ZIP
        zip_buf = io.BytesIO()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        with _zipfile.ZipFile(zip_buf, 'w', _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(DB_FILE_NAME, db_bytes)
            zf.writestr('info.txt',
                        f"Exportado: {datetime.now().isoformat()}\n"
                        f"Archivo:   {DB_FILE_NAME}\n"
                        f"Tamaño DB: {len(db_bytes)} bytes\n")
        zip_buf.seek(0)

        nombre = f"engastado_db_{ts}.zip"
        return zip_buf.getvalue(), nombre

    # ------------------------------------------------------------------
    #  IMPORTAR — sube un ZIP con engastado.db y reemplaza la BD local
    # ------------------------------------------------------------------

    def importar_db(self, contenido_zip):
        """
        Reemplaza la BD actual con la contenida en el ZIP.

        Args:
            contenido_zip (bytes): Contenido del archivo ZIP subido

        Returns:
            dict: {'éxito': bool, 'mensaje': str, 'tablas': dict}
        """
        try:
            zip_buf = io.BytesIO(contenido_zip)

            # Extraer el .db del ZIP
            with _zipfile.ZipFile(zip_buf, 'r') as zf:
                db_files = [n for n in zf.namelist() if n.endswith('.db')]
                if not db_files:
                    return {'éxito': False, 'mensaje': 'El ZIP no contiene ningún archivo .db'}
                db_bytes = zf.read(db_files[0])

            # Guardar en un archivo temporal
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                tmp.write(db_bytes)
                tmp_path = tmp.name

            # Verificar que es una BD SQLite válida
            try:
                test_con = sqlite3.connect(tmp_path)
                tablas = test_con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                conteos = {}
                for (t,) in tablas:
                    try:
                        n = test_con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                        conteos[t] = n
                    except Exception:
                        conteos[t] = '?'
                test_con.close()
            except Exception as e:
                os.unlink(tmp_path)
                return {'éxito': False, 'mensaje': f'El archivo .db es inválido o está corrupto: {e}'}

            # Cerrar el pool de SQLAlchemy para liberar handles
            self.db.engine.dispose()

            # Borrar WAL/SHM si existen
            for ext in ['-wal', '-shm']:
                f = self.db_path + ext
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            # Restaurar: copiar src → dst con sqlite3.backup()
            src_con = sqlite3.connect(tmp_path)
            dst_con = sqlite3.connect(self.db_path)
            src_con.backup(dst_con)
            dst_con.close()
            src_con.close()
            os.unlink(tmp_path)

            # Forzar reconexión del pool
            self.db.engine.dispose()

            return {
                'éxito':   True,
                'mensaje': f'BD restaurada correctamente ({len(conteos)} tablas)',
                'tablas':  conteos,
            }

        except Exception as e:
            return {'éxito': False, 'mensaje': f'Error inesperado: {e}'}

    # ------------------------------------------------------------------
    #  BACKUPS LOCALES — listar y restaurar desde data/
    # ------------------------------------------------------------------

    def listar_backups(self):
        """
        Lista los archivos de backup disponibles en data/.

        Returns:
            list[dict]: [{nombre, fecha_str, tamaño_kb}, ...]  ordenados desc
        """
        resultado = []
        if not os.path.isdir(self.data_dir):
            return resultado

        for nombre in os.listdir(self.data_dir):
            if 'backup' not in nombre.lower() or not nombre.startswith('engastado'):
                continue
            ruta = os.path.join(self.data_dir, nombre)
            if not os.path.isfile(ruta):
                continue
            try:
                stat = os.stat(ruta)
                resultado.append({
                    'nombre':    nombre,
                    'fecha_ts':  stat.st_mtime,
                    'fecha_str': datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M'),
                    'tamano_kb': round(stat.st_size / 1024, 1),
                })
            except Exception:
                pass

        resultado.sort(key=lambda x: x['fecha_ts'], reverse=True)
        return resultado

    def restaurar_backup(self, nombre_backup):
        """
        Restaura la BD desde un archivo de backup local en data/.

        Args:
            nombre_backup (str): Nombre del archivo (solo nombre, sin ruta)

        Returns:
            dict: {'éxito': bool, 'mensaje': str}
        """
        nombre_limpio = os.path.basename(nombre_backup)
        if not nombre_limpio.startswith('engastado') or 'backup' not in nombre_limpio:
            return {'éxito': False, 'mensaje': 'Nombre de backup no válido'}

        ruta = os.path.join(self.data_dir, nombre_limpio)
        if not os.path.isfile(ruta):
            return {'éxito': False, 'mensaje': 'Archivo de backup no encontrado'}

        try:
            c = sqlite3.connect(ruta)
            c.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            c.close()
        except Exception as e:
            return {'éxito': False, 'mensaje': f'Backup corrupto: {e}'}

        self.db.engine.dispose()
        for ext in ['-wal', '-shm']:
            f = self.db_path + ext
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

        src_con = sqlite3.connect(ruta)
        dst_con = sqlite3.connect(self.db_path)
        src_con.backup(dst_con)
        dst_con.close()
        src_con.close()
        self.db.engine.dispose()

        return {'éxito': True, 'mensaje': f'Restaurado desde {nombre_limpio}'}
