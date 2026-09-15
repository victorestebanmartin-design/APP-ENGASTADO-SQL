@echo off
setlocal enabledelayedexpansion

REM Abre COJOsw en la mejor ventana disponible. Lo usan run.bat (modo visible)
REM y ARRANCAR.vbs (el icono del escritorio), para que la app se abra siempre
REM igual se haya arrancado el servidor como se haya arrancado.

if "%~1"=="" (set URL=http://localhost:5001) else (set URL=%~1)

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
    start "" "!APP_LNK!"
    exit /b 0
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

if "!NAVEGADOR_APP!"=="" (
    for %%P in (
        "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
        "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
    ) do (
        if exist %%P if "!NAVEGADOR_APP!"=="" set NAVEGADOR_APP=%%~P
    )
)

if not "!NAVEGADOR_APP!"=="" (
    start "" "!NAVEGADOR_APP!" --app="!URL!"
) else (
    start "" "!URL!"
)

exit /b 0
