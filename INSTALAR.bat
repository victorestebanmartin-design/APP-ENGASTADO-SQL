@echo off
title ENGASTADO SQL - Instalacion inicial
cd /d "%~dp0"

echo ================================================================================
echo  INSTALACION - SISTEMA DE ENGASTADO AUTOMATICO
echo  https://github.com/victorestebanmartin-design/APP-ENGASTADO-SQL
echo ================================================================================
echo.

REM -----------------------------------------------------------------------
REM 1. Comprobar Python
REM -----------------------------------------------------------------------
echo [1/4] Comprobando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo  Descargalo desde: https://www.python.org/downloads/
    echo  IMPORTANTE: durante la instalacion marca la opcion "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   Encontrado: %%v
echo.

REM -----------------------------------------------------------------------
REM 2. Comprobar Git
REM -----------------------------------------------------------------------
echo [2/4] Comprobando Git...

set GIT_EXE=
where git >nul 2>&1
if %errorlevel% equ 0 (
    set GIT_EXE=git
) else (
    REM Buscar el git de GitHub Desktop
    for /d %%d in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
        if exist "%%d\resources\app\git\cmd\git.exe" (
            set GIT_EXE=%%d\resources\app\git\cmd\git.exe
        )
    )
    REM Git for Windows en rutas estandar
    if exist "C:\Program Files\Git\cmd\git.exe" set GIT_EXE=C:\Program Files\Git\cmd\git.exe
    if exist "C:\Program Files (x86)\Git\cmd\git.exe" set GIT_EXE=C:\Program Files (x86)\Git\cmd\git.exe
)

if "%GIT_EXE%"=="" (
    echo.
    echo  [ERROR] Git no esta instalado.
    echo.
    echo  Descargalo desde: https://git-scm.com/download/win
    echo  La instalacion por defecto es suficiente.
    echo.
    pause
    exit /b 1
)
echo   Encontrado: %GIT_EXE%
echo.

REM -----------------------------------------------------------------------
REM 3. Crear entorno virtual e instalar dependencias
REM -----------------------------------------------------------------------
echo [3/4] Creando entorno virtual e instalando dependencias...

if not exist "venv\" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo   Entorno virtual creado.
) else (
    echo   Entorno virtual ya existe, omitiendo creacion.
)

call venv\Scripts\activate.bat
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo  [ERROR] Fallo al instalar dependencias.
    pause
    exit /b 1
)
echo   Dependencias instaladas correctamente.
echo.

REM -----------------------------------------------------------------------
REM 4. Base de datos
REM -----------------------------------------------------------------------
echo [4/4] Comprobando base de datos...

if exist "data\engastado.db" (
    echo   Base de datos encontrada: data\engastado.db
) else (
    echo   No se encontro base de datos.
    echo.
    echo   OPCIONES:
    echo   A) Copia el archivo data\engastado.db desde el PC principal
    echo      a esta carpeta y vuelve a ejecutar run.bat
    echo.
    echo   B) Si es una instalacion nueva sin datos previos, run.bat
    echo      creara una base de datos vacia automaticamente.
    echo.
)

echo.
echo ================================================================================
echo  Instalacion completada correctamente.
echo.
echo  Siguiente paso:
if not exist "data\engastado.db" (
    echo   1. Copia data\engastado.db desde el PC principal ^(opcional^)
    echo   2. Ejecuta run.bat para arrancar el servidor
) else (
    echo   Ejecuta run.bat para arrancar el servidor
)
echo.
echo  Para futuras actualizaciones usa: ACTUALIZAR.bat
echo ================================================================================
echo.
pause
