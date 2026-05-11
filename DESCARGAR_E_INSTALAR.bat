@echo off
title ENGASTADO SQL - Descarga e instalacion completa
echo ================================================================================
echo  DESCARGA E INSTALACION - SISTEMA DE ENGASTADO AUTOMATICO
echo  Repositorio: https://github.com/victorestebanmartin-design/APP-ENGASTADO-SQL
echo ================================================================================
echo.

REM -----------------------------------------------------------------------
REM 1. Comprobar Python
REM -----------------------------------------------------------------------
echo [1/5] Comprobando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python no esta instalado o no esta en el PATH.
    echo  Descargalo desde: https://www.python.org/downloads/
    echo  IMPORTANTE: marca "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   Encontrado: %%v
echo.

REM -----------------------------------------------------------------------
REM 2. Comprobar Git
REM -----------------------------------------------------------------------
echo [2/5] Buscando Git...

set GIT_EXE=
where git >nul 2>&1
if %errorlevel% equ 0 ( set GIT_EXE=git ) else (
    for /d %%d in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
        if exist "%%d\resources\app\git\cmd\git.exe" set GIT_EXE=%%d\resources\app\git\cmd\git.exe
    )
    if exist "C:\Program Files\Git\cmd\git.exe"      set GIT_EXE=C:\Program Files\Git\cmd\git.exe
    if exist "C:\Program Files (x86)\Git\cmd\git.exe" set GIT_EXE=C:\Program Files (x86)\Git\cmd\git.exe
)

if "%GIT_EXE%"=="" (
    echo.
    echo  [ERROR] Git no esta instalado.
    echo  Descargalo desde: https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)
echo   Encontrado: %GIT_EXE%
echo.

REM -----------------------------------------------------------------------
REM 3. Elegir carpeta de instalacion
REM -----------------------------------------------------------------------
echo [3/5] Ubicacion de instalacion
echo.
echo  Donde quieres instalar la aplicacion?
echo  (Deja en blanco para usar C:\ENGASTADO)
echo.
set /p DESTINO=  Carpeta de destino: 
if "%DESTINO%"=="" set DESTINO=C:\ENGASTADO

echo.
echo   Se instalara en: %DESTINO%
set /p CONFIRMAR=  Confirmar? (S/N): 
if /i "%CONFIRMAR%" neq "S" (
    echo  Instalacion cancelada.
    pause
    exit /b 0
)

REM -----------------------------------------------------------------------
REM 4. Clonar repositorio
REM -----------------------------------------------------------------------
echo.
echo [4/5] Descargando aplicacion desde GitHub...

if exist "%DESTINO%\" (
    echo  La carpeta ya existe. Actualizando en lugar de clonar...
    cd /d "%DESTINO%"
    "%GIT_EXE%" pull origin main
) else (
    "%GIT_EXE%" clone https://github.com/victorestebanmartin-design/APP-ENGASTADO-SQL "%DESTINO%"
    if %errorlevel% neq 0 (
        echo  [ERROR] No se pudo descargar la aplicacion. Comprueba la conexion a internet.
        pause
        exit /b 1
    )
    cd /d "%DESTINO%"
)
echo   Descarga completada.
echo.

REM -----------------------------------------------------------------------
REM 5. Entorno virtual y dependencias
REM -----------------------------------------------------------------------
echo [5/5] Instalando dependencias...

if not exist "venv\" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo  [ERROR] Fallo al instalar dependencias.
    pause
    exit /b 1
)
echo   Dependencias instaladas.

REM -----------------------------------------------------------------------
REM Fin
REM -----------------------------------------------------------------------
echo.
echo ================================================================================
echo  Instalacion completada en: %DESTINO%
echo.
if not exist "data\engastado.db" (
    echo  IMPORTANTE: Copia el archivo data\engastado.db desde el PC principal
    echo  a la carpeta: %DESTINO%\data\
    echo.
)
echo  Para arrancar la aplicacion: abre %DESTINO%\run.bat
echo  Para futuras actualizaciones usa el panel de Admin o ACTUALIZAR.bat
echo ================================================================================
echo.

set /p ARRANCAR=  Arrancar la aplicacion ahora? (S/N): 
if /i "%ARRANCAR%"=="S" (
    start "" "%DESTINO%\run.bat"
)
pause
