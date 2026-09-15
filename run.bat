@echo off
setlocal enabledelayedexpansion
title ENGASTADO SQL - Servidor
cd /d "%~dp0"

REM ── 0) Relanzarse MINIMIZADO ───────────────────────────────────────────
REM Arranca solo al encender el PC, asi que la ventana no debe estorbar en
REM medio de la pantalla. Minimizada (no oculta) sigue estando en la barra de
REM tareas: si algo peta se puede abrir y ver que dice.
REM El argumento MINIMIZADO evita que se relance en bucle infinito.
REM
REM SILENCIOSO lo pone ARRANCAR.vbs, que ya ha lanzado esto SIN ventana:
REM no hay que relanzar nada, y al terminar no se puede dejar la consola
REM esperando una tecla porque no hay ventana donde pulsarla.
set MODO=%~1
if /i not "!MODO!"=="MINIMIZADO" if /i not "!MODO!"=="SILENCIOSO" (
    start /min "" "%~f0" MINIMIZADO
    exit /b
)

REM ── 0.1) Carpeta de logs ───────────────────────────────────────────────
if not exist "logs" mkdir "logs"

REM Marca de tiempo ORDENABLE para el nombre del log. Se pide a PowerShell a
REM proposito: %DATE% y %TIME% cambian de formato segun la configuracion
REM regional de Windows (dd/MM vs MM/dd, ':' vs '.'), y acaban generando
REM nombres invalidos o imposibles de ordenar.
set TS=
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss" 2^>nul') do set TS=%%i
if "!TS!"=="" set TS=sin-fecha_%RANDOM%

set "LOG=%~dp0logs\servidor_!TS!.log"

REM ── 0.2) Salida en UTF-8 ───────────────────────────────────────────────
REM La salida de la app va a un fichero (ver mas abajo), no a la consola, y
REM entonces Python usa la codificacion regional de Windows (cp1252) para
REM stdout. Un solo emoji en un print lanza UnicodeEncodeError y tumba la
REM peticion que lo estuviera imprimiendo. Con esto el proceso entero -
REM incluidos los avisos de arranque y los traceback - habla UTF-8.
set PYTHONIOENCODING=utf-8

REM La ventana de la app la abre el propio servidor (arranque_local.py), en
REM cuanto acepta conexiones. Antes se abria aqui a los 2 segundos y a veces
REM llegaba antes que el servidor: "no se puede acceder a este sitio" nada mas
REM arrancar. Si ya hay otro servidor en marcha, el que sobra abre la app y se
REM aparta sin tocar nada.
set COJOSW_ABRIR_APP=1

REM Activar entorno virtual
call venv\Scripts\activate.bat

:INICIO
cls
echo ================================================================================
echo  SISTEMA DE ENGASTADO AUTOMATICO - SQLite V2.0
echo  (Watchdog activo - reinicio automatico habilitado)
echo ================================================================================
echo.
echo  Registro de esta sesion:
echo    !LOG!
echo.
echo  Abriendo COJOsw en http://localhost:5001 ...

:SERVIDOR
REM Todo lo que escupa la app (stdout y stderr) va al log de esta sesion, no
REM a una consola que nadie esta mirando. Se abre en modo AÑADIR (>>) para
REM que un reinicio por OTA no borre lo que fallo justo antes: el motivo del
REM problema suele estar en las lineas anteriores al reinicio.
echo. >> "!LOG!" 2>nul
echo ================================================================================ >> "!LOG!" 2>nul
echo  Arranque del servidor >> "!LOG!" 2>nul
echo ================================================================================ >> "!LOG!" 2>nul

python run_sql.py >> "!LOG!" 2>&1
set EXIT_CODE=!errorlevel!

REM Codigo 42 = reinicio solicitado por actualizacion OTA
if !EXIT_CODE! == 42 (
    echo. >> "!LOG!" 2>nul
    echo  -- Reinicio solicitado por actualizacion OTA -- >> "!LOG!" 2>nul
    echo.
    echo  Reiniciando servidor tras actualizacion...
    timeout /t 2 /nobreak >nul
    goto INICIO
)

REM Codigo 44 = ya habia un servidor en marcha y este arranque sobraba (se
REM ha pulsado el icono con la app ya funcionando). La ventana de la app ya
REM se ha abierto contra el servidor bueno: aqui no hay nada que hacer.
if !EXIT_CODE! == 44 (
    echo. >> "!LOG!" 2>nul
    echo  -- Ya habia un servidor en marcha: este arranque sobraba -- >> "!LOG!" 2>nul
    exit /b 0
)

REM Codigo 43 = apagado pedido por un admin desde la web (Admin -> Sistema).
REM No es un fallo: ni se relanza ni se queda nadie esperando una tecla.
if !EXIT_CODE! == 43 (
    echo. >> "!LOG!" 2>nul
    echo  -- Apagado solicitado desde el panel de administracion -- >> "!LOG!" 2>nul
    echo.
    echo  El servidor se ha apagado desde la web.
    timeout /t 3 /nobreak >nul
    exit /b 0
)

echo. >> "!LOG!" 2>nul
echo  -- El servidor se ha detenido (codigo: !EXIT_CODE!) -- >> "!LOG!" 2>nul

echo.
echo El servidor se ha detenido (codigo: !EXIT_CODE!).
echo.
echo Los detalles del fallo estan en:
echo   !LOG!
echo.

REM Sin ventana no hay tecla que pulsar: un `pause` aqui dejaria un cmd.exe
REM invisible colgado para siempre. El motivo del fallo queda en el log.
if /i "!MODO!"=="SILENCIOSO" exit /b !EXIT_CODE!

pause
