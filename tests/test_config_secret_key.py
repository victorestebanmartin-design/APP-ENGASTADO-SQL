"""Pruebas de persistencia segura de la clave de sesión (config._cargar_o_generar_secret_key).

Usan siempre tmp_path como _BASE_DIR: nunca tocan el .secret_key real del
proyecto. Los procesos de multiprocessing son funciones a nivel de módulo
(requisito de 'spawn', el método por defecto en Windows) y todas las esperas
llevan timeout para que un fallo no deje pytest bloqueado.
"""
import multiprocessing
import os
import threading
import time

import pytest

import config


def _generar_clave_en_proceso(base_dir, inicio, resultados):
    os.environ.pop('SECRET_KEY', None)
    config._BASE_DIR = base_dir
    inicio.wait()
    resultados.put(config._cargar_o_generar_secret_key())


def test_workers_concurrentes_comparten_secret_key(tmp_path):
    inicio = multiprocessing.Event()
    resultados = multiprocessing.Queue()
    procesos = [
        multiprocessing.Process(
            target=_generar_clave_en_proceso,
            args=(str(tmp_path), inicio, resultados),
        )
        for _ in range(6)
    ]

    try:
        for proceso in procesos:
            proceso.start()
        inicio.set()
        claves = [resultados.get(timeout=15) for _ in procesos]
    finally:
        for proceso in procesos:
            proceso.join(timeout=15)
            if proceso.is_alive():
                proceso.terminate()
                proceso.join(timeout=5)
        resultados.close()
        resultados.join_thread()

    for proceso in procesos:
        assert not proceso.is_alive()
        assert proceso.exitcode == 0

    assert len(set(claves)) == 1
    assert (tmp_path / '.secret_key').read_text(encoding='utf-8') == claves[0]
    # No deben quedar temporales de publicación tras la carrera.
    assert list(tmp_path.glob('.secret_key.*.tmp')) == []
    assert not (tmp_path / '.secret_key.lock').exists()


def test_repara_secret_key_vacia(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)
    (tmp_path / '.secret_key').write_text('', encoding='utf-8')

    clave = config._cargar_o_generar_secret_key()

    assert clave
    assert (tmp_path / '.secret_key').read_text(encoding='utf-8') == clave


def test_chmod_fallido_no_impide_leer_clave(tmp_path, monkeypatch):
    ruta = tmp_path / '.secret_key'
    ruta.write_text('clave-existente', encoding='utf-8')
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setattr(config.os, 'chmod', lambda *_: (_ for _ in ()).throw(OSError()))

    assert config._cargar_o_generar_secret_key() == 'clave-existente'


def test_reutiliza_clave_existente_sin_tocar_el_candado(tmp_path, monkeypatch):
    ruta = tmp_path / '.secret_key'
    ruta.write_text('clave-existente', encoding='utf-8')
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)

    assert config._cargar_o_generar_secret_key() == 'clave-existente'
    # El camino rápido (clave ya publicada) no debe crear ni dejar un candado.
    assert not (tmp_path / '.secret_key.lock').exists()


def test_respeta_secret_key_de_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.setenv('SECRET_KEY', 'clave-del-entorno')

    assert config._cargar_o_generar_secret_key() == 'clave-del-entorno'
    # No se toca el fichero ni se crea nada en disco.
    assert not (tmp_path / '.secret_key').exists()
    assert not (tmp_path / '.secret_key.lock').exists()


def test_fallo_al_publicar_no_devuelve_clave_transitoria(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)

    def _replace_roto(*_a, **_kw):
        raise OSError('disco de pega')

    monkeypatch.setattr(config.os, 'replace', _replace_roto)

    with pytest.raises(RuntimeError) as exc_info:
        config._cargar_o_generar_secret_key()

    # El mensaje de error no debe filtrar ninguna clave generada.
    assert 'clave-' not in str(exc_info.value)
    # Ni el fichero final ni el candado deben quedar activos.
    assert not (tmp_path / '.secret_key').exists()
    assert not (tmp_path / '.secret_key.lock').exists()


def test_limpia_temporales_si_falla_la_escritura(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)

    def _fsync_roto(*_a, **_kw):
        raise OSError('fsync de pega')

    monkeypatch.setattr(config.os, 'fsync', _fsync_roto)

    with pytest.raises(RuntimeError):
        config._cargar_o_generar_secret_key()

    assert list(tmp_path.glob('.secret_key.*.tmp')) == []
    assert not (tmp_path / '.secret_key.lock').exists()


def test_perdedor_espera_a_que_el_ganador_publique(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setattr(config, '_SECRET_KEY_WAIT_TIMEOUT_S', 5.0)

    candado = tmp_path / '.secret_key.lock'
    candado.mkdir()

    def _ganador_lento():
        time.sleep(0.2)
        ruta = tmp_path / '.secret_key'
        ruta.write_text('clave-del-ganador', encoding='utf-8')
        candado.rmdir()

    hilo = threading.Thread(target=_ganador_lento)
    hilo.start()
    try:
        clave = config._cargar_o_generar_secret_key()
    finally:
        hilo.join(timeout=5)
        assert not hilo.is_alive()

    assert clave == 'clave-del-ganador'


def test_perdedor_falla_si_el_ganador_no_publica_a_tiempo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setattr(config, '_SECRET_KEY_WAIT_TIMEOUT_S', 0.2)

    candado = tmp_path / '.secret_key.lock'
    candado.mkdir()
    try:
        with pytest.raises(RuntimeError):
            config._cargar_o_generar_secret_key()
        # No debe haber generado ni publicado una clave propia.
        assert not (tmp_path / '.secret_key').exists()
    finally:
        candado.rmdir()


def test_candado_abandonado_se_libera(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_BASE_DIR', str(tmp_path))
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setattr(config, '_SECRET_KEY_LOCK_TIMEOUT_S', 0.05)

    candado = tmp_path / '.secret_key.lock'
    candado.mkdir()
    antiguo = time.time() - 10
    os.utime(candado, (antiguo, antiguo))

    clave = config._cargar_o_generar_secret_key()

    assert clave
    assert (tmp_path / '.secret_key').read_text(encoding='utf-8') == clave
    assert not candado.exists()
