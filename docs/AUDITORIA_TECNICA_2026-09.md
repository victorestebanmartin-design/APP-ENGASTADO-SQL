# Auditoría técnica — septiembre de 2026

## Alcance

Revisión estática del backend Flask, configuración, acceso SQLite, endpoints de
administración, subida/restauración de archivos y suite automatizada. La suite
completa (`python -m pytest`) se ha ejecutado: 552 tests pasan, 3 se omiten y 4
fallan por causas ajenas a esta auditoría (firmware/latencia ESP32 y una regla de
expiración de sesión de operario — ver A-06). Esta revisión no sustituye un pentest
de red, una prueba de carga en el hardware de planta ni una restauración ensayada
con una copia de la base de datos de producción.

## Resumen ejecutivo

La aplicación cuenta con buenas defensas para su contexto: consultas parametrizadas,
rutas administrativas decoradas, comparación constante del PIN, límite de intentos,
validación de rutas de archivos, errores con referencia sin filtrar excepciones y
tests con una base SQLite aislada. No se identificó una vulnerabilidad crítica
explotable durante esta revisión.

Se corrigieron dos riesgos de severidad media:

1. Las respuestas no incluían cabeceras contra *clickjacking* y detección MIME.
2. La creación de `.secret_key` no era atómica y heredaba permisos dependientes del
   `umask`; dos workers simultáneos podían usar claves distintas durante el arranque.

La revisión automática posterior detectó que crear el archivo con `O_EXCL` antes de
escribir todavía dejaba una ventana en la que otro worker podía leerlo vacío. Una
primera corrección publicaba la clave mediante un enlace duro (`os.link`), pero un
segundo repaso (Codex Review, severidad P2) encontró una carrera distinta: los
workers que reparaban un `.secret_key` vacío heredado podían borrar la clave que otro
worker acababa de publicar. Se sustituyó todo el mecanismo por un candado explícito
(un directorio `.secret_key.lock`, creado con `os.mkdir`, atómico en POSIX y en
Windows) que serializa por completo la generación/reparación, y por `os.replace`
para publicar el fichero final de forma atómica sin depender de enlaces duros
(no soportados en todos los sistemas de archivos de Windows). También se reparan
archivos vacíos heredados y el arranque falla explícitamente si no puede
persistirse, o leerse, una clave compartida.

## Hallazgos

### A-01 — Cabeceras defensivas ausentes (media, corregido)

Se añadieron `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, una política
de referente limitada al mismo origen y una `Permissions-Policy` restrictiva.
`Strict-Transport-Security` solo se emite si `SESSION_COOKIE_SECURE` está activo,
porque forzar HTTPS rompería los puestos que deliberadamente usan HTTP en la LAN.

No se habilitó todavía una Content Security Policy: varias plantillas contienen
JavaScript y CSS inline. Primero deben migrarse a archivos estáticos o a *nonces* y
probarse todas las pantallas operativas.

### A-02 — Persistencia de la clave de sesión (media, corregido)

`config._cargar_o_generar_secret_key` serializa la generación con un candado
(directorio `.secret_key.lock`, creación atómica vía `os.mkdir`) para que, si varios
procesos arrancan a la vez, solo uno genere y publique la clave; los demás esperan
(con un tope de tiempo) y leen la misma clave publicada, en vez de generar cada uno
la suya. La publicación usa `os.replace` sobre un temporal ya escrito, sincronizado
(`flush` + `fsync`) y con permisos `0600`, que es atómico tanto en POSIX como en
Windows: ningún proceso puede leer un fichero a medio escribir, y no hace falta
borrar el fichero anterior (vacío o con contenido) antes de publicar el nuevo. Un
candado más viejo que el tiempo máximo de escritura se considera abandonado (proceso
muerto a medio camino) y se libera para no bloquear el arranque indefinidamente.
Si no se puede persistir ni leer una clave compartida, el arranque falla con un
`RuntimeError` en vez de continuar con una clave transitoria distinta por proceso.

### A-03 — Administración sin PIN permitida (alta, riesgo aceptado pendiente)

Si `ADMIN_PIN_HASH` está vacío, los endpoints administrativos quedan abiertos por
diseño para facilitar la primera instalación. Aunque se muestra un aviso visible al
arrancar, esto es peligroso si el servidor queda accesible desde una red no
confiable.

**Recomendación:** hacer obligatorio el PIN en una futura versión con un flujo de
alta inicial, y mientras tanto verificar `ADMIN_PIN_HASH` en cada instalación antes
de exponer el puerto 5001.

### A-04 — HTTPS opcional en la red de planta (media, pendiente de infraestructura)

Las cookies ya son `HttpOnly` y `SameSite=Lax`; el atributo `Secure` puede activarse
con `SESSION_COOKIE_SECURE=true`. En HTTP, un usuario con capacidad de observar la
LAN podría capturar tráfico o sesiones.

**Recomendación:** terminar TLS en un proxy local, activar
`SESSION_COOKIE_SECURE=true` y restringir el acceso al servidor mediante firewall a
las subredes y dispositivos necesarios.

### A-05 — Antifuerza bruta local al proceso (baja, pendiente)

El contador de intentos de PIN reside en memoria y por proceso. Un reinicio lo borra
y varios workers no comparten el estado. Para el despliegue pequeño actual reduce
ataques casuales, pero no constituye un limitador distribuido.

**Recomendación:** persistir los intentos en SQLite o aplicar limitación en el proxy
si aumenta la exposición o el número de workers.

### A-06 — El blueprint de rutas no sobrevivía a una segunda app (alta, corregido)

Encontrado al ejecutar la suite completa para validar esta auditoría, no al
revisarla estáticamente: `app/routes/base.py` creaba el blueprint `main` de nuevo
en cada `init_routes()` (pensado para dar una app aislada a cada test), pero los
módulos de rutas (`paginas.py`, `sistema.py`, etc.) importan `bp` una sola vez, la
primera vez que Python los carga, y quedan cacheados. Solo la primera app creada en
todo el proceso de `pytest` tenía sus rutas de verdad registradas; cualquier app
posterior (es decir, casi todos los tests) registraba un blueprint `main` vacío, y
toda petición devolvía 404 en vez de la respuesta esperada. Se revirtió a un
blueprint único creado una sola vez a nivel de módulo: Flask permite registrar el
mismo `Blueprint` en varias instancias de `Flask`, que es justo lo que necesitan los
tests, sin recrearlo. La ruta de diagnóstico de `app/observabilidad.py`
(`/api/sistema/carga`) pasa a registrarse directamente en `app` en vez de en el
blueprint, para no depender de en qué momento del arranque se registra éste.

## Prioridades recomendadas

1. Confirmar que todas las instalaciones tienen `ADMIN_PIN_HASH` y copias de
   seguridad restaurables.
2. Restringir por firewall y planificar HTTPS para la LAN.
3. Eliminar scripts y estilos inline para poder desplegar una CSP estricta.
4. Ejecutar una prueba de restauración y una prueba de concurrencia con el número
   real de puestos antes de cambios importantes de producción.
