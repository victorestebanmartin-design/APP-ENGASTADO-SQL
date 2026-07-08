# Informe Técnico — COJO SW

**Aplicación:** COJO SW — *Crimping Operations, Jobs & Orders Software* (Sistema de Engastado Automático)
**Organización:** MERAK · Knorr-Bremse
**Destinatario:** Departamento de IT
**Autor:** Víctor Esteban Martín
**Fecha:** Julio 2026
**Versión de la aplicación:** 3.0 Pro

---

## 1. ¿Qué es la aplicación?

**COJO SW** es una **aplicación web interna** para la gestión integral del proceso de **engastado de cables** en producción. Su nombre resume sus funciones: **C**rimping (engastado automático de terminales), **O**perations (gestión de planta en tiempo real), **J**obs (bonos y lotes de producción), **O**rders (trazabilidad y seguimiento completos) y **SW** (software — aplicación web local). Cubre todo el ciclo de trabajo de la planta:

1. **Carga del listado de cables** (archivos Excel de corte) desde el panel de administración.
2. **Generación de etiquetas** identificativas para los elementos de cable (formato A4 troquelado e impresora Zebra ZPL).
3. **Órdenes de producción**: registro, estados (pendiente → en bono → en proceso → completado) y planificación.
4. **Bonos de trabajo**: agrupación de órdenes que se fabrican juntas, con asignación a **carros físicos** (1–6).
5. **Guiado del operario en máquina** (módulo Engastado V3): el operario se identifica escaneando su código de barras, el sistema le muestra los terminales pendientes agrupados por máquina (para minimizar cambios de herramienta) y va confirmando cada engastado con progreso en tiempo real.
6. **Preparación de consumibles**: manguitos (guiado de colocación y generación de ficheros TXT de pedido al proveedor) y mangueras (instrucciones de pelado guiadas).
7. **Visualización**: dashboard en tiempo real pensado para una pantalla de planta (progreso por bono y por carro).
8. **Trazabilidad**: informe PDF por carro con terminal, operario y fecha/hora de cada engastado.

Los usuarios acceden desde cualquier PC de la nave con un **navegador web**; no se instala nada en los puestos cliente.

---

## 2. Arquitectura y tecnologías

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.13 (64 bits) |
| Framework web | Flask 3.1 (plantillas Jinja2) |
| Base de datos | SQLite (fichero único `data/engastado.db`, modo WAL) |
| Acceso a datos | SQLAlchemy + capa de repositorios con SQL parametrizado |
| Servidor de aplicación | Waitress (WSGI para Windows) |
| Frontend | HTML, CSS y JavaScript estándar (sin frameworks, sin CDNs externos) |
| Procesamiento Excel | pandas + openpyxl |
| Impresión de etiquetas | Impresora Zebra (lenguaje ZPL), con modo simulación configurable |

**Estructura interna:** la aplicación sigue el patrón *application factory* de Flask, con las rutas separadas por dominio funcional (bonos, órdenes, carros, etiquetas, manguitos, progreso, informes, sistema…) y una **capa de repositorios** que concentra todo el acceso a base de datos. Esta separación facilita el mantenimiento y una eventual migración a otro motor de base de datos.

**Punto importante:** la aplicación **no depende de ningún servicio externo**. No usa SQL Server, no llama a APIs de internet y no necesita conexión a internet para funcionar. Toda la información vive en un único fichero SQLite local.

---

## 3. Modelo de despliegue (producción)

La instalación definitiva se ejecuta **en red local, sin conexión a internet**:

- Un **PC servidor** (Windows 10, 64 bits) ejecuta la aplicación, que escucha en el puerto **TCP 5001** para toda la red local.
- El resto de PCs de la nave acceden por navegador a `http://IP-DEL-SERVIDOR:5001`.
- Existe un **paquete de instalación offline** completo (`paquete_offline`): instalador de Python 3.13 y todas las dependencias ya descargadas (wheels), con un instalador automático (`INSTALAR_OFFLINE.bat`). No se descarga nada de internet.
- Endpoint de comprobación: `http://IP-DEL-SERVIDOR:5001/health` responde `{"status": "ok"}`.

### Requisitos del PC servidor

1. Windows 10, 64 bits.
2. Python 3.13.x de 64 bits (incluido en el paquete offline).
3. Puerto TCP 5001 abierto en el Firewall de Windows (regla de entrada). Es lo único que requiere permisos de administrador; la aplicación en sí **no necesita permisos de administrador** para instalarse ni ejecutarse.
4. **IP fija** para que la URL de acceso no cambie.
5. (Opcional) Tarea programada que ejecute `run.bat` al iniciar sesión, para arranque automático.

### Requisitos de los PCs cliente

- Únicamente un navegador moderno (Edge, Chrome o Firefox) y acceso a la red local. Sin instalación.

### Periféricos

- (Opcional) Impresora de etiquetas **Zebra GK420T** conectada al servidor. Si no está disponible, la app funciona en modo simulación.
- Lectores de código de barras estándar (emulación de teclado) en los puestos de operario.

---

## 4. Cómo se ha construido

El desarrollo se ha realizado con **Visual Studio Code** como entorno de trabajo, apoyado en **GitHub Copilot** con sus distintos modelos de IA — principalmente **Claude Sonnet y Claude Opus (Anthropic)** — como asistentes de programación. El flujo de trabajo ha sido iterativo: diseño de cada módulo, generación y revisión de código asistida por IA, y validación funcional en planta con los operarios.

Herramientas utilizadas:

- **Visual Studio Code** — editor / IDE principal.
- **GitHub Copilot** (modelos Claude Sonnet y Claude Opus) — asistencia de IA para diseño, codificación, revisión y documentación.
- **Python + Flask** — desarrollo del backend.
- **pytest** — pruebas automatizadas.

Durante el desarrollo se han usado entornos de prueba temporales para validar la aplicación con usuarios reales antes de la instalación definitiva; **esos entornos no forman parte de la solución final**, que corre exclusivamente en la red local de la nave.

---

## 5. Seguridad

- **Sin exposición a internet:** la aplicación solo es accesible desde la red local; en producción el servidor no tiene salida a internet.
- **Panel de administración protegido por PIN:** el PIN no se guarda en claro, sino como hash SHA-256 en un fichero `.env` local. Tras **5 intentos fallidos, bloqueo automático de 15 minutos**. La sesión de administrador expira a las 8 horas.
- **Clave de sesión única por instalación:** la `SECRET_KEY` de Flask se genera aleatoriamente en cada instalación (no viene fijada en el código).
- **SQL parametrizado en toda la capa de datos:** protección frente a inyección SQL.
- **Subida de ficheros restringida:** solo `.xlsx`/`.xls`, con límite de 50 MB, y rutas de ficheros validadas (existen pruebas específicas de seguridad de rutas).
- **Escritura protegida** en la gestión de máquinas y terminales (solo desde sesión de administrador).
- **Sin datos personales sensibles:** la base de datos contiene datos de producción (órdenes, bonos, terminales) e identificadores de operario para trazabilidad.

---

## 6. Escalabilidad y rendimiento

- SQLite con **modo WAL** soporta con holgura la carga real de planta (4–10 usuarios concurrentes). Es una carga de lectura intensiva con escrituras cortas (confirmaciones de engastado), el escenario ideal para SQLite.
- Las conexiones se gestionan con *pool* (verificación y reciclado automático) y timeout de 30 s ante bloqueos.
- El frontend se actualiza mediante peticiones ligeras al servidor (progreso en tiempo real sin recargar página).
- **Ruta de crecimiento:** si en el futuro aumentara significativamente el número de usuarios o de plantas, la capa de repositorios permite migrar a un motor cliente-servidor (PostgreSQL / SQL Server) sin reescribir la lógica de negocio. También puede ejecutarse en un servidor más potente sin cambio alguno: la aplicación es la misma.

---

## 7. Calidad y mantenimiento

- **Suite de más de 60 pruebas automatizadas (pytest)** que cubren autenticación, bonos, órdenes, procesamiento de Excel, seguridad de ficheros y endpoints. Las pruebas usan una base de datos temporal, por lo que pueden ejecutarse con la aplicación en marcha sin riesgo para los datos reales.
- **Copia de seguridad trivial:** basta con copiar el fichero `data\engastado.db` (puede copiarse en caliente). Se recomienda una tarea programada de copia diaria a otra ubicación de red.
- **Logs** de aplicación en `logs\app.log`.
- **Actualizaciones:** al no haber internet, una actualización consiste en sustituir la carpeta de la aplicación por la nueva versión (la base de datos y el `.env` se conservan; las migraciones de esquema se aplican solas al arrancar).
- **Inicialización automática:** una instalación nueva crea sola el esquema y los datos maestros iniciales (carros, puestos, máquinas, colores).

---

## 8. Resumen para IT

| Aspecto | Valor |
|---|---|
| Nombre | COJO SW v3.0 Pro |
| Tipo | Aplicación web interna (intranet) |
| Servidor | 1 PC Windows 10 x64 con Python 3.13 |
| Clientes | Navegador web, sin instalación |
| Puerto | TCP 5001 (regla de entrada en firewall) |
| Internet | **No requerida** (instalación y funcionamiento 100 % offline) |
| Base de datos | SQLite, fichero único local |
| Backup | Copia del fichero `data\engastado.db` |
| Permisos de administrador | Solo para la regla de firewall |
| Servicios externos | Ninguno |
