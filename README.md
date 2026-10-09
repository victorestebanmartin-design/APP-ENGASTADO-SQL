# Sistema de Engastado Automático

Aplicación web (Flask + SQLite) para la gestión del engastado de cables en fábrica:
órdenes de producción, bonos, carros, guiado del operario por terminal, etiquetas,
manguitos y preparación de mangueras.

## Arranque rápido

**En un PC de fábrica (Windows, sin permisos de administrador):**

```bat
INSTALAR.bat    :: primera vez: crea el venv e instala dependencias
ARRANCAR.vbs    :: el icono del día a día: arranca el servidor y abre la app
run.bat         :: lo mismo, pero con la consola a la vista (para depurar)
detener.bat     :: lo apaga a mano, si la web ya no responde
```

`ARRANCAR.vbs` no abre ninguna ventana de consola: arranca el servidor en segundo
plano, espera a que esté listo y abre COJOsw. Si el servidor ya estaba en marcha,
no arranca otro — solo abre la app, así que se puede pulsar las veces que haga falta.

Para tener un icono de COJOsw en el escritorio (en vez del icono genérico de
VBScript), ejecuta una vez `crear_icono_escritorio.vbs`: deja ahí un acceso
directo llamado **"Arrancar COJOsw"** con el icono de la app, apuntando a
`ARRANCAR.vbs`. (El nombre no puede empezar por "COJOsw" — eso lo reserva
`abrir_app.bat` para detectar la PWA instalada del navegador.)

El servidor queda en http://localhost:5001. Para apagarlo por las buenas:
**Admin → Sistema → Apagar servidor** (deja la app inaccesible para toda la nave,
y hay que volver al PC servidor para encenderla).

Guías detalladas: [INICIO.md](INICIO.md) y [GUIA_RAPIDA_SQLITE.md](GUIA_RAPIDA_SQLITE.md).

**Producción (PythonAnywhere):** se despliega desde el PC de desarrollo con
`python deploy.py "mensaje"` (hace push a GitHub, sincroniza el servidor, recarga la
app y baja un backup de la BD). También se puede actualizar desde el propio panel de
administración de la app (botón "Actualizar sistema", protegido por PIN).

## Estructura

```
APP-ENGASTADO-SQL/
├── config.py               # Configuración (rutas, PIN admin, impresora...)
├── run_sql.py / wsgi.py    # Arranque local / producción
├── schema_sqlite.sql       # Esquema de la base de datos
├── seed_inicial.json       # Datos iniciales (carros, puestos, máquinas, colores)
├── deploy.py               # Despliegue a PythonAnywhere
├── app/
│   ├── __init__.py         # Factory de la app + migraciones al arrancar
│   ├── auth.py             # Protección por PIN del módulo de administración
│   ├── excel_manager.py    # Lectura/caché de Excel y lógica de agrupación
│   └── routes/             # Rutas por dominio (blueprint 'main')
│       ├── base.py         #   helpers compartidos y acceso a BD
│       ├── bonos.py, ordenes.py, carros.py, proyectos.py
│       ├── etiquetas.py, manguitos.py, progreso.py, reports.py
│       ├── puestos.py, cable_colores.py, operarios.py
│       ├── trabajo_v3.py   #   vista de operario + sesiones de bloqueo
│       └── sistema.py      #   salud, actualización OTA, deploy hook
├── repositories/           # Capa de acceso a datos (SQL parametrizado)
├── templates/ y static/    # HTML, CSS y JS
├── migrations/             # Scripts SQL puntuales
└── tests/                  # Suite pytest (BD temporal, no toca datos reales)
```

## Base de datos

SQLite con WAL activado (soporta los 4-10 usuarios concurrentes de planta).
El fichero vive en `data/engastado.db` (fuera del repositorio). Una instalación
nueva se inicializa sola: esquema desde `schema_sqlite.sql` + datos de
`seed_inicial.json` (solo inserta lo que falte; lo gestionado desde el panel
de administración nunca se pisa).

## Editor de preparación de mangueras

Desde **Preparación Mangueras → Editar preparación**, abre un Excel `.xlsx` o
`.xlsm`, o selecciona un corte registrado. El editor propone las filas cuya
sección empieza por un número seguido de `x` (también `X` o `×`), y muestra
además las que ya contienen preparación. Cada entrada se identifica por su
fila del Excel, aunque coincidan marca y elemento.

Los lados **De** y **Para** permiten indicar pelado de manguera, pelado o corte
de malla, malla hacia atrás con/sin retráctil, medidas comunes e individuales
de activos y varios retráctiles con código y medida. También se pueden consultar
todos los campos originales de la fila.

Los cambios conservan un borrador en ese navegador, que se recupera al volver
a abrir el mismo Excel. **Guardar preparación** y **Guardar Excel** abren un
diálogo con dos opciones: **Solo descargar**, para obtener la copia completa
sin cambiar el servidor, y **Descargar y aplicar**, para descargarla y actualizar
el mismo archivo del corte. La copia mantiene las otras hojas, fórmulas y formato.

Aplicar exige una sesión de administración (el diálogo permite validar el PIN),
comprueba que el Excel del corte sigue siendo el mismo y guarda un backup antes
de sustituirlo. No cambia las asociaciones, etiquetas ni progreso del corte.
Si se abrió un Excel local, hay que seleccionar el corte de destino con ese
mismo Excel de origen. Para un corte nuevo, primero se registra por el flujo habitual.
Si la aplicación falla, la copia descargada y el borrador siguen disponibles.

Cada manguera admite **Observaciones de la manguera**. El texto se conserva en
el borrador y se escribe en la columna `Observaciones Mangueras` del Excel:
columna W si queda después de las columnas existentes, o al final si la hoja
ya llega más allá. Las observaciones originales del Excel no se modifican.

Los retráctiles se pueden elegir en la biblioteca de cada lado. El catálogo se
forma con los códigos que ya aparecen en los cortes Excel subidos; también se
puede escribir un código nuevo. Al añadirlo se propone una longitud de `30 mm`,
que se puede cambiar antes de guardar.

El editor muestra los activos asociados y sus terminales por lado. La asociación
exige longitud cero en el activo, marca común (por ejemplo, `1502-P` con `1502-1`
y `1502-2`), mismo código de cable, elemento de etiquetas (o el de origen si no
hay columna de etiquetas) y serie. También reconoce `2705(1)`/`2705(2)` como
activos de `2705` y `2705(S)` como su malla, aunque tenga un elemento físico
distinto como `RACK`. Admite además el número de activo en Observaciones cuando
coincide la marca. Activos y malla asociados no se ofrecen como mangueras separadas.
También admite el índice antes del paréntesis: `L1(1)`, `L2(2)` y `L3(3)` se
asocian a `L`; `L(S)` se identifica como su pantalla/malla. La vista previa
muestra línea, activos y malla por separado aunque la fila tenga `S/T`, e indica
que no hay terminal que engastar en ese lado.
En Zefiro, `J (RED)`, `J (WHITE)` y `J (BLUE)` se asocian a `J` como activos
por color, junto con `J(S)` como pantalla, sin mezclarlos con la manguera `N`.
Las asociaciones ambiguas o no identificadas se avisan y no se bloquean automáticamente.

Los nombres de los lados coinciden con engastado: **De = liso (sin guion)**,
**Para = lado del guion**. Aparecen tanto en el editor como en el guiado de preparación.

Al generar el Excel se revisan todas las mangueras asociadas con seguridad:
un lado sin **PM (pelado de manguera)** marca con `*` el elemento de ese lado
en los activos y en la propia manguera/malla. Es la misma regla que excluye
terminales de engastado y de sus conteos. Al añadir PM se retiran únicamente
los asteriscos automáticos del editor, nunca los manuales. Las columnas
`Bloqueo Mangueras DE/PARA` registran esa procedencia y deben conservarse.
Los cambios entran en vigor al aplicar el Excel al corte, no al editar el borrador.

## Administración

El panel de administración se protege con un PIN. Generar el hash e instalarlo:

```bash
python _scripts_utiles/generar_pin_hash.py   # genera ADMIN_PIN_HASH para el .env
```

Sin `ADMIN_PIN_HASH` en el `.env`, la protección queda desactivada (avisa al arrancar).
Hay bloqueo automático de 15 minutos tras 5 intentos fallidos de PIN.

## Tests

```bash
pip install -r requirements-dev.txt   # o: python -m pip ... si pip está bloqueado
pytest
```

La suite usa una base de datos temporal por test: se puede lanzar con la app en
marcha sin riesgo para los datos.
