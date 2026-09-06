import io
import json
import sqlite3
import zipfile
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from app.config_manager import ConfigManager


@pytest.fixture
def manager(tmp_path):
    data = tmp_path / 'data'
    (data / 'cortes').mkdir(parents=True)
    with closing(sqlite3.connect(data / 'engastado.db')) as conn:
        conn.executescript(Path('schema_sqlite.sql').read_text(encoding='utf-8'))
    engine = create_engine('sqlite:///' + str(data / 'engastado.db'))
    yield ConfigManager(SimpleNamespace(engine=engine), str(tmp_path))
    engine.dispose()


def archive(db, files=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('engastado.db', db)
        for name, content in (files or {}).items():
            z.writestr(name, content)
    return buf.getvalue()


def test_roundtrip_progress_and_documents(manager):
    root = Path(manager.data_dir)
    (root / 'progreso_bono_a.json').write_text('{"T1":{"completado":true}}')
    (root / 'maquinas_pdf').mkdir()
    (root / 'maquinas_pdf/ficha.pdf').write_bytes(b'PDF fixture')
    payload, _ = manager.exportar_completo()
    (root / 'progreso_bono_a.json').write_text('{}')
    (root / 'progreso_bono_sobrante.json').write_text('{}')
    result = manager.importar_db(payload)
    assert result['éxito'], result
    assert json.loads((root / 'progreso_bono_a.json').read_text())['T1']['completado']
    assert not (root / 'progreso_bono_sobrante.json').exists()
    assert (root / 'maquinas_pdf/ficha.pdf').read_bytes() == b'PDF fixture'
    assert (root / result['backup']).exists()
    assert manager.restaurar_backup(result['backup'])['éxito']
    assert (root / 'progreso_bono_sobrante.json').exists()


@pytest.mark.parametrize('invalid', [b'not sqlite', b''])
def test_invalid_database_does_not_touch_excel(manager, invalid):
    excel = Path(manager.cortes_dir, 'a.xlsx')
    excel.write_bytes(b'original')
    before = Path(manager.db_path).read_bytes()
    result = manager.importar_db(archive(invalid, {'cortes/a.xlsx': b'changed'}))
    assert not result['éxito']
    assert 'WinError 32' not in result['mensaje']
    assert excel.read_bytes() == b'original'
    assert Path(manager.db_path).read_bytes() == before


def test_invalid_json_does_not_touch_excel(manager):
    excel = Path(manager.cortes_dir, 'a.xlsx'); excel.write_bytes(b'original')
    result = manager.importar_db(archive(manager._db_a_bytes(), {'cortes/a.xlsx': b'changed', 'progreso_bono_a.json': b'broken'}))
    assert not result['éxito']
    assert excel.read_bytes() == b'original'


@pytest.mark.parametrize('name', ['../outside.xlsx', 'cortes/../../outside.xlsx', 'cortes/..\\outside.xlsx', 'C:/evil.xlsx'])
def test_unsafe_path_rejected(manager, name):
    result = manager.importar_db(archive(manager._db_a_bytes(), {name: b'bad'}))
    assert not result['éxito']


def test_apply_failure_rolls_back_files_and_db(manager, monkeypatch):
    excel = Path(manager.cortes_dir, 'a.xlsx'); excel.write_bytes(b'original')
    original = manager._reemplazar_db
    attempts = []
    def fail_once(path):
        attempts.append(path)
        if len(attempts) == 1:
            raise OSError('Fallo simulado al restaurar')
        return original(path)
    monkeypatch.setattr(manager, '_reemplazar_db', fail_once)
    result = manager.importar_db(archive(manager._db_a_bytes(), {'cortes/a.xlsx': b'changed', 'cortes/new.xlsx': b'new'}))
    assert not result['éxito']
    assert excel.read_bytes() == b'original'
    assert not Path(manager.cortes_dir, 'new.xlsx').exists()
    assert len(attempts) == 2
    assert manager.listar_backups()


def test_legacy_and_excel_optout(manager):
    excel = Path(manager.cortes_dir, 'a.xlsx'); excel.write_bytes(b'original')
    result = manager.importar_db(archive(manager._db_a_bytes(), {'cortes/a.xlsx': b'changed'}), incluir_excels=False)
    assert result['éxito']
    assert excel.read_bytes() == b'original'
    assert 'no garantiza' in result['mensaje']


def test_backup_guard_blocks_requests_and_recovers(app, client):
    ruta = str(Path(app.config['DATA_DIR'], '.maintenance.sqlite'))
    with closing(sqlite3.connect(ruta, isolation_level=None)) as conn:
        conn.execute('BEGIN EXCLUSIVE')
        assert client.get('/health').status_code == 503
        conn.rollback()
    assert client.get('/health').status_code == 200


def test_backup_guard_rejects_restore_during_request(app, admin_client):
    ruta = str(Path(app.config['DATA_DIR'], '.maintenance.sqlite'))
    with closing(sqlite3.connect(ruta, isolation_level=None)) as conn:
        conn.execute('BEGIN'); conn.execute('SELECT * FROM guardia').fetchall()
        assert admin_client.post('/api/importar/db').status_code == 503
        conn.rollback()
    assert admin_client.post('/api/importar/db').status_code == 400
