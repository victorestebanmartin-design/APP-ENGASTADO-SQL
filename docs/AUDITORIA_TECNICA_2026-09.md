# Auditoría técnica — septiembre de 2026

## Alcance

Revisión estática del backend Flask, configuración, acceso SQLite, endpoints de
administración, subida/restauración de archivos y suite automatizada. Se intentó
ejecutar la suite completa, pero el entorno no incluía las dependencias de la app y
el proxy impidió instalarlas. Esta revisión no sustituye un pentest de red,
una prueba de carga en el hardware de planta ni una restauración ensayada con una
copia de la base de datos de producción.

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

La clave se crea ahora en exclusiva con permisos `0600`. Si dos procesos arrancan a
la vez, solo uno crea el fichero y el otro lee la clave ganadora. Los ficheros ya
existentes también se restringen a `0600` en sistemas compatibles.

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

## Prioridades recomendadas

1. Confirmar que todas las instalaciones tienen `ADMIN_PIN_HASH` y copias de
   seguridad restaurables.
2. Restringir por firewall y planificar HTTPS para la LAN.
3. Eliminar scripts y estilos inline para poder desplegar una CSP estricta.
4. Ejecutar una prueba de restauración y una prueba de concurrencia con el número
   real de puestos antes de cambios importantes de producción.
