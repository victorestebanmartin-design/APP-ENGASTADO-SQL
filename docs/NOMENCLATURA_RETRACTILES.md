# Nomenclatura de Retráctiles — Preparación de Mangueras

> **Fichero vivo:** actualizar aquí cuando cambien los criterios o se añadan nuevos casos.  
> Última revisión: 2026-08-03

---

## Columnas en el Excel

Los retráctiles van en columnas propias, independientes de las instrucciones de pelado:

| Columna | Lado |
|---|---|
| `Retractil DE` | Lado De de la manguera |
| `Retractil PARA` | Lado Para de la manguera |

---

## Formato de los tokens

```
CODIGO_MEDIDA
```

- `CODIGO` — código del retráctil (número de referencia)
- `_` — separador obligatorio
- `MEDIDA` — milímetros a cortar (número entero)

Para **varios retráctiles en el mismo lado**, separarlos con `/`:

```
CODIGO1_MEDIDA1/CODIGO2_MEDIDA2
```

---

## Ejemplos

### Un solo retráctil en cada lado

| Columna | Valor |
|---|---|
| `Retractil DE` | `649255_40` |
| `Retractil PARA` | `649251_70` |

- Lado De: retráctil **649255**, cortar **40 mm**
- Lado Para: retráctil **649251**, cortar **70 mm**

---

### Varios retráctiles en un mismo lado

| Columna | Valor |
|---|---|
| `Retractil DE` | `649255_40/649251_70` |
| `Retractil PARA` | *(vacío)* |

- Lado De: retráctil 649255 → 40 mm · retráctil 649251 → 70 mm
- Lado Para: sin retráctiles

---

### Solo en un lado

| Columna | Valor |
|---|---|
| `Retractil DE` | *(vacío)* |
| `Retractil PARA` | `649255_55` |

- Lado De: sin retráctiles
- Lado Para: retráctil **649255**, cortar **55 mm**

---

## Reglas

1. **El separador entre código y medida es siempre `_`** — el último `_` de cada token marca la separación; el código puede contener guiones, letras o números.
2. **La medida es siempre un número entero** de milímetros.
3. **Múltiples retráctiles:** separar con `/` dentro de la misma celda.
4. **Las columnas son opcionales** — si están vacías o no existen, no aparece ningún retráctil en pantalla.
5. **Compatible con instrucciones de pelado** — las columnas `Retractil DE/PARA` son independientes de `Instrucciones Mangueras DE/PARA`; se pueden usar juntas o por separado.
