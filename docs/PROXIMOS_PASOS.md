# 🎯 PRÓXIMOS PASOS - Migración a SQL

**Fecha:** 16 de febrero de 2026  
**Estado:** Estructura base creada ✅  
**Proyecto viejo:** Intacto y funcionando ✅

---

## ✅ Completado

1. **Estructura de carpetas creada:**
   - ✅ `APP-ENGASTADO-SQL/` con todos los directorios
   - ✅ Schema SQL completo (`schema.sql`)
   - ✅ Configuración (`config.py`)
   - ✅ Requirements con dependencias SQL (`requirements.txt`)
   - ✅ Script de arranque (`run_sql.py`)
   - ✅ Migrador stub (`migrate_json_to_sql.py`)
   - ✅ .gitignore configurado
   - ✅ README con instrucciones completas

2. **Proyecto viejo preservado:**
   - ✅ Ningún archivo modificado en `PROYECTO-ENGASTADO1git/`
   - ✅ Sistema JSON sigue funcionando en puerto 5000
   - ✅ Datos intactos

---

## 📋 Checklist de Implementación

### Fase 1: Setup SQL Server (1-2 días)

- [ ] **Instalar SQL Server**
  - [ ] Descargar SQL Server Express
  - [ ] Instalar SSMS (SQL Server Management Studio)
  - [ ] Verificar servicio corriendo

- [ ] **Instalar ODBC Driver**
  - [ ] Descargar ODBC Driver 17 o 18
  - [ ] Verificar instalación: `Get-OdbcDriver`

- [ ] **Crear base de datos**
  - [ ] Conectar con SSMS a `localhost\SQLEXPRESS`
  - [ ] Ejecutar `schema.sql` completo
  - [ ] Verificar tablas creadas (17 tablas esperadas)
  - [ ] Verificar vistas (`vw_bonos_con_carros`, `vw_ordenes_por_bono`)

- [ ] **Configurar conexión**
  - [ ] Editar `config.py` con tu servidor SQL
  - [ ] Probar conexión: `python -c "import pyodbc; print(pyodbc.drivers())"`

### Fase 2: Entorno Python (1 día)

- [ ] **Setup entorno virtual**
  ```powershell
  cd C:\Users\estebanv\APP-ENGASTADO-SQL
  python -m venv venv
  .\venv\Scripts\activate
  pip install -r requirements.txt
  ```

- [ ] **Verificar instalación**
  - [ ] `python -c "import pyodbc; print('OK')"`
  - [ ] `python -c "import sqlalchemy; print('OK')"`
  - [ ] `python -c "from config import Config; print(Config.DB_NAME)"`

### Fase 3: Migración de Datos (2-3 días)

- [ ] **Completar `migrate_json_to_sql.py`**
  - [ ] Implementar inserción de proyectos
  - [ ] Implementar inserción de órdenes
  - [ ] Implementar inserción de bonos/carros
  - [ ] Implementar códigos de cortes
  - [ ] Implementar puestos/máquinas/terminales
  - [ ] Implementar grupos de etiquetas
  - [ ] Manejo de errores y rollback

- [ ] **Backup antes de migrar**
  ```powershell
  Copy-Item C:\Users\estebanv\PROYECTO-ENGASTADO1git\data C:\Users\estebanv\data_backup_20260216 -Recurse
  ```

- [ ] **Ejecutar migración**
  ```powershell
  # Dry-run primero
  python migrate_json_to_sql.py --dry-run
  
  # Si todo OK, ejecutar real
  python migrate_json_to_sql.py
  ```

- [ ] **Validar migración**
  - [ ] Contar registros en SQL vs JSON
  - [ ] Verificar integridad referencial (FKs)
  - [ ] Comprobar datos críticos manualmente

### Fase 4: Capa de Repositorios (3-5 días)

- [ ] **Crear repositorios base**
  - [ ] `repositories/base_repository.py` (clase abstracta)
  - [ ] `repositories/proyecto_repository.py`
  - [ ] `repositories/orden_repository.py`
  - [ ] `repositories/bono_repository.py`
  - [ ] `repositories/carro_repository.py`
  - [ ] `repositories/codigo_corte_repository.py`
  - [ ] `repositories/puesto_maquina_repository.py`
  - [ ] `repositories/etiqueta_repository.py`

- [ ] **Implementar operaciones CRUD**
  - [ ] Create (INSERT)
  - [ ] Read (SELECT con filtros)
  - [ ] Update (UPDATE transaccional)
  - [ ] Delete (DELETE con cascadas)

- [ ] **Queries especializadas**
  - [ ] Búsqueda por estado
  - [ ] Agregaciones (contar, sumar)
  - [ ] Joins complejos (bonos con carros, órdenes con proyectos)

### Fase 5: Adaptar Lógica de Negocio (5-7 días)

- [ ] **Copiar módulos del proyecto viejo**
  ```powershell
  Copy-Item C:\Users\estebanv\PROYECTO-ENGASTADO1git\app\zpl_templates.py app\
  Copy-Item C:\Users\estebanv\PROYECTO-ENGASTADO1git\static\* static\ -Recurse
  Copy-Item C:\Users\estebanv\PROYECTO-ENGASTADO1git\templates\* templates\ -Recurse
  ```

- [ ] **Refactorizar `app/excel_manager.py`**
  - [ ] Cambiar `json.load/dump` por `CodigoCorteRepository`
  - [ ] Mantener lógica de parsing Excel intacta
  - [ ] Transacciones SQL al guardar códigos

- [ ] **Refactorizar `app/printer_manager.py`**
  - [ ] Cambiar cola JSON por `EtiquetaRepository`
  - [ ] Tabla `etiquetas_pendientes` para cola
  - [ ] Reintentos transaccionales

- [ ] **Refactorizar `app/proyecto_manager.py`**
  - [ ] Eliminar singleton global
  - [ ] Usar `ProyectoRepository`, `BonoRepository`, `CarroRepository`
  - [ ] Transacciones para estado de proyectos/carros

- [ ] **Adaptar `app/routes.py`**
  - [ ] Cada endpoint usa repositorio correspondiente
  - [ ] Transacciones por request
  - [ ] Manejo de excepciones SQL
  - [ ] Logging de operaciones

### Fase 6: Testing (3-4 días)

- [ ] **Testing funcional básico**
  - [ ] Arrancar app: `python run_sql.py`
  - [ ] Acceder a `http://localhost:5001/health`
  - [ ] Probar carga de Excel
  - [ ] Probar escaneo de órdenes
  - [ ] Probar creación de bonos
  - [ ] Probar asignación de carros
  - [ ] Probar actualización de estados
  - [ ] Probar generación de etiquetas

- [ ] **Testing de concurrencia**
  - [ ] Abrir 5+ sesiones simultáneas
  - [ ] Escanear órdenes en paralelo
  - [ ] Actualizar estados concurrentemente
  - [ ] Verificar NO hay pérdida de datos
  - [ ] Verificar NO hay deadlocks

- [ ] **Testing de integridad**
  - [ ] Crear orden huérfana (sin bono) → debe fallar FK
  - [ ] Eliminar bono con carros → debe limpiar o fallar
  - [ ] Actualizar estado inválido → debe fallar CHECK constraint

### Fase 7: Piloto (1 semana)

- [ ] **Configurar acceso piloto**
  - [ ] Identificar 2-3 usuarios piloto
  - [ ] Configurar firewall para puerto 5001
  - [ ] Apuntar sus PCs a `http://TU_IP:5001`
  - [ ] Otros usuarios siguen en puerto 5000

- [ ] **Monitoreo diario**
  - [ ] Revisar logs en `logs/app.log`
  - [ ] Consultar queries lentas en SQL Server
  - [ ] Verificar uso de CPU/memoria
  - [ ] Detectar errores de usuarios

- [ ] **Comparación de resultados**
  - [ ] Misma operación en ambos sistemas
  - [ ] Comparar datos generados
  - [ ] Validar paridad funcional

### Fase 8: Go Live (2-3 días)

- [ ] **Backup pre-switcheo**
  - [ ] Backup completo de SQL: `BACKUP DATABASE EngastadoDB...`
  - [ ] Backup final de JSON
  - [ ] Backup de código

- [ ] **Switcheo de producción**
  - [ ] Anunciar ventana de mantenimiento
  - [ ] Detener app vieja (puerto 5000)
  - [ ] Cambiar `run_sql.py` a puerto 5000
  - [ ] Arrancar nueva app en puerto 5000
  - [ ] Verificar acceso de todos los usuarios

- [ ] **Deprecar JSON**
  - [ ] Marcar carpeta `data/` como read-only
  - [ ] Documentar cómo acceder a datos viejos si necesario
  - [ ] Mantener `PROYECTO-ENGASTADO1git` 1 mes como contingencia

### Fase 9: Hardening Operativo (1 semana)

- [ ] **Backup automático SQL**
  - [ ] Script de backup diario
  - [ ] Tarea programada Windows
  - [ ] Retención: 7 días completos, 4 semanales, 3 mensuales
  - [ ] Probar restore desde backup

- [ ] **Monitoreo**
  - [ ] Alertas por errores críticos
  - [ ] Dashboard de queries lentas
  - [ ] Logs centralizados

- [ ] **Documentación**
  - [ ] Manual de operador actualizado
  - [ ] Troubleshooting SQL Server
  - [ ] Procedimiento de restore
  - [ ] Contactos de soporte

---

## 🚨 Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Error en migración de datos | Media | Alto | Dry-run + backup + validación registro a registro |
| Performance pobre de SQL | Baja | Medio | Índices bien definidos + query optimization |
| Drivers ODBC no compatibles | Media | Alto | Probar múltiples drivers (17, 18, pymssql) |
| Usuarios rechazan nueva UI | Baja | Bajo | UI idéntica, solo backend cambia |
| Corrupción de datos SQL | Muy baja | Crítico | Backups diarios + replicación (opcional) |
| Sistema viejo no arranca después | Baja | Alto | Mantenido intacto, sin tocar código |

---

## 📞 Contactos de Emergencia

- **SQL Server issues:** Documentación Microsoft
- **Rollback urgente:** Volver a ejecutar `run.py` del proyecto viejo
- **Backup location:** `C:\Backups\EngastadoDB\`

---

## 🎯 Timeline Estimado

**Total: 3-6 semanas**

- Semana 1: Setup SQL + Migración datos
- Semana 2-3: Repositorios + Lógica de negocio
- Semana 4: Testing funcional + concurrencia
- Semana 5: Piloto con usuarios
- Semana 6: Go live + hardening

---

**Última actualización:** 16 de febrero de 2026  
**Próximo checkpoint:** Setup SQL Server y primera migración dry-run
