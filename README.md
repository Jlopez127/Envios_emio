---
title: Portal Envíos Encargomío
emoji: 📦
colorFrom: gray
colorTo: blue
sdk: streamlit
sdk_version: 1.50.0
app_file: app.py
pinned: false
---

# Portal de Envíos Encargomío

Dashboard financiero y de conciliación para la línea de envíos **Miami → Colombia**.
Streamlit + Python, deploy en HuggingFace Spaces. **Sin base de datos**: los datos
operativos se consultan en vivo (mock / export ASTRID en Dropbox / API futura) y lo
único que persiste es un Excel en Dropbox (append-only).

## Las 5 tabs

1. **📊 Vista general** — filtros propios (fechas + manifiestos); KPIs (valor cobrado al
   cliente, pagado a aerolíneas, pagado a ASTRID, utilidad, #manifiestos/#envíos, kg,
   peso promedio, % con factura) y gráficos (destinos, clientes, envíos/kg por manifiesto).
2. **✈️ Entrada a Colombia** — por manifiesto: pactado (motor) vs cobrado por la
   aerolínea, en dos caminos (peso aerolínea vs báscula, y cobro tarifa/cargos) + pagos
   a aerolínea.
3. **🚚 Despacho en Colombia** — por guía: esperado (regla 8 lb) vs cobro de **ASTRID**
   (factura la distribución nacional) + pagos a ASTRID.
4. **⚖️ Novedades** — novedades de peso con drill-down por tula (sus envíos, o heurística
   honesta si el export no trae asignación), justificación de novedades, manifiestos sin
   cobro, e historial de resueltas.
5. **📤 Cargar archivos** — carga por visión (Anthropic) de facturas de aerolínea y
   pantallazos de tulas; placeholder de factura de despacho ASTRID.

## Flags de datasource (variables de entorno / Space)

| Flag | Valores | Qué controla |
|---|---|---|
| `DATASOURCE_ASTRID` | `mock` \| `excel` \| `api` | Origen de manifiestos (`api` aún no existe) |
| `DATASOURCE_DROPBOX` | `mock` \| `real` | Persistencia (y, en modo `excel`, origen de manifiestos desde Dropbox) |
| `EXCEL_DIRECTORIO_LOCAL` | ruta | Modo `excel` local (gana sobre Dropbox); vacío + `DROPBOX=real` → Dropbox |

Modo producción típico en el Space: `DATASOURCE_ASTRID=excel`, `DATASOURCE_DROPBOX=real`,
`EXCEL_DIRECTORIO_LOCAL` sin setear. Detalle de modos: [`docs/CORRER_LOCAL.md`](docs/CORRER_LOCAL.md).

## Secrets requeridos (en el Space → Settings → Secrets; nunca en el repo)

`config.get_secret` acepta **ambas formas**: anidada (`.streamlit/secrets.toml` local) y
**plana** (como HuggingFace Spaces suele cargar los secrets). Basta con proveer una.

| Secreto | Forma anidada (TOML) | Forma plana (HF) |
|---|---|---|
| Anthropic (visión) | `[anthropic] api_key` | `ANTHROPIC_API_KEY` |
| Dropbox | `[dropbox] app_key / app_secret / refresh_token` | `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET` / `DROPBOX_REFRESH_TOKEN` |
| Rutas Dropbox (opcional) | `[dropbox] manifiestos_path / excel_path` | `DROPBOX_MANIFIESTOS_PATH` / `DROPBOX_EXCEL_PATH` |
| Auth | `[auth]` (ver abajo) | — |
| Usuarios admin autorizados | `[auth] usuarios` | `AUTH_USERS` (coma-separados) |
| Tarifas y umbrales (opcional) | `[tarifario] imp_tarifa_kg / imp_awb_fee / imp_pickup / …` | `TARIFA_IMP_KG` / `TARIFA_IMP_AWB_FEE` / `TARIFA_IMP_PICKUP` / … |
| Manifiestos legacy (opcional) | `[manifiestos] legacy` (JSON) | `MANIFIESTOS_LEGACY` (JSON) |

> **Los valores de negocio nunca están en el código.** Tarifas/umbrales, rutas de
> Dropbox, lista de manifiestos legacy y usuarios admin traen defaults **DEMO genéricos**;
> los reales se cargan por secret/env del host (y, para el tarifario, también por la hoja
> `TARIFARIO` del Excel de Dropbox).
>
> **Precedencia del tarifario:** hoja `TARIFARIO` (Dropbox) **>** `[tarifario]`/`TARIFA_*`
> (secret/env) **>** default DEMO (`imp_tarifa_kg = 1.00`, etc.). Editás las tarifas sin
> re-deploy cambiando la hoja `TARIFARIO`.

Ejemplo `.streamlit/secrets.toml` (local; **gitignoreado**):

```toml
[anthropic]
api_key = "sk-ant-..."

[dropbox]
app_key = "..."
app_secret = "..."
refresh_token = "..."

[auth.cookie]
name = "encargomio_portal"
key = "una-clave-larga-aleatoria"
expiry_days = 7

[auth.credentials.usernames.admin1]
name = "Admin Uno"
email = "admin1@example.com"
password = "$2b$..."   # hash bcrypt

[auth.credentials.usernames.admin2]
name = "Admin Dos"
password = "$2b$..."

[auth.credentials.usernames.admin3]
name = "Admin Tres"
password = "$2b$..."
```

**Usernames SIEMPRE en minúsculas** (bug de casing de streamlit-authenticator; el portal
normaliza a minúsculas y los usuarios deben ingresar en minúsculas). Usuarios autorizados:
`admin1`, `admin2`, `admin3` (DEMO en el código; los reales se cargan por secret/env `AUTH_USERS`, coma-separados). Sin `[auth]` → **modo abierto** con aviso (solo desarrollo).

Generar un hash bcrypt:

```python
import streamlit_authenticator as stauth
print(stauth.Hasher.hash("mi-password"))
```

## Correr local

Ver [`docs/CORRER_LOCAL.md`](docs/CORRER_LOCAL.md). Tests: `python -m pytest -q`.

## Deploy a HuggingFace Spaces

Ver [`docs/DEPLOY.md`](docs/DEPLOY.md). **Regla crítica:** merge a `main` en GitHub NO
despliega; hay que hacer `git push hf main` explícito después de cada merge.

## Migración a la API de ASTRID (cuando exista)

Hoy varios campos no vienen del export y hay flujos provisionales (ver
[`docs/PENDIENTES_API.md`](docs/PENDIENTES_API.md), HU del 21/07/2026). Pasos exactos:

1. **Paso 0**: comparar el **payload real de la API** contra
   [`docs/CONTRATO_DATOS.md`](docs/CONTRATO_DATOS.md) (mapear cada campo del contrato).
2. **Implementar `datasources/astrid_api.py`** contra `datasources/base.py` (misma
   interfaz `FuenteASTRID`: `get_manifiestos`, `get_manifiesto`), devolviendo el
   Manifiesto completo con `tula.kg_reportado`, `envio.tula_codigo`, `tipo` y
   `valor_cobrado_cliente_usd` reales.
3. **Cambiar el flag** `DATASOURCE_ASTRID=api`.
4. **Revisar `docs/PENDIENTES_API.md`** y **retirar los flujos marcados como
   provisionales**:
   - Pantallazos de tulas (`TULAS_REPORTADAS`, `extraer(..., "pantalla_tulas")`) — la API
     ya trae `kg_reportado` por tula.
   - Los `None` del export excel (kg_reportado, valor_cobrado, tipo, tula_codigo, pallets)
     y la heurística de "envíos más pesados".
   - `MANIFIESTOS_LEGACY` si la API sirve esos manifiestos históricos con su estructura.
