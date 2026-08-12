@echo off
setlocal enabledelayedexpansion
title ENGASTADO SQL - Servidor
cd /d "%~dp0"

REM Activar entorno virtual
call venv\Scripts\activate.bat

:INICIO
cls
echo ================================================================================
echo  SISTEMA DE ENGASTADO AUTOMATICO - SQLite V2.0
echo  (Watchdog activo - reinicio automatico habilitado)
echo ================================================================================
echo.
echo  Abriendo navegador en http://localhost:5001 ...
timeout /t 2 /nobreak >nul

REM Modo "app": si hay Chrome o Edge, se abre en una ventana sin barra de
REM direcciones ni pestanas (--app=), para que parezca una aplicacion en vez
REM de una pagina web. Si no se encuentra ninguno, se abre en el navegador
REM normal como hasta ahora.
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

python run_sql.py
set EXIT_CODE=%errorlevel%

REM Codigo 42 = reinicio solicitado por actualizacion OTA
if %EXIT_CODE% == 42 (
    echo.
    echo  Reiniciando servidor tras actualizacion...
    timeout /t 2 /nobreak >nul
    goto INICIO
)

echo.
echo El servidor se ha detenido (codigo: %EXIT_CODE%).
pause
