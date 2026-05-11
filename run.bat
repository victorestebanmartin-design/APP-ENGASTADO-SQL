@echo off
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
start "" "http://localhost:5001"

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
