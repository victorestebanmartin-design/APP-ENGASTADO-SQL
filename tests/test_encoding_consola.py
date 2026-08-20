"""Guardian de la salida por consola: un print no puede tumbar una peticion.

Hermano de test_encoding_ficheros.py, pero para stdout en vez de open().

El fallo real: run.bat manda la salida de la app a un fichero de log
(`python run_sql.py >> servidor.log`). Al no haber consola, Python usa en
Windows la codificacion regional para stdout, cp1252, donde no cabe ningun
emoji. Y como los mensajes de log llevan iconos, un print reventaba con
UnicodeEncodeError.

Lo grave no era perder la linea de log, sino que UnicodeEncodeError hereda de
ValueError: se colaba por los `except ValueError` de la ruta que lo estuviera
imprimiendo y se convertia en un fallo de la peticion. En planta se vio como:

  - Admin -> "Regenerar etiquetas" contestaba "'charmap' codec can't encode
    characters in position 0-1" (el print de las etiquetas borradas), y encima
    dejaba la tabla vacia porque el borrado ya habia hecho commit.
  - En engastado, elegir un terminal decia "no tiene trabajo en ningun carro"
    y no mostraba paquetes: el Excel se cargaba bien y lo que reventaba era el
    print de "Excel cargado" justo despues.
"""
import ast
import os
import subprocess
import sys

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Emoji de dos puntos de codigo (el icono + el selector de variacion U+FE0F):
# es el que salia en el mensaje de planta como "position 0-1".
EMOJI = '\U0001F5D1️'


def _python_con_stdout_cp1252(codigo):
    """Ejecuta 'codigo' con stdout en cp1252, como el Windows de fabrica."""
    entorno = dict(os.environ, PYTHONIOENCODING='cp1252')
    return subprocess.run(
        [sys.executable, '-c', codigo],
        cwd=RAIZ, env=entorno, capture_output=True, text=True,
        encoding='utf-8', errors='replace',
    )


def test_sin_forzar_utf8_un_print_con_emoji_revienta():
    """Control: sin el arreglo, el escenario de Windows falla de verdad.

    Si este test deja de fallar en el subproceso, es que ya no estamos
    reproduciendo el problema y el de abajo no demuestra nada.
    """
    r = _python_con_stdout_cp1252(f'print("{EMOJI} etiquetas eliminadas")')
    assert r.returncode != 0
    assert 'UnicodeEncodeError' in r.stderr


def test_forzar_utf8_deja_imprimir_cualquier_cosa():
    r = _python_con_stdout_cp1252(
        'from consola_utf8 import forzar_utf8\n'
        'forzar_utf8()\n'
        f'print("{EMOJI} etiquetas eliminadas")\n'
    )
    assert r.returncode == 0, r.stderr
    assert 'etiquetas eliminadas' in r.stdout


def _primeras_sentencias(ruta):
    """Sentencias del modulo, sin el docstring."""
    with open(ruta, encoding='utf-8') as f:
        cuerpo = ast.parse(f.read(), filename=ruta).body
    if (cuerpo and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)):
        cuerpo = cuerpo[1:]
    return cuerpo


def test_los_arranques_fuerzan_utf8_antes_que_nada():
    """run_sql.py y wsgi.py deben llamar a forzar_utf8() lo primero.

    Lo primero de verdad: si se cuela un import por delante y ese import
    imprime (o falla y escupe un traceback con acentos), volvemos al fallo.
    """
    for entrada in ('run_sql.py', 'wsgi.py'):
        cuerpo = _primeras_sentencias(os.path.join(RAIZ, entrada))
        assert len(cuerpo) >= 2, f'{entrada}: sin arranque de codificacion'

        importa = cuerpo[0]
        assert isinstance(importa, ast.ImportFrom), f'{entrada}: la 1a sentencia deberia importar forzar_utf8'
        assert importa.module == 'consola_utf8', f'{entrada}: la 1a sentencia deberia importar forzar_utf8'

        llamada = cuerpo[1]
        assert (isinstance(llamada, ast.Expr)
                and isinstance(llamada.value, ast.Call)
                and getattr(llamada.value.func, 'id', None) == 'forzar_utf8'), (
            f'{entrada}: falta la llamada a forzar_utf8() antes del resto')


def test_run_bat_fija_pythonioencoding():
    """Cinturon y tirantes: lo que se imprima antes de que corra nuestro
    codigo (un traceback de arranque, por ejemplo) tambien va en UTF-8."""
    with open(os.path.join(RAIZ, 'run.bat'), encoding='utf-8') as f:
        contenido = f.read().lower()
    assert 'set pythonioencoding=utf-8' in contenido


def _excel(ruta, columnas):
    pd.DataFrame(columnas).to_excel(ruta, sheet_name='Format', index=False)


def _excel_valido(ruta):
    _excel(ruta, {
        'Cod. cable': ['640C10023', '640C10024'],
        'Sección': ['0.5', '0.5'],
        'De Elemento Etiquetas': ['TB1', 'TB2'],
        'De Terminal': ['640204', '640204'],
        'Para Terminal': ['S/T', 'S/T'],
        'Descripción Cable': ['cable prueba', 'cable prueba'],
        'Longitud': [150, 150],
    })


def _cuantas_etiquetas(client, archivo):
    d = client.post('/api/etiquetas/cargar_grupos', json={'archivo': archivo}).get_json()
    return len(d.get('grupos', []))


def test_regenerar_etiquetas_funciona(admin_client, app):
    ruta = os.path.join(app.config['UPLOAD_FOLDER'], 'corte.xlsx')
    _excel_valido(ruta)

    d = admin_client.post('/api/etiquetas/regenerar', json={'archivo': 'corte.xlsx'}).get_json()
    assert d['success'], d
    assert d['total'] == 2
    assert _cuantas_etiquetas(admin_client, 'corte.xlsx') == 2


def test_un_excel_malo_no_deja_el_archivo_sin_etiquetas(admin_client, app):
    """Regenerar es sustituir, no 'borrar y a ver si sale'.

    Antes se borraba y se hacia commit ANTES de leer el Excel: si la lectura
    fallaba, el archivo se quedaba sin ninguna etiqueta y en engastado el
    terminal salia como completado sin ensenar un solo paquete.
    """
    ruta = os.path.join(app.config['UPLOAD_FOLDER'], 'corte.xlsx')
    _excel_valido(ruta)
    admin_client.post('/api/etiquetas/regenerar', json={'archivo': 'corte.xlsx'})
    assert _cuantas_etiquetas(admin_client, 'corte.xlsx') == 2

    # El mismo archivo, ahora sin la columna de elementos
    _excel(ruta, {'Cod. cable': ['640C10023'], 'Sección': ['0.5']})
    r = admin_client.post('/api/etiquetas/regenerar', json={'archivo': 'corte.xlsx'})
    d = r.get_json()
    assert not d['success']
    assert 'columnas requeridas' in d['message']

    assert _cuantas_etiquetas(admin_client, 'corte.xlsx') == 2, (
        'las etiquetas anteriores se han perdido al fallar la regeneracion')
