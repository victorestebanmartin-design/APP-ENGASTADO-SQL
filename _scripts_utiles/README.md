# Scripts de Utilidad / Diagnóstico

Esta carpeta contiene scripts Python que se crearon durante el desarrollo para
tareas puntuales (insertar datos, diagnosticar errores, arreglar algo roto).
**No son parte de la aplicación principal.**

---

## Scripts de verificación / diagnóstico

| Archivo | Para qué sirvió |
|---------|----------------|
| `check_db.py` | Verificar tablas y conteo de registros en la BD |
| `check_db_full.py` | Inspección completa de la BD con detalles |
| `check_bonos.py` | Revisar estado de bonos en la BD |
| `check_data.py` | Comprobar datos generales cargados |
| `check_orden_location.py` | Localizar órdenes por número/bono |
| `verify_db.py` | Verificación general de integridad de la BD |
| `verify_final.py` | Verificación final tras migraciones |

## Scripts de creación manual de datos

| Archivo | Para qué sirvió |
|---------|----------------|
| `crear_carros.py` | Insertar los 6 carros manualmente tras vaciado de BD |
| `create_carros.py` | Variante del anterior |
| `create_maquinas.py` | Insertar puestos y máquinas manualmente |
| `create_terminales.py` | Insertar 45 terminales en `maquinas_terminales` |
| `setup_bono_real.py` | Configurar un bono real de prueba |

## Scripts de corrección (fix)

| Archivo | Para qué sirvió |
|---------|----------------|
| `fix_bono.py` | Corregir asociación de órdenes a bonos |
| `fix_bono_association.py` | Arreglar campo `bono_id` en órdenes |
| `fix_bono_final.py` | Versión final del arreglo de bonos |
| `fix_italia_code.py` | Corregir código de proyecto ITALIA en la BD |
| `move_orders.py` | Mover órdenes de un bono a otro |

## Scripts de migración obsoletos

| Archivo | Para qué sirvió |
|---------|----------------|
| `migrate_json_to_sql.py` | Migración a SQL Server (descartado, sin permisos admin) |
| `migrate_puestos_maquinas.py` | Versión antigua de migración de puestos |
| `migrar_etiquetas_json_a_sql.py` | Migración puntual de etiquetas JSON → SQL |
| `run_sql_old.py` | Versión anterior del script de arranque |

---

> La migración permanente y completa está en `/migrate_json_to_sqlite.py` (raíz del proyecto).
