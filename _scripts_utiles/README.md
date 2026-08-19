# Scripts de Utilidad / Diagnóstico

Esta carpeta contiene scripts Python que se crearon durante el desarrollo para
tareas puntuales (insertar datos, diagnosticar errores, arreglar algo roto).
**No son parte de la aplicación principal.**

---

## Puesta en marcha de un PC de puesto

| Archivo | Para qué sirve |
|---------|----------------|
| `configurar_pc_puesto.ps1` | Quita el «No es seguro» del navegador y crea el acceso directo sin barra de direcciones |
| `generar_pin_hash.py` | Generar el `ADMIN_PIN_HASH` del `.env` |

### El aviso «No es seguro»

No lo pone la app: lo pone el navegador porque se entra por `http://` en vez
de `https://`. Los navegadores marcan así **todo** origen que no sea https,
con la única excepción de `localhost` — da igual que la red esté aislada y sin
internet. Por eso el servidor no lo ve (entra por `localhost`) y los puestos sí
(entran por `http://192.168.50.1:5001`).

Montar https de verdad pediría un certificado y meterlo en el almacén de
confianza de cada PC, para no ganar nada: en una red de planta cerrada no hay
nadie en medio de quien protegerse. La alternativa práctica es decirle al
navegador, por política de empresa, que ese origen concreto es de fiar:

```powershell
# En el PC del puesto, como administrador:
powershell -ExecutionPolicy Bypass -File .\configurar_pc_puesto.ps1
```

Luego hay que **cerrar el navegador del todo** y volver a abrirlo. Para
comprobar que la política está puesta: `chrome://policy`.

De paso arregla algo que estaba roto sin que se notara: sobre `http://` con
una IP, el navegador no permite registrar el *service worker*, así que la app
nunca ofrecía **«Instalar aplicación»** en los puestos (ver
`templates/_head_pwa.html`). Al marcar el origen como de confianza pasa a ser
«contexto seguro» y la instalación vuelve a estar disponible.

El acceso directo que crea abre la app con `--app=`, es decir sin barra de
direcciones, sin pestañas y sin botones de navegación: en un puesto el
operario no tiene por qué ver ninguna URL ni poder irse a otro sitio.

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
