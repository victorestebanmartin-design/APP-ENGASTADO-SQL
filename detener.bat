@echo off
setlocal enabledelayedexpansion
title ENGASTADO SQL - Detener servidor
cd /d "%~dp0"

REM Apaga el servidor "a mano", para cuando la web ya no responde y no hay
REM ventana de consola que cerrar (arranque con ARRANCAR.vbs).
REM La forma normal de apagarlo es Admin -> Sistema -> Apagar servidor.

echo ================================================================================
echo  DETENER EL SERVIDOR DE ENGASTADO
echo ================================================================================
echo.
echo  AVISO: la app dejara de estar disponible para TODOS los puestos de la nave.
echo.

set PIDFILE=data\server.pid
if not exist "%PIDFILE%" (
    echo  No hay ningun servidor en marcha ^(no existe %PIDFILE%^).
    echo  Si crees que si lo hay, buscalo en el Administrador de tareas: python.exe
    echo.
    pause
    exit /b 1
)

set PID=
for /f "usebackq tokens=*" %%i in ("%PIDFILE%") do set PID=%%i

if "!PID!"=="" (
    echo  El fichero %PIDFILE% esta vacio o ilegible.
    echo.
    pause
    exit /b 1
)

echo  Servidor encontrado: PID !PID!
echo.
choice /c SN /n /m "  Detenerlo ahora? [S/N] "
if errorlevel 2 (
    echo.
    echo  Cancelado. El servidor sigue en marcha.
    echo.
    pause
    exit /b 0
)

echo.
REM /T mata tambien al cmd.exe que lo lanzo (el run.bat oculto), para que no
REM se quede un proceso invisible por ahi.
taskkill /PID !PID! /T /F
if errorlevel 1 (
    echo.
    echo  No se ha podido detener el proceso !PID!.
    echo  Puede que ya no existiera: borra %PIDFILE% y vuelve a intentarlo.
    echo.
    pause
    exit /b 1
)

del "%PIDFILE%" 2>nul

echo.
echo  Servidor detenido.
echo  Para arrancarlo otra vez: ARRANCAR.vbs ^(o run.bat si quieres ver la consola^).
echo.
pause
