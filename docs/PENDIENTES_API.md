# Pendientes de la API de ASTRID

Registro central de los datos que el **export Excel de ASTRID no trae** y que el
portal necesita. Sirve de constancia formal: cada faltante depende de la API de
ASTRID (solicitada en la **HU del 21/07/2026**).

> Se actualiza en **cada fase** que toque un faltante (marcar aquí cuándo y cómo se
> resolvió, o si se agrega un nuevo faltante).

| Campo | Dónde se usa | Estado actual | De quién depende | Referencia |
|---|---|---|---|---|
| `kg_reportado` por tula (pesos reportados por tula) | Novedades de peso (conciliación de tulas: sistema vs. reportado) | No existe en el export → `tula.kg_reportado = None` | API ASTRID | HU 21/07/2026 |
| `valor_cobrado_cliente_usd` por envío | P&L — ingresos (facturación al cliente) | No existe en el export → `None` | API ASTRID | HU 21/07/2026 |
| `tipo` (estándar / comercial) por envío | P&L y analítica (segmentación de ingresos y volumen) | No existe en el export → `None` | API ASTRID | HU 21/07/2026 |
| `tula_codigo` por envío (tula por envío) | Conciliación fina (agrupar envíos por tula) | Asignación **incompleta** en el export (~4/20 en el ejemplo de cobertura parcial) → `None` si vacío; `n_tulas = None` si <80% de envíos traen tula | API ASTRID | HU 21/07/2026 |
| `pallets` por manifiesto | Métricas de importación | No existe en el export → `manifiesto.pallets = None` | API ASTRID | HU 21/07/2026 |

## Variantes de export — decisión cerrada (21/07/2026): se omiten

**Decisión del owner (21/07/2026):** el patrón estricto
`YYYY-MM-DD-<id>-ASTRID[ (n)].xlsx` es **DEFINITIVO**. Los sufijos posteriores a
`ASTRID` (`-con-TULA`, `-CAJAS` y similares) **se omiten para siempre**: los exports
futuros de ASTRID no traerán esos nombres.

Sufijos vistos y su tratamiento definitivo:

| Sufijo en el nombre | Ejemplo | Tratamiento |
|---|---|---|
| `-con-TULA` | `2026-07-06-900002-ASTRID-con-TULA.xlsx` | Se omite (definitivo) |
| `-con-TULA-CEL` | `2026-07-06-900002-ASTRID-con-TULA-CEL.xlsx` | Se omite (definitivo) |
| `-CAJAS` | `2026-07-08-900003-ASTRID-CAJAS.xlsx` | Se omite (definitivo) |
| `DEFINITIVO` | `*DEFINITIVO*` | Se omite (definitivo) |
| `DUPLICADOS` | `*DUPLICADOS*` | Se omite (definitivo) |
| `CAJAS-CEL` | `*CAJAS-CEL*` | Se omite (definitivo) |

**Comportamiento (correcto y definitivo):** solo se ingiere el export base (+ sufijos
Dropbox `" (1)"`). Cualquier otro archivo se **omite y queda registrado en
`archivos_omitidos`** (visible para diagnóstico); no se pierde nada. No se amplía el
patrón. El código actual (`datasources/astrid_excel.py`, regex `_PATRON`) ya cumple
esta decisión — no requiere cambios.

**Dedupe** (varios archivos válidos del mismo `id`): se usa el de **`mtime` más
reciente** y se registra una **advertencia** siempre que ocurra.

## Flujo provisional: pesos por tula por visión (se elimina con la API)

Mientras la API de ASTRID no traiga `kg_reportado` por tula, el portal permite cargar
esos pesos **por visión** (pantallazo de la pantalla de tulas de ASTRID → extracción
con la API de Anthropic → hoja `TULAS_REPORTADAS` en Dropbox, append-only, llave
`(manifiesto_id, numero_tula)`).

- **Alcance:** `vision/extractor.py` (`extraer(..., "pantalla_tulas")`), tab ⚖️ Novedades,
  `dropbox_base`/`dropbox_mock`/`dropbox_api` (`leer/agregar_tulas_reportadas`), y el
  motor (`kg_reportado_total` con `fuente="tulas_reportadas"`).
- **Se elimina** cuando la API de ASTRID provea `kg_reportado` por tula (fila
  `kg_reportado` de la tabla de arriba): en ese momento la conciliación de peso usa el
  dato de la API y este flujo (hoja + extracción de tulas) queda obsoleto.
- Buscar `TULAS_REPORTADAS` y `pantalla_tulas` en el repo para ubicarlo.

## Otros apoyos provisionales (a retirar con la API)

- **Drill-down de tula por heurística** (`core/vista.py` `envios_de_tula`, `app.py`
  bloque `.heuristica`): cuando falta `tula_codigo` (export excel), en vez de los envíos
  de la tula se listan los N más pesados del manifiesto como **sospecha** — etiquetado
  explícitamente como NO confirmado. Se retira cuando llegue `tula_codigo` real.
- **Lista de manifiestos legacy** (`config.get_manifiestos_legacy`, cargada por
  secret/env `MANIFIESTOS_LEGACY` — no en el código): manifiestos históricos de ANTES de
  la convención de nombres. Se retira si la API sirve esos
  manifiestos con su estructura (ver docs/CONTRATO_DATOS.md → "Excepciones legacy").

## Barrido de coherencia (Fase 6, 21/07/2026)

Todos los `# PENDIENTE_API` del código corresponden a los **5 campos** de la tabla de
arriba (kg_reportado, valor_cobrado_cliente_usd, tipo, tula_codigo, pallets), todos con
referencia **HU 21/07/2026**. Ubicaciones: `datasources/astrid_excel.py` (los 5 campos),
`core/calculos.py` (motivos de `kg_reportado` no disponible) y `app.py` (texto de la
heurística de tulas). No hay faltantes sin documentar.

## Convención en código

Cada punto donde se produce uno de estos faltantes está marcado en el código con:

```python
# PENDIENTE_API: <campo> — llega con la API de ASTRID (HU 21/07/2026)
```

Buscar `PENDIENTE_API` en el repo para ubicarlos todos.
