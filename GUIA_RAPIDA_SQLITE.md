# 🚀 GUÍA RÁPIDA - SQLite (SIN PERMISOS ADMIN)

**Fecha:** 16 de febrero de 2026  
**Situación:** No tienes permisos de administrador para instalar SQL Server  
**Solución:** Usar SQLite (incluido en Python, sin instalación)

---

## ✅ Por qué SQLite es viable para tu caso

### Ventajas
- ✅ **Sin instalación:** Viene con Python
- ✅ **Sin permisos admin:** Archivo de base de datos local
- ✅ **Concurrencia aceptable:** WAL mode soporta múltiples lectores + 1 escritor
- ✅ **Funciona AHORA:** 5 minutos para estar operativo
- ✅ **Portabilidad:** Un solo archivo `data/engastado.db`

### Limitaciones conocidas
- ⚠️ **Escrituras concurrentes:** Solo 1 escritor a la vez (los demás esperan con timeout de 30seg)
- ⚠️ **Performance:** Más lento que SQL Server en queries complejos
- ⚠️ **Sin usuarios/permisos SQL:** Seguridad por filesystem
- ⚠️ **Respaldo manual:** Backup = copiar archivo .db

### Veredicto para 4-10 usuarios
**✅ VIABLE** con las siguientes consideraciones:
- Si las escrituras son cortas (< 1 segundo) → WAL mode maneja bien la cola
- Si hay picos de escritura simultánea → pueden haber bloqueos temporales (retry automático)
- Monitorear timeouts y errores de "database is locked"

---

## 🚀 Instalación en 5 minutos

### Paso 1: Crear entorno virtual (2 min)

```powershell
cd C:\Users\estebanv\APP-ENGASTADO-SQL
python -m venv venv
.\venv\Scripts\activate
```

### Paso 2: Instalar dependencias (2 min)

```powershell
pip install -r requirements.txt
```

**Nota:** pyodbc NO está en requirements ahora (SQLite viene con Python)

### Paso 3: Arrancar aplicación (1 min)

```powershell
python run_sql.py
```

**La base de datos se crea automáticamente** desde `schema_sqlite.sql` si no existe.

### Paso 4: Verificar (30 seg)

Abrir navegador:
```
http://localhost:5001/health
```

Deberías ver:
```json
{
  "status": "ok",
  "database": "connected",
  "db_type": "SQLite",
  "sqlite_version": "3.x.x",
  "db_path": "C:\\Users\\estebanv\\APP-ENGASTADO-SQL\\data\\engastado.db"
}
```

---

## 📊 Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `schema_sqlite.sql` | ✅ Nuevo - Schema adaptado a SQLite |
| `config.py` | ✅ Modificado - USA SQLite en vez de SQL Server |
| `requirements.txt` | ✅ Modificado - SIN pyodbc |
| `run_sql.py` | ✅ Modificado - Inicializa SQLite auto |
| `repositories/__init__.py` | ✅ Compatible - SQLAlchemy funciona igual |

---

## 🗄️ Ubicación de la base de datos

```
APP-ENGASTADO-SQL/
└── data/
    └── engastado.db  ← Tu base de datos SQLite
```

**Backup:** Simplemente copiar este archivo
```powershell
Copy-Item data\engastado.db data\engastado_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').db
```

---

## 🔧 Configuración de concurrencia (WAL mode)

El schema ya incluye:
```sql
PRAGMA journal_mode = WAL;  -- Write-Ahead Logging
PRAGMA synchronous = NORMAL; -- Balance performance/seguridad
PRAGMA cache_size = 10000;   -- Cache de 10MB
```

**WAL mode permite:**
- ✅ Múltiples lectores simultáneos (sin límite)
- ✅ 1 escritor simultáneo
- ✅ Lecturas NO bloquean escrituras
- ✅ Escrituras NO bloquean lecturas

**Timeout configurado:**
- 30 segundos en `config.py` → `SQLALCHEMY_ENGINE_OPTIONS`
- Si una escritura tarda > 30seg, falla con "database is locked"

---

## 🧪 Testing de concurrencia

### Probar con 5 usuarios simultáneos:

```powershell
# Abrir 5 terminales PowerShell diferentes y ejecutar:
while ($true) { 
    Invoke-WebRequest http://localhost:5001/health 
    Start-Sleep -Seconds 1
}
```

Si todo funciona bien → ✅ Concurrencia OK

Si ves errores "database is locked" frecuentes → ⚠️ Necesitas optimizar tiempos de transacción

---

## 📋 Migrar datos desde JSON

Cuando implementes `migrate_json_to_sql.py`, funcionará igual:

```powershell
python migrate_json_to_sql.py --dry-run  # Validar
python migrate_json_to_sql.py            # Migrar
```

La diferencia es que inserta en SQLite en vez de SQL Server (mismo código con SQLAlchemy).

---

## 🔄 Migrar a SQL Server después (si consigues permisos)

Si más adelante consigues permisos admin, puedes migrar:

### Opción 1: Exportar/Importar
```powershell
# 1. Exportar desde SQLite a JSON/CSV
python export_sqlite_to_json.py

# 2. Instalar SQL Server
# 3. Ejecutar schema.sql (original SQL Server)
# 4. Importar JSON a SQL Server
python migrate_json_to_sql.py
```

### Opción 2: Usar SQLAlchemy migration tools
- Alembic puede migrar esquemas entre bases
- O simplemente dump data y re-insert

**Código de aplicación NO cambia** (SQLAlchemy es agnóstico a DB)

---

## ⚠️ Limitaciones críticas a tener en cuenta

### 1. Bloqueos de escritura
**Síntoma:** Error "database is locked"  
**Solución:**
- Transacciones cortas (< 1 segundo)
- Retry automático (ya configurado en SQLAlchemy)
- Evitar transacciones largas que bloqueen

### 2. Performance con queries complejos
**Síntoma:** Queries lentos con JOINs grandes  
**Solución:**
- Índices bien definidos (ya en schema_sqlite.sql)
- Limitar resultados (LIMIT)
- Cachear queries frecuentes

### 3. Sin autenticación de usuarios
**Síntoma:** Todos tienen acceso completo al archivo .db  
**Solución:**
- Permisos de filesystem Windows
- Autenticación en capa de aplicación Flask
- No exponer archivo .db públicamente

### 4. Backup manual
**Síntoma:** No hay backup automático como SQL Server  
**Solución:**
- Script de backup diario (ver sección siguiente)
- Comprimir archivo .db

---

## 💾 Script de Backup Automático

```powershell
# Crear archivo: backup_sqlite.ps1

$fecha = Get-Date -Format "yyyyMMdd_HHmmss"
$origen = "C:\Users\estebanv\APP-ENGASTADO-SQL\data\engastado.db"
$destino = "C:\Backups\engastado_$fecha.db"

# Crear carpeta de backups
New-Item -ItemType Directory -Path "C:\Backups" -Force | Out-Null

# Copiar base de datos
Copy-Item $origen $destino

# Comprimir (opcional)
Compress-Archive $destino "$destino.zip" -Force
Remove-Item $destino

Write-Host "✅ Backup creado: $destino.zip"

# Limpiar backups viejos (mantener últimos 7 días)
Get-ChildItem "C:\Backups\engastado_*.zip" | 
    Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-7)} | 
    Remove-Item
```

**Programar tarea diaria:**
```powershell
# Ejecutar PowerShell como usuario normal:
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-File C:\Users\estebanv\APP-ENGASTADO-SQL\backup_sqlite.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
Register-ScheduledTask -TaskName "Backup SQLite Engastado" -Action $action -Trigger $trigger -Description "Backup diario de base de datos SQLite"
```

---

## 🔍 Monitoreo

### Ver tamaño de base de datos
```powershell
Get-Item data\engastado.db | Select-Object Name, @{Name="Size(MB)";Expression={[math]::Round($_.Length/1MB,2)}}
```

### Ver archivos WAL (Write-Ahead Log)
```powershell
Get-ChildItem data\engastado.db*
# Verás: engastado.db, engastado.db-wal, engastado.db-shm
```

### Consultar archivo SQLite directamente
```powershell
# Instalar sqlite3 CLI (opcional):
# https://www.sqlite.org/download.html

sqlite3 data\engastado.db "SELECT COUNT(*) FROM ordenes_produccion;"
```

---

## ✅ Ventajas de SQLite vs JSON actual

| Aspecto | JSON actual | SQLite |
|---------|-------------|--------|
| Concurrencia | ❌ Condiciones de carrera | ✅ WAL mode + locks |
| Transacciones | ❌ No tiene | ✅ ACID completo |
| Integridad | ❌ Sin constraints | ✅ FKs, CHECKs, UNIQUEs |
| Consultas | ❌ Load todo a memoria | ✅ Queries SQL eficientes |
| Auditoría | ⚠️ Limitada | ✅ Triggers + updated_at |
| Backup | ⚠️ Copiar carpeta | ✅ Copiar 1 archivo |
| Permisos admin | ✅ No requiere | ✅ No requiere |

---

## 🎯 Siguiente paso

**AHORA MISMO:**
```powershell
cd C:\Users\estebanv\APP-ENGASTADO-SQL
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python run_sql.py
```

Abre navegador: **http://localhost:5001/health**

Si ves `"status": "ok"` → ✅ **Lista la base de datos**

---

## 📞 Troubleshooting

### Error: "No module named 'flask'"
```powershell
pip install -r requirements.txt
```

### Error: "No such file: schema_sqlite.sql"
Verifica que estás en la carpeta correcta:
```powershell
Get-Location  # Debe mostrar: APP-ENGASTADO-SQL
```

### Error: "database is locked" frecuente
1. Verificar que no hay múltiples instancias de run_sql.py corriendo
2. Reducir tiempo de transacciones en código
3. Aumentar timeout en config.py (actual: 30 seg)

### Base de datos corrupta
Restore desde backup:
```powershell
Copy-Item C:\Backups\engastado_FECHA.db data\engastado.db -Force
```

---

**Última actualización:** 16 de febrero de 2026  
**Próximo:** Implementar repositories y migrar datos JSON
