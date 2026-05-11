# ⚠️ PROBLEMA DETECTADO: Políticas de Grupo

**Fecha:** 16 de febrero de 2026

---

## 🚨 Situación

Detectamos **2 problemas** en tu entorno:

### 1. ❌ Sin permisos de administrador
- No puedes instalar SQL Server
- **Solución:** ✅ Usar SQLite (ya implementado)

### 2. ❌ Políticas de grupo bloquean pip.exe
- Error: "La directiva de grupo bloquea a este programa"
- No puedes ejecutar: `pip install ...`
- **Problema:** Entorno corporativo con restricciones altas

---

## 🔍 Verificar restricciones

```powershell
# 1. Verificar si tienes permisos admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host "Admin: $isAdmin"  # False ❌

# 2. Verificar políticas de grupo de Python
python -m pip --version  # ¿Funciona?
pip --version            # ¿Funciona?

# 3. Verificar política AppLocker
Get-AppLockerPolicy -Effective | Select-Object -ExpandProperty RuleCollections
```

---

## 🎯 Opciones disponibles

### Opción 1: Usar Python del sistema (si tiene las librerías)

```powershell
# Verificar qué tienes instalado en Python del sistema
python -c "import flask; print('Flask:', flask.__version__)"
python -c "import sqlalchemy; print('SQLAlchemy:', sqlalchemy.__version__)"
python -c "import pandas; print('Pandas:', pandas.__version__)"
```

Si **todas las librerías necesarias** ya están en el Python del sistema → ✅ Puedes usar ese Python directamente sin venv.

### Opción 2: Instalar con `python -m pip` (puede funcionar)

A veces las políticas bloquean `pip.exe` pero no `python -m pip`:

```powershell
cd C:\Users\estebanv\APP-ENGASTADO-SQL
python -m pip install --user Flask SQLAlchemy pandas openpyxl
```

**Nota:** `--user` instala en tu perfil de usuario, no requiere admin.

### Opción 3: Instalar manualmente (wheel files)

Descargar archivos `.whl` y instalarlos offline:

```powershell
# 1. Descargar wheels desde https://pypi.org/
# 2. Instalar local:
python -m pip install --user Flask-3.1.0-py3-none-any.whl
python -m pip install --user SQLAlchemy-2.0.25-py3-none-any.whl
# ... etc
```

### Opción 4: Python portable (sin instalación)

Descargar Python portable que no requiere instalación:
- https://www.python.org/ftp/python/3.11.0/python-3.11.0-embed-amd64.zip
- Descomprimir en carpeta de usuario
- Instalar pip manualmente

### Opción 5: **SOLICITAR A IT** (Recomendado)

Pedir a tu departamento IT que:
1. Te den permisos de administrador (temporal o permanente), O
2. Instalen SQL Server Express para ti, O
3. Desbloqueen políticas de pip/Python para tu usuario, O
4. Instalen las dependencias necesarias globalmente

### Opción 6: Usar el Python del proyecto viejo

Si el proyecto viejo (`PROYECTO-ENGASTADO1git`) ya tiene un entorno virtual con las librerías:

```powershell
# Usar ese Python:
C:\Users\estebanv\PROYECTO-ENGASTADO1git\.venv\Scripts\python.exe --version

# Probar instalar solo lo que falta (SQLAlchemy):
C:\Users\estebanv\PROYECTO-ENGASTADO1git\.venv\Scripts\python.exe -m pip install --user SQLAlchemy
```

---

## 📋 Diagnóstico completo

Ejecuta esto para saber qué opciones tienes:

```powershell
# Guardar en: diagnostico_completo.ps1

Write-Host "=== DIAGNÓSTICO COMPLETO ===" -ForegroundColor Cyan

# 1. Permisos admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host "`n1. Admin: $isAdmin" -ForegroundColor $(if ($isAdmin) {'Green'} else {'Red'})

# 2. Python
Write-Host "`n2. Python:" -ForegroundColor Yellow
python --version
$pythonPath = (Get-Command python).Source
Write-Host "   Ubicación: $pythonPath"

# 3. pip (multiple tests)
Write-Host "`n3. pip:" -ForegroundColor Yellow
try {
    pip --version 2>&1 | Write-Host
    Write-Host "   ✅ pip.exe funciona" -ForegroundColor Green
} catch {
    Write-Host "   ❌ pip.exe bloqueado" -ForegroundColor Red
}

try {
    python -m pip --version 2>&1 | Write-Host
    Write-Host "   ✅ python -m pip funciona" -ForegroundColor Green
} catch {
    Write-Host "   ❌ python -m pip bloqueado" -ForegroundColor Red
}

# 4. Librerías existentes
Write-Host "`n4. Librerías Python instaladas:" -ForegroundColor Yellow
$libs = @('flask', 'sqlalchemy', 'pandas', 'openpyxl', 'werkzeug', 'jinja2')
foreach ($lib in $libs) {
    try {
        $version = & python -c "import $lib; print($lib.__version__)" 2>$null
        if ($version) {
            Write-Host "   ✅ $lib : $version" -ForegroundColor Green
        } else {
            Write-Host "   ❌ $lib : NO instalado" -ForegroundColor Red
        }
    } catch {
        Write-Host "   ❌ $lib : NO instalado" -ForegroundColor Red
    }
}

# 5. SQLite
Write-Host "`n5. SQLite:" -ForegroundColor Yellow
$sqliteVersion = python -c "import sqlite3; print(sqlite3.sqlite_version)" 2>$null
Write-Host "   ✅ Version: $sqliteVersion" -ForegroundColor Green

# 6. Proyecto viejo
Write-Host "`n6. Proyecto viejo:" -ForegroundColor Yellow
if (Test-Path "C:\Users\estebanv\PROYECTO-ENGASTADO1git\.venv") {
    Write-Host "   ✅ Tiene venv" -ForegroundColor Green
    $oldPython = "C:\Users\estebanv\PROYECTO-ENGASTADO1git\.venv\Scripts\python.exe"
    & $oldPython --version 2>&1 | Write-Host
} else {
    Write-Host "   ❌ No tiene venv" -ForegroundColor Red
}

Write-Host "`n=== FIN DIAGNÓSTICO ===" -ForegroundColor Cyan
Write-Host "`nRecomendación: Revisar qué opciones tienes disponibles arriba"
```

---

## 🎯 Decisión: ¿Qué hacer AHORA?

### Escenario A: Python del sistema tiene las librerías
→ **Usar Python global sin venv**
```powershell
cd C:\Users\estebanv\APP-ENGASTADO-SQL
python run_sql.py  # Directo
```

### Escenario B: `python -m pip` funciona
→ **Instalar dependencias con --user**
```powershell
python -m pip install --user -r requirements.txt
python run_sql.py
```

### Escenario C: Usar venv del proyecto viejo
→ **Extender ese venv**
```powershell
C:\Users\estebanv\PROYECTO-ENGASTADO1git\.venv\Scripts\activate
pip install SQLAlchemy  # Solo lo que falta
cd C:\Users\estebanv\APP-ENGASTADO-SQL
python run_sql.py
```

### Escenario D: TODO bloqueado
→ **Solicitar a IT o esperar permisos**
- Mientras tanto, seguir con sistema JSON viejo
- Documentar requisitos para IT
- Solicitar formalmente permisos

---

## 📞 Qué solicitar a IT

**Email/ticket template:**

```
Asunto: Solicitud de permisos para desarrollo Python

Hola equipo IT,

Necesito desarrollar una aplicación Python para mejorar el sistema de 
engastado automático. Actualmente tengo restricciones que bloquean:

1. Permisos de administrador (necesito para SQL Server, alternativamente 
   puedo usar SQLite que no requiere admin)

2. Ejecución de pip.exe (bloqueado por políticas de grupo)

Opciones solicitadas (en orden de preferencia):

A. Desbloquear pip.exe para mi usuario (estebanv)
   - Permitir: python.exe -m pip con flag --user

B. Instalar globalmente estas librerías Python:
   - Flask==3.1.0
   - SQLAlchemy==2.0.25
   - pandas==2.2.3
   - openpyxl==3.1.5
   - werkzeug, jinja2, numpy, python-dateutil

C. Permisos de administrador temporal para auto-gestionar

Justificación: Sistema actual (JSON) tiene problemas de concurrencia 
con 4-10 usuarios simultáneos, necesitamos migrar a base de datos.

Gracias,
[Tu nombre]
```

---

## ✅ Mientras tanto...

El **sistema viejo JSON** sigue funcionando. Puedes:
1. Seguir usándolo en producción
2. Documentar los problemas de concurrencia
3. Presionar para conseguir permisos
4. Preparar el código de la migración (sin ejecutar aún)

---

**Próximo paso:** Ejecuta el script de diagnóstico y dime qué resultado te da.
