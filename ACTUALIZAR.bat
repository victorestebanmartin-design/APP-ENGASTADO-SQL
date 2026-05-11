@echo off
title ENGASTADO - Actualizar desde GitHub
cd /d "%~dp0"

echo ================================================================================
echo  ACTUALIZACION AUTOMATICA - APP ENGASTADO SQL
echo  Repositorio: https://github.com/victorestebanmartin-design/APP-ENGASTADO-SQL
echo ================================================================================
echo.

REM Comprobar que git esta instalado
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git no esta instalado o no esta en el PATH.
    echo Descargalo desde: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM Mostrar version actual
echo [1/4] Version actual:
git log -1 --format="  Commit: %%h  Fecha: %%ci  %%s"
echo.

REM Descargar cambios
echo [2/4] Descargando cambios desde GitHub...
git fetch origin main
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo conectar con GitHub. Comprueba la conexion.
    pause
    exit /b 1
)

REM Comprobar si hay cambios
git diff --quiet HEAD origin/main
if %errorlevel% equ 0 (
    echo.
    echo  Ya tienes la version mas reciente. No hay cambios nuevos.
    echo.
    pause
    exit /b 0
)

REM Mostrar que cambia
echo.
echo  Cambios disponibles:
git log HEAD..origin/main --oneline --format="  + %%s (%%cr)"
echo.

REM Confirmar
set /p CONFIRMAR=  Aplicar actualizacion? (S/N): 
if /i "%CONFIRMAR%" neq "S" (
    echo  Actualizacion cancelada.
    pause
    exit /b 0
)

REM Aplicar cambios (preservar data/ que tiene la BD y archivos locales)
echo.
echo [3/4] Aplicando cambios...
git pull origin main
if %errorlevel% neq 0 (
    echo [ERROR] Fallo al aplicar los cambios.
    pause
    exit /b 1
)

REM Actualizar dependencias si requirements.txt cambio
echo.
echo [4/4] Comprobando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt -q --exists-action i
echo.

echo ================================================================================
echo  Actualizacion completada correctamente.
echo  Version instalada:
git log -1 --format="  Commit: %%h  Fecha: %%ci  %%s"
echo.
echo  Reinicia el servidor (run.bat) para aplicar los cambios.
echo ================================================================================
echo.
pause
