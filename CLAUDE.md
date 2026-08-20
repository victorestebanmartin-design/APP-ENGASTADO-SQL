# Notas para trabajar en este repo

El README explica qué es la aplicación y cómo arrancarla. Esto es lo otro: las
trampas que ya han costado un rato de diagnóstico y conviene no repetir.

## El servidor puede ser Windows

En fábrica la app corre en un PC Windows (`run.bat`), no solo en PythonAnywhere.
Lo que en Linux es inofensivo, allí revienta.

**Todo `open()` de texto lleva `encoding='utf-8'`, al leer y al escribir.** Sin
él, Python usa la codificación del sistema: UTF-8 en Linux, cp1252 en Windows.
cp1252 no sabe escribir la flecha `→` que llevan los consejos de la UI ("Admin →
Operarios → Módulos permitidos"), así que guardar un evento con acentos o flechas
lanzaba `UnicodeEncodeError`. El síntoma en planta era engañoso: pasar una tarjeta
sin permisos devolvía "error interno del servidor" en vez del motivo real, y en
desarrollo funcionaba perfecto.

`tests/test_encoding_ficheros.py` recorre el código con `ast` y falla si aparece
un `open()` de texto sin `encoding`. Si salta, no lo silencies: añade el
`encoding='utf-8'`.

**Lo mismo vale para `print()`.** `run.bat` manda la salida a un fichero de log,
y sin consola Python usa cp1252 para stdout: un emoji en un mensaje de log
lanzaba `UnicodeEncodeError`. Y como `UnicodeEncodeError` hereda de
`ValueError`, se colaba por los `except ValueError` de la ruta y tumbaba la
petición: "Regenerar etiquetas" devolvía `'charmap' codec can't encode...` (y
dejaba la tabla vacía), y elegir un terminal en engastado no encontraba
paquetes porque el print de después de cargar el Excel reventaba.

Los arranques (`run_sql.py`, `wsgi.py`) llaman a `consola_utf8.forzar_utf8()` lo
primero de todo, y `run.bat` fija `PYTHONIOENCODING=utf-8`. Lo vigila
`tests/test_encoding_consola.py`. No metas nada por delante de esa llamada.

## Regenerar es sustituir

Al rehacer datos derivados de un Excel (`_regenerar_etiquetas_archivo`), calcula
primero y borra después, en la misma transacción. Si se borra con `commit` y el
Excel falla luego, el archivo se queda sin etiquetas y engastado da el terminal
por completado sin enseñar un paquete: el operario no ve un error, ve trabajo
que ya no existe.

## Firmware de las placas ESP32

`esp32/` es MicroPython, no CPython: su `open()` **no** acepta `encoding` (por eso
esa carpeta está excluida del test de arriba).

Las placas se actualizan por OTA, y el servidor anuncia la versión leyendo
`FW_VERSION` de `esp32/main.py` **del código desplegado**
(`app/routes/sistema.py:_rfid_firmware_version`). Así que al tocar el firmware:

1. Sube `FW_VERSION` (formato `AAAA-MM-DDx`), o las placas no verán nada nuevo.
2. Actualiza el servidor: mientras siga con el código viejo, sigue sirviendo el
   firmware viejo.
3. Comprueba en Admin → Lectores RFID que las placas han cogido la versión.

## Rechazos de tarjeta: el mensaje es parte del arreglo

El operario que pasa la tarjeta no puede hacer nada con un "error interno". Cada
rechazo (`_rechazo` en `app/routes/operarios.py`) guarda **motivo** (qué ha
pasado) y **consejo** (qué hacer), y las dos pantallas que los pintan
(`templates/login_operario.html` y `static/js/v3/v3-rfid-entrada.js`) muestran
ambos. Un rechazo sin consejo deja al operario parado delante del lector.

En el firmware, cualquier **4xx** es una decisión del servidor sobre esa tarjeta
→ pitido de rechazo con su motivo. El error técnico (tres pitidos) queda solo
para 5xx o sin respuesta.

## Tests

```bash
python -m pytest          # la suite entera, ~2 min
```

Cada test recibe su propia BD SQLite temporal creada desde `schema_sqlite.sql`
(ver `tests/conftest.py`); nunca se toca `data/engastado.db`.
