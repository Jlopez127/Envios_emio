# Contrato de Datos — Portal de Envíos Encargomío

Estructura canónica de los objetos del dominio y del archivo de persistencia. Este
contrato es la referencia única para modelos, mocks, interfaces y conciliación.

- **Moneda:** USD.
- **Peso:** kg para importación (aéreo), lb para distribución nacional.

---

## Modelos de dominio

### Manifiesto
```
{ id, fecha, awb_master, pallets, tulas: [Tula], envios: [Envio] }
```

### Tula
```
{ codigo (ej "260714-900007-3"), numero, kg_sistema, kg_reportado }
```

### Envio
```
{ guia, casillero, cliente, destinatario, ciudad, departamento, contenido,
  peso_lb, peso_kg, tula_codigo, tipo ("estandar" | "comercial"),
  valor_cobrado_cliente_usd }
```

### FacturaAerolinea
```
{ numero, fecha, awb, kg_cobrados, tarifa_kg_usd, awb_fee_usd,
  pickup_entrega_usd, otros_cargos: [{ concepto, valor }], total_usd }
```

### CobroDistribucion
```
{ guia, manifiesto_id, transportadora, lb_facturadas, valor_usd }
```

> La distribución nacional la **factura ASTRID** (mismo proveedor del sistema). En la UI
> el cobro/pago de despacho se rotula **"ASTRID"**; el campo `transportadora` se conserva
> como el sub-carrier concreto (TransA, TransB, etc.).

### Novedad
```
{ fecha, usuario, manifiesto_id, tula_codigo | null, guia | null,
  tipo ("peso_tula" | "cobro_aerolinea" | "cobro_distribucion"),
  valor_esperado, valor_real, delta, justificacion, accion, estado }
```

### GastoReal
```
{ fecha, manifiesto_id, proveedor,
  concepto ("importacion" | "distribucion"),
  referencia (nro_factura o guia), detalle_json, total_usd,
  origen ("vision" | "manual") }
```

### Tarifario
Valores **DEMO genéricos** (los reales no viven en el código). Precedencia de carga:
**hoja `TARIFARIO` (Dropbox) > env/secret (`[tarifario]` / `TARIFA_*`) > default DEMO**.
```
{ imp_awb_fee: 10.0,          # DEMO
  imp_pickup: 50.0,           # DEMO
  imp_tarifa_kg: 1.00,        # DEMO (la real vía secret/env o hoja TARIFARIO)
  dist_base_usd: 5,           # DEMO
  dist_base_lb: 5,            # DEMO
  dist_usd_lb_extra: 1,       # DEMO
  alerta_peso_kg: 2.0,
  alerta_peso_pct: 10.0,
  cobertura_tulas_minima: 0.80,     # config del motor; ver "Reglas de derivación"
  cobro_comercial_usd_lb: 5.0,      # DEMO — cobro al cliente USD/lb (comercial)
  cobro_estandar_usd_lb: 4.0 }      # DEMO — cobro al cliente USD/lb (estándar)
```

---

## Excel de Dropbox (persistencia)

Un solo archivo, **cuatro hojas**, todas **append-only**.

### Hoja `NOVEDADES`
Columnas = campos de **Novedad**:
`fecha, usuario, manifiesto_id, tula_codigo, guia, tipo, valor_esperado,
valor_real, delta, justificacion, accion, estado`

### Hoja `GASTOS_REALES`
Columnas = campos de **GastoReal**:
`fecha, manifiesto_id, proveedor, concepto, referencia, detalle_json,
total_usd, origen`

### Hoja `COBROS_DISTRIBUCION`
Columnas = campos de **CobroDistribucion**:
`guia, manifiesto_id, transportadora, lb_facturadas, valor_usd`

Es el "cobrado real" del frente Colombia, análogo a la FacturaAerolinea del frente
USA: el detalle operativo **por guía** de lo que factura la transportadora.

### Hoja `TULAS_REPORTADAS` (provisional)

Columnas = campos de **TulaReportada**:
`manifiesto_id, numero_tula, kg_reportado, awb_master, fecha, usuario, origen`

Pesos por tula cargados **por visión** (pantallazo/correo de ASTRID), como adelanto
mientras la API de ASTRID no traiga `kg_reportado` por tula. El `awb_master` se persiste
acá porque el AWB **se asigna al despachar** (no nace con el manifiesto) y llega en ese
mismo correo — así queda el vínculo **manifiesto↔awb** para el match de facturas.
**Flujo provisional**: se elimina cuando la API traiga los pesos (ver docs/PENDIENTES_API.md).

### Idempotencia — nunca duplicar

- **Novedad:** clave = `(manifiesto_id, tula_codigo | guia, tipo)`.
- **GastoReal:** clave = `(manifiesto_id, concepto, referencia)`.
- **CobroDistribucion:** clave = `(manifiesto_id, guia)`.
- **TulaReportada:** clave = `(manifiesto_id, numero_tula)`.

Antes de agregar una fila, verificar que no exista ya una con la misma clave. Nunca se
duplican filas.

---

## Reglas de derivación

Reglas del motor de cálculo (`core/calculos.py`) que derivan valores no explícitos en
el contrato. Deben ser **trazables**: el resultado expone de dónde salió cada número.

### kg de sistema total del manifiesto — `fuente = "tulas" | "envios"`

El total de kg de sistema puede provenir de dos lugares según la calidad de los datos:

- **`fuente = "tulas"`** — suma de `tula.kg_sistema`. Se usa cuando las tulas cubren
  el manifiesto, es decir cuando la fracción de envíos con `tula_codigo` asignado es
  **≥ `cobertura_tulas_minima`** (default 0.80). Caso mock/API.
- **`fuente = "envios"`** — suma de `envio.peso_kg`. Se usa cuando la asignación de
  tulas está **incompleta** (`< cobertura_tulas_minima`), como en el export Excel
  (~9% de envíos con tula). En este caso se registra la advertencia:
  `"asignación de tulas incompleta (X%) — total calculado por envíos"`.

La `fuente` viaja dentro del `Resultado` (en `detalle["fuente"]`) y se propaga hasta
la conciliación de importación (`fuente_kg_sistema`) para que el dashboard (Fase 3)
pueda mostrar el origen del cálculo. El umbral `cobertura_tulas_minima` es config del
`Tarifario`, no un valor hardcodeado.

> Nota: en el mock, `tula.kg_sistema` es la autoridad del total y los `envio.peso_kg`
> son independientes; en el Excel real, `envio.peso_kg` suma el total y las tulas son
> una agrupación parcial. La regla anterior da el total correcto en ambos casos
> (cada fuente entrega el total correcto según la calidad de los datos del manifiesto).

### kg reportado (báscula) — `fuente = "tulas" | "tulas_reportadas"`

El peso de báscula del manifiesto (`kg_reportado_total`) puede venir de dos lugares:

- **`fuente = "tulas"`** — `tula.kg_reportado` del datasource (mock/API).
- **`fuente = "tulas_reportadas"`** — suma de la hoja `TULAS_REPORTADAS` del manifiesto
  (cargadas por pantallazo), cuando el datasource no trae pesos por tula (caso excel).

**Prioridad: datasource sobre pantallazo.** Si un manifiesto llega a tener AMBAS (la API
las trae y ya existían registros por pantallazo) y los totales difieren más que el umbral
de alerta (`alerta_peso_kg` o `alerta_peso_pct`), se registra una **advertencia visible**
(*"pesos de báscula del datasource difieren de los registrados por pantallazo (X vs Y
kg)"*) — puede ser repesaje legítimo, pero no se resuelve en silencio. La `fuente` viaja
en el `Resultado` y se propaga a la conciliación (`fuente_kg_reportado`).

### CobroDistribucion vs. GastoReal(distribucion) — evitar doble contabilidad

Dos objetos distintos, dos usos distintos. No confundirlos:

- **`CobroDistribucion`** (hoja `COBROS_DISTRIBUCION`) = detalle operativo **por guía**
  (lo que la transportadora factura guía a guía). Es la fuente de la **conciliación de
  distribución** (tab Distribución): `delta = valor_cobrado − esperado` por guía.
- **`GastoReal(concepto="distribucion")`** (hoja `GASTOS_REALES`) = **agregado
  confirmado** que alimenta el **P&L** (suma de cobros de un manifiesto/corte, con
  `referencia` al lote o factura de la transportadora).

**Regla:** la conciliación por guía lee `COBROS_DISTRIBUCION`; el **P&L lee solo
`GASTOS_REALES`**. Nunca se suman cobros individuales directo al P&L — así se evita la
doble contabilidad cuando existan ambos. (Analogía USA: la FacturaAerolinea concilia
importación, pero el P&L usa el `GastoReal(concepto="importacion")`.)

### FacturaAerolinea — `detalle_json` es la fuente canónica (sin almacén aparte)

**Decisión (21/07/2026):** NO existe un almacén de facturas separado. La factura
extraída por visión se persiste **únicamente** como `GastoReal(concepto="importacion",
origen="vision")`, con la FacturaAerolinea completa en su `detalle_json` (kg_cobrados,
tarifa_kg_usd, awb_fee_usd, pickup_entrega_usd, otros_cargos, awb). La conciliación de
importación **reconstruye la FacturaAerolinea desde `detalle_json`** — ese campo es la
fuente canónica de la factura.

### Excepciones legacy de nombre de archivo (cerradas)

La convención vigente para todo export futuro es `YYYY-MM-DD-<id>-ASTRID.xlsx` (patrón
estricto; ver docs/PENDIENTES_API.md → "Variantes de export"). Algunos manifiestos
históricos, de ANTES de fijarse la convención, no la cumplen y se incluyen por una
**lista de excepciones cerrada y explícita** que mapea el **nombre exacto** del archivo
a su `(id, fecha)`. Esa lista es **dato operativo**: no vive en el código, se carga por
secret/env (`config.get_manifiestos_legacy`; secret `[manifiestos] legacy` o env
`MANIFIESTOS_LEGACY`, JSON). Formato (ejemplo genérico):

```json
{ "2026-01-01-900001-EJEMPLO.xlsx": ["900001", "2026-01-01"] }
```

Reglas:
- **La lista NO crece.** Cualquier archivo nuevo debe cumplir el patrón estricto.
- **Regla dura:** se omite SIEMPRE cualquier archivo cuyo nombre contenga `DIAN`
  (aunque estuviera en la lista) — defensa futura.
- La `fecha` sale del nombre cuando lo trae; si el nombre no la trae, se fija en la
  entrada legacy (ej. max de `FECHA GUIA` del contenido).
- El parser los digiere sin cambios (tienen `INFO MANIFIESTO` + columnas del contrato;
  hojas/columnas extra se ignoran).
