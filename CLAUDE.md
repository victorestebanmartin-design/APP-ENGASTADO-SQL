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
