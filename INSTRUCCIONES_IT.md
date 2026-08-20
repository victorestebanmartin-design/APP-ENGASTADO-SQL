# INSTALACIÓN — APP ENGASTADO (servidor de nave)

## Qué es
Aplicación web interna (Python + Flask + SQLite). Se ejecuta en un PC que hace
de servidor; el resto de PCs de la nave acceden por navegador a:

    http://IP-DEL-SERVIDOR:5001

No usa SQL Server ni ningún servicio externo. La base de datos es un único
archivo local (`data\engastado.db`).

---

## Requisitos en el PC servidor (Windows 10, 64 bits)
1. **Python 3.13.x (64 bits)** desde https://www.python.org/downloads/
   - En el instalador, **MARCAR "Add Python to PATH"**.
   - IMPORTANTE: debe ser 3.13 de 64 bits. Con otra versión, la instalación
     offline (carpeta `paquete_offline\wheels`) no será compatible.
2. Puerto **TCP 5001** abierto en el Firewall de Windows (regla de ENTRADA).
3. **IP fija** para el PC (para que la URL no cambie).
4. **Que el PC no se suspenda** (ver más abajo: *El servidor no puede dormirse*).
5. (Opcional) Arranque automático: tarea programada que ejecute `run.bat` al
   iniciar sesión.

---

## Instalación (con internet)
1. Copiar la carpeta **`APP-ENGASTADO-SQL`** completa al disco del servidor
   (p. ej. `C:\ENGASTADO`). Debe incluir:
   - `data\engastado.db`  (la base de datos con los datos reales)
   - `.env`               (archivo oculto; contiene el PIN de administrador)
   - **NO** copiar la carpeta `venv\` (se regenera en el servidor).
2. Doble clic en **`INSTALAR.bat`**
   - Crea el entorno virtual e instala dependencias (las descarga de internet).
3. Doble clic en **`run.bat`** para arrancar. Se abrirá el navegador en
   http://localhost:5001

---

## Instalación OFFLINE (si el servidor NO tiene internet)
La carpeta **`paquete_offline`** ya incluye TODO lo necesario:
- `python-3.13.14-amd64.exe` — instalador offline de Python 3.13 (64 bits).
- `wheels\` — todas las dependencias ya descargadas.
- `INSTALAR_OFFLINE.bat` — instalador automático (Python + dependencias).

### Opción A — Automática (recomendada)
1. Copiar la carpeta de la app al servidor (con `data\engastado.db` y `.env`).
2. Doble clic en **`paquete_offline\INSTALAR_OFFLINE.bat`**.
   - Si Python 3.13 no está, lo instala solo; después vuelve a ejecutar el
     mismo `.bat` (para que el PATH quede actualizado).
   - Crea el entorno virtual e instala las dependencias desde los wheels.
3. Ejecutar **`run.bat`**.

### Opción B — Manual
1. Instalar Python: doble clic en `paquete_offline\python-3.13.14-amd64.exe`
   y **MARCAR "Add Python to PATH"**.
2. Copiar la carpeta de la app al servidor (con `data\engastado.db` y `.env`).
3. Abrir **PowerShell** en la carpeta de la app y ejecutar:

        python -m venv venv
        venv\Scripts\activate
        pip install --no-index --find-links paquete_offline\wheels -r requirements.txt

4. Ejecutar **`run.bat`**.

---

## Abrir el puerto en el Firewall (PowerShell como administrador)

    New-NetFirewallRule -DisplayName "App Engastado 5001" -Direction Inbound -Protocol TCP -LocalPort 5001 -Action Allow

---

## El servidor no puede dormirse

Un PC de oficina viene configurado para **suspenderse solo** a los pocos
minutos sin teclado ni ratón. El PC servidor es justo eso: nadie lo toca, solo
sirve peticiones por red. Suspendido no va lento, **está parado**: la CPU no
ejecuta y la tarjeta de red se apaga, así que el puerto 5001 deja de existir.

Cómo se ve desde la planta (y por qué despista):
- Los PCs de puesto: *«No se puede acceder a este sitio»*.
- Las placas ESP32: sin respuesta → pitido de error técnico.
- En cuanto alguien mueve el ratón del servidor, vuelve todo solo.
- En los logs de la app **no hay ningún error**: hay un hueco.

El tráfico de red **no** despierta al equipo (eso sería Wake-on-LAN, que
además no reanudaría una petición HTTP a medias).

**La app ya se defiende sola:** al arrancar le pide a Windows que no suspenda el
equipo mientras el servidor esté en marcha (`mantener_despierto.py`). No
necesita permisos de administrador y deja de aplicarse al parar el servidor.
En el log de arranque (`logs\servidor_*.log`) aparece la línea:

    Suspension del PC: evitada -> el equipo no se suspendera mientras el servidor este en marcha

Si ahí pone `SIN evitar`, la protección **no** se aplicó y hay que configurar el
plan de energía a mano.

**Configurarlo también en Windows (recomendado, cinturón y tirantes).** En una
consola normal del usuario que arranca la app, **sin permisos de
administrador**:

    powercfg /change standby-timeout-ac 0
    powercfg /change hibernate-timeout-ac 0
    powercfg /change disk-timeout-ac 0

(`0` = nunca; `-ac` = enchufado a la corriente. Si el servidor fuese un
portátil, repetir con `-dc` para batería.) La pantalla puede seguir
apagándose: no afecta al servidor.

Para comprobar cómo ha quedado:

    powercfg /query SCHEME_CURRENT SUB_SLEEP

Dos ajustes más que **sí** piden administrador y conviene revisar si aun así
hay cortes de madrugada:
- Administrador de dispositivos → adaptador de red → Propiedades →
  *Administración de energía* → **desmarcar** «Permitir que el equipo apague
  este dispositivo para ahorrar energía».
- Si el PC está en dominio, comprobar que ninguna directiva de grupo repone el
  plan de energía (la protección de la app sigue valiendo aunque eso pase).

---

## Comprobación
Desde **OTRO** PC de la red, abrir en el navegador:

    http://IP-DEL-SERVIDOR:5001/health

Debe responder algo como `{"status": "ok", ...}`.

---

## Icono en el escritorio / barra de tareas (opcional)

La app trae icono propio (COJOsw). Cómo dejarlo bien depende del equipo:

**En el PC servidor** (o en cualquiera que entre por `http://localhost:5001`):
1. Abrir Edge o Chrome y entrar en `http://localhost:5001`.
2. Menú `⋮` → **Aplicaciones** → *Instalar este sitio como una aplicación*
   (en Chrome: `⋮` → *Emitir, guardar y compartir* → *Instalar página como aplicación*).
3. **Dejar el nombre que propone (`COJOsw`)** y aceptar anclar a la barra de tareas.

A partir de ahí `run.bat` detecta ese acceso directo y abre la app instalada en
vez del navegador, así que la barra de tareas muestra el icono de COJOsw. Si se
le cambia el nombre al instalarla, `run.bat` no la encontrará y volverá a abrir
el navegador en modo ventana (que funciona igual, pero con el icono del
navegador).

**En los PCs cliente** (entran por `http://IP-DEL-SERVIDOR:5001`): el navegador
**no ofrece instalar**, porque solo lo permite sobre HTTPS o `localhost`. El
equivalente es `⋮` → *Guardar y compartir* → **Crear acceso directo…** y marcar
**"Abrir como ventana"**. Mismo resultado visual: icono propio y ventana sin
barra de direcciones.

Para accesos directos creados a mano está `static\img\cojosw.ico` (icono de
Windows multi-tamaño): botón derecho en el acceso directo → Propiedades →
Cambiar icono → examinar hasta ese archivo.

---

## Notas
- La app **no requiere permisos de administrador** (sí se necesitan para abrir
  el puerto del firewall).
- **Backup** = copiar el archivo `data\engastado.db` (se puede copiar en caliente).
- **Git NO es necesario** para funcionar (solo para actualizaciones automáticas).
- La app sirve en `0.0.0.0:5001`, por eso es accesible desde toda la red local.

---

## Contenido del paquete de entrega
- Carpeta `APP-ENGASTADO-SQL` (con `data\engastado.db` y `.env`, sin `venv\`).
- Carpeta `paquete_offline` con:
  - `python-3.13.14-amd64.exe` (instalador offline de Python 3.13, 64 bits).
  - `wheels\` (dependencias para instalación sin internet).
  - `INSTALAR_OFFLINE.bat` (instalador automático sin internet).
