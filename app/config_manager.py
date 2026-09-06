"""
config_manager.py
-----------------
Exportación e importación de la BD completa como archivo .db dentro de un ZIP.

Dos modos:
  - Solo BD:    ZIP con engastado.db
  - Completo:   BD + Excel + avance de bonos + documentos y datos auxiliares
"""
import os
import sqlite3
import zipfile as _zipfile
import io
import tempfile
import json
from pathlib import Path
from contextlib import closing
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

        with tempfile.TemporaryDirectory(prefix='cojosw_export_') as tmp:
            tmp_path = os.path.join(tmp, 'export.db')
            with closing(sqlite3.connect(self.db_path)) as src, closing(sqlite3.connect(tmp_path)) as dst:
                src.backup(dst)
            return Path(tmp_path).read_bytes()

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
        ZIP con BD, Excel, progreso y documentos persistentes.
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
                        zf.write(fpath, 'cortes/' + fname)
                        excels_añadidos.append(fname)

            # Datos persistentes fuera de SQLite; no incluir claves ni canales ESP32.
            archivos = self._archivos_adicionales()
            for nombre in archivos:
                zf.write(os.path.join(self.data_dir, nombre), nombre)
            zf.writestr('manifest.json', json.dumps({
                'version': 1, 'tipo': 'completo',
                'archivos': ['engastado.db'] + ['cortes/' + n for n in excels_añadidos] + archivos,
            }, ensure_ascii=False))

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

    def _archivos_adicionales(self):
        raiz = Path(self.data_dir)
        archivos = [p.name for p in raiz.glob('progreso_bono_*.json') if p.is_file()]
        for nombre in ('grupos_etiquetas.json',):
            if (raiz / nombre).is_file():
                archivos.append(nombre)
        for carpeta in ('maquinas_pdf', 'manguitos'):
            if (raiz / carpeta).is_dir():
                archivos.extend(p.relative_to(raiz).as_posix()
                                for p in (raiz / carpeta).rglob('*') if p.is_file())
        return sorted(archivos)

    @staticmethod
    def _validar_db(ruta):
        with closing(sqlite3.connect(ruta)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('La base de datos no supera la comprobación de integridad')
            tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'bonos', 'ordenes_produccion', 'proyectos', 'carros', 'codigos_cortes'} <= tablas:
                raise ValueError('La base de datos no pertenece a una instalación de COJOsw')
            # Rechazar esquemas incompletos antes de reemplazar una instalación sana.
            schema = Path(__file__).resolve().parent.parent / 'schema_sqlite.sql'
            with closing(sqlite3.connect(':memory:')) as esperado:
                esperado.executescript(schema.read_text(encoding='utf-8'))
                for (tabla,) in esperado.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"):
                    ident = '"' + tabla.replace('"', '""') + '"'
                    requeridas = {r[1] for r in esperado.execute('PRAGMA table_info(' + ident + ')')}
                    disponibles = {r[1] for r in conn.execute('PRAGMA table_info(' + ident + ')')}
                    if not requeridas <= disponibles:
                        raise ValueError('Esquema incompatible: faltan tablas o columnas en ' + tabla)
            if conn.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('La base de datos contiene referencias inconsistentes')
            return {t: conn.execute('SELECT COUNT(*) FROM "' + t.replace('"', '""') + '"').fetchone()[0]
                    for t in tablas}

    def _reemplazar_db(self, ruta):
        # SQLite gestiona WAL: nunca borrar sus ficheros con conexiones abiertas.
        self.db.engine.dispose()
        try:
            with closing(sqlite3.connect(ruta)) as src, closing(sqlite3.connect(self.db_path)) as dst:
                src.backup(dst)
        finally:
            self.db.engine.dispose()

    def importar_db(self, contenido_zip, incluir_excels=True):
        """Valida en staging, respalda y restaura el conjunto con rollback ante errores."""
        respaldo = None
        try:
            with tempfile.TemporaryDirectory(prefix='cojosw_import_') as tmp:
                staging = Path(tmp)
                with _zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
                    nombres = [i.filename for i in zf.infolist() if not i.is_dir()]
                    if len(nombres) != len(set(n.casefold() for n in nombres)):
                        raise ValueError('El ZIP contiene nombres duplicados')
                    for n in nombres:
                        if '\\' in n or ':' in n or n.startswith('/') or any(x in ('', '.', '..') for x in n.split('/')):
                            raise ValueError('El ZIP contiene una ruta no válida')
                    if sum(i.file_size for i in zf.infolist()) > 512 * 1024 * 1024:
                        raise ValueError('El ZIP supera 512 MB descomprimido')
                    dbs = [n for n in nombres if n.endswith('.db') and '/' not in n]
                    if len(dbs) != 1:
                        raise ValueError('El ZIP debe contener exactamente una base de datos')
                    nueva_db = staging / 'nueva.db'
                    nueva_db.write_bytes(zf.read(dbs[0]))
                    conteos = self._validar_db(str(nueva_db))
                    completos = False
                    if 'manifest.json' in nombres:
                        manifest = json.loads(zf.read('manifest.json'))
                        if manifest.get('version') != 1 or manifest.get('tipo') != 'completo':
                            raise ValueError('Versión de copia no compatible')
                        if set(manifest.get('archivos', [])) != set(nombres) - {'manifest.json', 'info.txt'}:
                            raise ValueError('El manifiesto no coincide con los archivos del ZIP')
                        completos = True
                    archivos = {}
                    for n in nombres:
                        excel = n.startswith('cortes/') and n.lower().endswith(EXCEL_EXTS)
                        adicional = (('/' not in n and n.startswith('progreso_bono_') and n.endswith('.json'))
                                     or n == 'grupos_etiquetas.json'
                                     or n.startswith(('maquinas_pdf/', 'manguitos/')))
                        if (excel and incluir_excels) or adicional:
                            contenido = zf.read(n)
                            if n.endswith('.json'):
                                if not isinstance(json.loads(contenido), (dict, list)):
                                    raise ValueError('JSON de datos inválido: ' + n)
                            archivos[n] = contenido
                # Validación completa ANTES de tocar datos locales.
                respaldo_bytes, _ = self.exportar_completo()
                respaldo = 'engastado_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.zip'
                Path(self.data_dir, respaldo).write_bytes(respaldo_bytes)
                anteriores = {}
                afectados = set(archivos)
                # Una copia completa representa también la ausencia de progreso.
                if completos:
                    afectados.update(self._archivos_adicionales())
                for n in afectados:
                    destino = Path(self.data_dir, n)
                    if not destino.resolve().is_relative_to(Path(self.data_dir).resolve()):
                        raise ValueError('Destino fuera del directorio de datos')
                    anteriores[n] = destino.read_bytes() if destino.is_file() else None
                vieja_db = staging / 'anterior.db'
                with _zipfile.ZipFile(io.BytesIO(respaldo_bytes)) as zf:
                    vieja_db.write_bytes(zf.read(DB_FILE_NAME))
                try:
                    for n in afectados:
                        destino = Path(self.data_dir, n)
                        if n in archivos:
                            destino.parent.mkdir(parents=True, exist_ok=True)
                            destino.write_bytes(archivos[n])
                        elif destino.exists():
                            destino.unlink()
                    self._reemplazar_db(str(nueva_db))
                except Exception:
                    for n, contenido in anteriores.items():
                        destino = Path(self.data_dir, n)
                        if contenido is None:
                            destino.unlink(missing_ok=True)
                        else:
                            destino.write_bytes(contenido)
                    self._reemplazar_db(str(vieja_db))
                    raise
                excels = sum(n.startswith('cortes/') for n in archivos)
                aviso = '' if completos else ' Copia antigua o solo BD: no garantiza restaurar el avance.'
                return {'éxito': True, 'mensaje': f'BD restaurada ({len(conteos)} tablas), {excels} Excel. Respaldo: {respaldo}.' + aviso,
                        'tablas': conteos, 'excels': excels, 'backup': respaldo}
        except Exception as e:
            return {'éxito': False, 'mensaje': f'No se pudo importar: {e}' +
                    (f'. Respaldo disponible: {respaldo}' if respaldo else '')}

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
        if nombre_limpio.endswith('.zip'):
            return self.importar_db(Path(ruta).read_bytes())
        # Mantener compatibilidad con los backups históricos .db.
        contenido = io.BytesIO()
        with _zipfile.ZipFile(contenido, 'w') as zf:
            zf.write(ruta, DB_FILE_NAME)
        return self.importar_db(contenido.getvalue(), incluir_excels=False)
