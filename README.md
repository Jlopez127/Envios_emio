# Portal de Envíos Encargomío

Dashboard financiero y de conciliación para la línea de envíos **Miami → Colombia**.
Streamlit + Python, deploy en Streamlit Community Cloud (desde el repo público). **Sin
base de datos**: los datos
operativos se consultan en vivo (mock / export ASTRID en Dropbox / API futura) y lo
único que persiste es un Excel en Dropbox (append-only).

## Roles y aislamiento (acceso externo)

**ASTRID** (proveedor del despacho nacional) tiene acceso **externo** al portal: sube sus
facturas de despacho/reajustes y ve el estado de pago de sus facturas. Por eso hay **dos
roles**, definidos por usuario en el secret de auth:

- **`admin`** (interno) — acceso total: las 6 tabs de abajo.
- **`proveedor`** (externo) — acceso **exclusivo** a su vista: sus facturas de despacho y
  estado de pago (con comprobante), y carga de facturas/reajustes. **Nunca** ve P&L,
  utilidad, márgenes, ingresos, conciliación de aerolínea, tarifas, clientes, destinos ni
  novedades. El aislamiento es en el **render** (esas tabs y sus datos **no se
  construyen** en sesión de proveedor), no visual. Ver "Secrets" para configurar el rol.

## Las 6 tabs (rol admin)

1. **📊 Vista general** — filtros propios (fechas + manifiestos); KPIs (valor cobrado al
   cliente, pagado a aerolíneas, pagado a ASTRID, utilidad, #manifiestos/#envíos, kg,
   peso promedio, % con factura), **cuentas por pagar** (pendiente aerolíneas/ASTRID,
   vencido), **ahorro por consolidación**, manifiestos sin factura, y gráficos.
2. **✈️ Entrada a Colombia** — por manifiesto: pactado (motor) vs cobrado por la
   aerolínea, en dos caminos (peso aerolínea vs báscula, y cobro tarifa/cargos) +
   **estado de pago** (badges pendiente/pagado/vencido, "Registrar pago") + pagos.
3. **🚚 Despacho en Colombia** — por guía: esperado (regla 8 lb) vs cobro de **ASTRID** +
   **despachos consolidados** (esperado sobre peso total + ahorro; sus guías no se
   doble-cuentan) + estado de pago a ASTRID + pagos.
4. **⚖️ Novedades** — novedades de peso con drill-down por tula, justificación,
   manifiestos sin cobro, e historial de resueltas.
5. **📤 Cargar archivos** — carga por visión (Anthropic) de facturas de aerolínea,
   pantallazos de tulas y **facturas de despacho ASTRID** (si el proveedor no las sube).
6. **🧾 Reajustes** — recepción y archivo de reajustes (extracción genérica best-effort,
   editable) + listado. Solo recepción en esta fase (ver `docs/PENDIENTES_API.md`).

## Flags de datasource (variables de entorno / Secrets)

| Flag | Valores | Qué controla |
|---|---|---|
| `DATASOURCE_ASTRID` | `mock` \| `excel` \| `api` | Origen de manifiestos (`api` aún no existe) |
| `DATASOURCE_DROPBOX` | `mock` \| `real` | Persistencia (y, en modo `excel`, origen de manifiestos desde Dropbox) |
| `EXCEL_DIRECTORIO_LOCAL` | ruta | Modo `excel` local (gana sobre Dropbox); vacío + `DROPBOX=real` → Dropbox |

Modo producción típico (en Secrets de Community Cloud): `DATASOURCE_ASTRID=excel`,
`DATASOURCE_DROPBOX=real`, `EXCEL_DIRECTORIO_LOCAL` sin setear. En Community Cloud los
flags van como claves top-level del TOML de Secrets (`config._flag` los lee de
`st.secrets`). Detalle de modos: [`docs/CORRER_LOCAL.md`](docs/CORRER_LOCAL.md).

## Secrets requeridos (en App settings → Secrets de Streamlit Community Cloud; nunca en el repo)

`config.get_secret` acepta **ambas formas**: anidada (`.streamlit/secrets.toml` local, y el
TOML que se pega en Community Cloud) y **plana** (formas legacy `ANTHROPIC_API_KEY`, etc.).
Basta con proveer una.

| Secreto | Forma anidada (TOML) | Forma plana (legacy) |
|---|---|---|
| Anthropic (visión) | `[anthropic] api_key` | `ANTHROPIC_API_KEY` |
| Dropbox | `[dropbox] app_key / app_secret / refresh_token` | `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET` / `DROPBOX_REFRESH_TOKEN` |
| Rutas Dropbox (opcional) | `[dropbox] manifiestos_path / excel_path` | `DROPBOX_MANIFIESTOS_PATH` / `DROPBOX_EXCEL_PATH` |
| Auth | `[auth]` (ver abajo) | — |
| Usuarios admin autorizados | `[auth] usuarios` | `AUTH_USERS` (coma-separados) |
| Rol por usuario | campo `role` en `[auth.credentials.usernames.<u>]` | `AUTH_ROLES="user:rol,..."` (o `[auth] roles`) |
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

### Estructura del bloque `[auth]` (placeholders — **sin valores reales**)

> **Los valores reales (cookie key, hashes, contraseñas) NUNCA van en el repo.** Se pegan
> **solo** en **App settings → Secrets** de Streamlit Community Cloud (y, para dev local,
> en `.streamlit/secrets.toml`, que está gitignoreado). Este README documenta **la forma**
> del bloque, no sus valores.

```toml
# --- Visión y persistencia (mismos placeholders; reales solo en Secrets) ---
[anthropic]
api_key = "<ANTHROPIC_API_KEY>"

[dropbox]
app_key = "<DROPBOX_APP_KEY>"
app_secret = "<DROPBOX_APP_SECRET>"
refresh_token = "<DROPBOX_REFRESH_TOKEN>"

# --- Auth: cookie de sesión ---
[auth.cookie]
name = "encargomio_portal"
key = "<COOKIE_KEY>"         # token largo aleatorio: secrets.token_urlsafe(48)
expiry_days = 7

# --- Auth: un bloque por usuario (username SIEMPRE en minúsculas) ---
[auth.credentials.usernames.<usuario_admin>]
name = "<Nombre a mostrar>"
password = "<hash-bcrypt $2b$...>"   # hash bcrypt, NUNCA la contraseña en claro
role = "admin"                        # acceso total (todas las tabs)

[auth.credentials.usernames.<usuario_proveedor>]
name = "<Nombre a mostrar>"
password = "<hash-bcrypt $2b$...>"
role = "proveedor"                    # acceso EXTERNO: SOLO su vista propia
```

**Roles.** El rol se define **por usuario** con el campo `role` (`admin` | `proveedor`)
dentro de su bloque de credenciales. Alternativa plana: `AUTH_ROLES="usuario:rol,..."`
(env o `[auth] roles`), que **gana** sobre el campo `role`. Sin rol explícito, un usuario
autorizado se toma como **`admin`**. El rol `proveedor` (acceso externo) ve **solo su
tab**; el resto (P&L, aerolínea, clientes, novedades) **no se construye** en su sesión.

**Casing.** Usernames y roles **SIEMPRE en minúsculas** (bug de casing de
streamlit-authenticator; el portal normaliza a minúsculas y los usuarios ingresan en
minúsculas). Sin `[auth]` → **modo abierto** con aviso (solo desarrollo local).

**Generar los valores** (localmente, para pegarlos en Secrets):

```python
import secrets, streamlit_authenticator as stauth
print("cookie key:", secrets.token_urlsafe(48))         # → [auth.cookie] key
print("hash:", stauth.Hasher.hash("<contraseña-en-claro>"))  # → password de cada usuario
```

## Correr local

Ver [`docs/CORRER_LOCAL.md`](docs/CORRER_LOCAL.md). Tests: `python -m pytest -q`.

## Deploy a Streamlit Community Cloud

Ver [`docs/DEPLOY.md`](docs/DEPLOY.md). **Auto-deploy:** con **push a `main`** en GitHub,
Streamlit Community Cloud **redespliega solo** (~1–2 min) desde el repo público. Los
secrets (credenciales, flags, `[auth]`) se pegan en **App settings → Secrets**. Si el
arranque falla, revisar los **logs** en *Manage app* (ver DEPLOY.md).

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
