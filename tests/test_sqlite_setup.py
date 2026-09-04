"""Pruebas de la inicialización segura de SQLite."""

import sqlite3

import pytest

from sqlite_setup import inicializar_sqlite


def test_inicializa_base_desde_esquema(tmp_path):
    schema = tmp_path / 'schema.sql'
    schema.write_text('CREATE TABLE ejemplo (id INTEGER PRIMARY KEY);', encoding='utf-8')
    db_path = tmp_path / 'data' / 'app.db'

    assert inicializar_sqlite(str(db_path), str(schema)) is True

    with sqlite3.connect(db_path) as conn:
        tabla = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ejemplo'"
        ).fetchone()
    assert tabla == ('ejemplo',)


def test_no_modifica_una_base_existente(tmp_path):
    db_path = tmp_path / 'app.db'
    db_path.write_bytes(b'contenido existente')
    schema = tmp_path / 'schema.sql'
    schema.write_text('CREATE TABLE ejemplo (id INTEGER);', encoding='utf-8')

    assert inicializar_sqlite(str(db_path), str(schema)) is False
    assert db_path.read_bytes() == b'contenido existente'


def test_elimina_base_parcial_si_falla_el_esquema(tmp_path):
    db_path = tmp_path / 'app.db'
    schema = tmp_path / 'schema.sql'
    schema.write_text(
        'CREATE TABLE creada (id INTEGER); SENTENCIA SQL INVALIDA;',
        encoding='utf-8',
    )

    with pytest.raises(sqlite3.Error):
        inicializar_sqlite(str(db_path), str(schema))

    assert not db_path.exists()
