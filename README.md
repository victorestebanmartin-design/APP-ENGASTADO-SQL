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
