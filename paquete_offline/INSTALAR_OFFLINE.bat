@echo off
title ENGASTADO SQL - Instalacion OFFLINE (sin internet)
cd /d "%~dp0.."

echo ================================================================================
echo  INSTALACION OFFLINE - SISTEMA DE ENGASTADO AUTOMATICO
echo  (No requiere conexion a internet)
echo ================================================================================
echo.

set PYINSTALLER=paquete_offline\python-3.13.14-amd64.exe

REM -----------------------------------------------------------------------
REM 1. Comprobar / instalar Python 3.13
REM -----------------------------------------------------------------------
echo [1/3] Comprobando Python...
python --version 2>nul | findstr /c:"3.13" >nul
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   Encontrado: %%v
) else (
    echo   Python 3.13 no encontrado. Lanzando instalador offline...
    if not exist "%PYINSTALLER%" (
        echo  [ERROR] No se encuentra %PYINSTALLER%
        echo  Asegurate de copiar la carpeta paquete_offline completa.
        pause
        exit /b 1
    )
    "%PYINSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1
    echo.
    echo   Python instalado. IMPORTANTE: cierra esta ventana y vuelve a
    echo   ejecutar INSTALAR_OFFLINE.bat para que el PATH quede actualizado.
    pause
    exit /b 0
)
echo.

REM -----------------------------------------------------------------------
REM 2. Entorno virtual + dependencias (desde wheels locales)
REM -----------------------------------------------------------------------
echo [2/3] Creando entorno virtual e instalando dependencias offline...

if not exist "venv\" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
pip install --no-index --find-links paquete_offline\wheels -r requirements.txt
if %errorlevel% neq 0 (
    echo  [ERROR] Fallo al instalar dependencias desde los wheels locales.
    pause
    exit /b 1
)
echo   Dependencias instaladas (sin internet).
echo.

REM -----------------------------------------------------------------------
REM 3. Base de datos
REM -----------------------------------------------------------------------
echo [3/3] Comprobando base de datos...
if exist "data\engastado.db" (
    echo   Base de datos encontrada.
) else (
    echo   No hay base de datos. Copia data\engastado.db del PC principal
    echo   o ejecuta run.bat para crear una vacia.
)

echo.
echo ================================================================================
echo  Instalacion OFFLINE completada. Ejecuta run.bat para arrancar.
echo ================================================================================
echo.
pause
