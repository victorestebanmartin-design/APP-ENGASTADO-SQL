@echo off
title ENGASTADO SQL - Servidor
cd /d "%~dp0"

echo ================================================================================
echo  SISTEMA DE ENGASTADO AUTOMATICO - SQLite V2.0
echo ================================================================================
echo.

REM Activar entorno virtual
call venv\Scripts\activate.bat

REM Arrancar la app
python run_sql.py

echo.
echo El servidor se ha detenido.
pause
