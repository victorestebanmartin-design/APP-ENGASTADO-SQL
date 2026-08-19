@echo off
setlocal enabledelayedexpansion
title ENGASTADO SQL - Servidor
cd /d "%~dp0"

REM ── 0) Relanzarse MINIMIZADO ───────────────────────────────────────────
REM Arranca solo al encender el PC, asi que la ventana no debe estorbar en
REM medio de la pantalla. Minimizada (no oculta) sigue estando en la barra de
REM tareas: si algo peta se puede abrir y ver que dice.
REM El argumento MINIMIZADO evita que se relance en bucle infinito.
if /i not "%~1"=="MINIMIZADO" (
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
timeout /t 2 /nobreak >nul

REM ── 1) App instalada (PWA), si la hay ──────────────────────────────────
REM Si la app se instalo desde el navegador ("Instalar este sitio como una
REM aplicacion"), Windows creo un acceso directo propio. Lanzarlo es lo unico
REM que da icono COJOsw en la BARRA DE TAREAS: el modo --app= de mas abajo
REM abre la ventana sin barra de direcciones, pero al no ser una app
REM registrada Windows la agrupa bajo el navegador y usa su icono.
set APP_LNK=

if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs" (
    for /r "%APPDATA%\Microsoft\Windows\Start Menu\Programs" %%F in (COJOsw*.lnk) do (
        if "!APP_LNK!"=="" set APP_LNK=%%F
    )
)

if "!APP_LNK!"=="" if exist "%USERPROFILE%\Desktop" (
    for /r "%USERPROFILE%\Desktop" %%F in (COJOsw*.lnk) do (
        if "!APP_LNK!"=="" set APP_LNK=%%F
    )
)

if not "!APP_LNK!"=="" (
    echo  Abriendo la app instalada COJOsw ...
    start "" "!APP_LNK!"
    goto :SERVIDOR
)

REM ── 2) Sin app instalada: modo "app" del navegador ─────────────────────
REM Si hay Chrome o Edge, se abre en una ventana sin barra de direcciones ni
REM pestanas (--app=), para que parezca una aplicacion en vez de una pagina
REM web. Si no se encuentra ninguno, se abre en el navegador normal.
REM El icono de la barra de tareas sera el del navegador: para tener el de
REM COJOsw hay que instalar la app una vez (ver arriba).
set NAVEGADOR_APP=

for %%P in (
    "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    "%LocalAppData%\Google\Chrome\Application\chrome.exe"
) do (
    if exist %%P if "!NAVEGADOR_APP!"=="" set NAVEGADOR_APP=%%~P
)

if "%NAVEGADOR_APP%"=="" (
    for %%P in (
        "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
        "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
    ) do (
        if exist %%P if "!NAVEGADOR_APP!"=="" set NAVEGADOR_APP=%%~P
    )
)

if not "%NAVEGADOR_APP%"=="" (
    start "" "%NAVEGADOR_APP%" --app="http://localhost:5001"
) else (
    start "" "http://localhost:5001"
)

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

echo. >> "!LOG!" 2>nul
echo  -- El servidor se ha detenido (codigo: !EXIT_CODE!) -- >> "!LOG!" 2>nul

echo.
echo El servidor se ha detenido (codigo: !EXIT_CODE!).
echo.
echo Los detalles del fallo estan en:
echo   !LOG!
echo.
pause
