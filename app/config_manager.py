"""
config_manager.py
-----------------
Exportación e importación de la BD completa como archivo .db dentro de un ZIP.

Dos modos:
  - Solo BD:    ZIP con engastado.db
  - Completo:   ZIP con engastado.db + todos los Excel de data/cortes/
"""
import os
import sqlite3
import zipfile as _zipfile
import io
import tempfile
from datetime import datetime
from sqlalchemy import text

DATA_DIR_NAME   = 'data'
DB_FILE_NAME    = 'engastado.db'
CORTES_DIR_NAME = 'cortes'          # subcarpeta dentro de data/
EXCEL_EXTS      = ('.xlsx', '.xls') # extensiones de Excel a incluir


class ConfigManager:

    def __init__(self, db, base_dir):
        self.db         = db
        self.base_dir   = base_dir
        self.data_dir   = os.path.join(base_dir, DATA_DIR_NAME)
        self.db_path    = os.path.join(self.data_dir, DB_FILE_NAME)
        self.cortes_dir = os.path.join(self.data_dir, CORTES_DIR_NAME)

    # ------------------------------------------------------------------
    #  INTERNAL — copia la BD activa a bytes vía sqlite3.backup()
    # ------------------------------------------------------------------

    def _db_a_bytes(self):
        """Devuelve el contenido del archivo .db como bytes usando sqlite3.backup()."""
        try:
            with self.db.engine.connect() as conn:
                conn.execute(text("PRAGMA wal_checkpoint(FULL)"))
                conn.commit()
        except Exception:
            pass

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            tmp_path = tmp.name

        src = sqlite3.connect(self.db_path)
        dst = sqlite3.connect(tmp_path)
        src.backup(dst)
        dst.close()
        src.close()

        with open(tmp_path, 'rb') as f:
            data = f.read()
        os.unlink(tmp_path)
        return data

    # ------------------------------------------------------------------
    #  EXPORTAR SOLO BD
    # ------------------------------------------------------------------

    def exportar_db(self):
        """
        ZIP con engastado.db únicamente.
        Returns: (bytes, nombre_archivo)
        """
        db_bytes = self._db_a_bytes()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        zip_buf = io.BytesIO()
        with _zipfile.ZipFile(zip_buf, 'w', _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(DB_FILE_NAME, db_bytes)
            zf.writestr('info.txt',
                        f"Exportado: {datetime.now().isoformat()}\n"
                        f"Tipo: solo BD\n"
                        f"Tamaño DB: {len(db_bytes)} bytes\n")
        zip_buf.seek(0)
        return zip_buf.getvalue(), f"engastado_db_{ts}.zip"

    # ------------------------------------------------------------------
    #  EXPORTAR COMPLETO (BD + Excel)
    # ------------------------------------------------------------------

    def exportar_completo(self):
        """
        ZIP con engastado.db + todos los Excel de data/cortes/.
        Returns: (bytes, nombre_archivo)
        """
        db_bytes = self._db_a_bytes()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        zip_buf = io.BytesIO()
        with _zipfile.ZipFile(zip_buf, 'w', _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(DB_FILE_NAME, db_bytes)

            # Excel de data/cortes/
            excels_añadidos = []
            if os.path.isdir(self.cortes_dir):
                for fname in os.listdir(self.cortes_dir):
                    if fname.lower().endswith(EXCEL_EXTS):
                        fpath = os.path.join(self.cortes_dir, fname)
                        zf.write(fpath, os.path.join('cortes', fname))
                        excels_añadidos.append(fname)

            zf.writestr('info.txt',
                        f"Exportado: {datetime.now().isoformat()}\n"
                        f"Tipo: completo (BD + Excel)\n"
                        f"Tamaño DB: {len(db_bytes)} bytes\n"
                        f"Excels: {len(excels_añadidos)}\n" +
                        ''.join(f"  - {e}\n" for e in excels_añadidos))

        zip_buf.seek(0)
        return zip_buf.getvalue(), f"engastado_completo_{ts}.zip"

    # ------------------------------------------------------------------
    #  IMPORTAR (BD + opcionalmente Excel)
    # ------------------------------------------------------------------

    def importar_db(self, contenido_zip, incluir_excels=True):
        """
        Reemplaza la BD desde un ZIP. Si incluir_excels=True y el ZIP
        contiene la carpeta 'cortes/', también restaura los Excel.

        Returns: {'éxito': bool, 'mensaje': str, 'tablas': dict, 'excels': int}
        """
        try:
            zip_buf = io.BytesIO(contenido_zip)

            with _zipfile.ZipFile(zip_buf, 'r') as zf:
                nombres = zf.namelist()

                # --- BD ---
                db_files = [n for n in nombres if n.endswith('.db') and '/' not in n]
                if not db_files:
                    return {'éxito': False, 'mensaje': 'El ZIP no contiene ningún archivo .db'}
                db_bytes = zf.read(db_files[0])

                # --- Excel (si hay y se piden) ---
                excel_files = [n for n in nombres
                               if n.startswith('cortes/') and n.lower().endswith(EXCEL_EXTS)]
                excels_restaurados = 0

                if incluir_excels and excel_files:
                    os.makedirs(self.cortes_dir, exist_ok=True)
                    for ef in excel_files:
                        fname = os.path.basename(ef)
                        dest  = os.path.join(self.cortes_dir, fname)
                        with open(dest, 'wb') as f:
                            f.write(zf.read(ef))
                        excels_restaurados += 1

            # --- Validar .db ---
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                tmp.write(db_bytes)
                tmp_path = tmp.name

            try:
                tc = sqlite3.connect(tmp_path)
                tablas = tc.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                conteos = {}
                for (t,) in tablas:
                    try:
                        conteos[t] = tc.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    except Exception:
                        conteos[t] = '?'
                tc.close()
            except Exception as e:
                os.unlink(tmp_path)
                return {'éxito': False, 'mensaje': f'Archivo .db inválido: {e}'}

            # --- Restaurar BD ---
            self.db.engine.dispose()
            for ext in ['-wal', '-shm']:
                f = self.db_path + ext
                if os.path.exists(f):
                    try: os.remove(f)
                    except Exception: pass

            src = sqlite3.connect(tmp_path)
            dst = sqlite3.connect(self.db_path)
            src.backup(dst)
            dst.close()
            src.close()
            os.unlink(tmp_path)
            self.db.engine.dispose()

            return {
                'éxito':  True,
                'mensaje': f'BD restaurada ({len(conteos)} tablas)'
                           + (f', {excels_restaurados} Excel restaurados' if excels_restaurados else ''),
                'tablas': conteos,
                'excels': excels_restaurados,
            }

        except Exception as e:
            return {'éxito': False, 'mensaje': f'Error inesperado: {e}'}

    # ------------------------------------------------------------------
    #  BACKUPS LOCALES
    # ------------------------------------------------------------------

    def listar_backups(self):
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
                try: os.remove(f)
                except Exception: pass

        src = sqlite3.connect(ruta)
        dst = sqlite3.connect(self.db_path)
        src.backup(dst)
        dst.close()
        src.close()
        self.db.engine.dispose()
        return {'éxito': True, 'mensaje': f'Restaurado desde {nombre_limpio}'}

