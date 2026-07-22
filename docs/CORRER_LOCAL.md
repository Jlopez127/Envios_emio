# Correr el portal en local

Referencia para levantar el Portal de Envíos Encargomío en la máquina, en cualquiera
de sus modos. Para quien retome el proyecto.

## Requisitos (una vez)

```bash
cd /ruta/al/repo
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Para los modos que tocan Dropbox o visión hace falta `.streamlit/secrets.toml`
(gitignoreado). Ver [`CREDENCIALES.md`](./CREDENCIALES.md). Esquema esperado:

```toml
[dropbox]
app_key = "..."
app_secret = "..."
refresh_token = "..."
# opcionales (si no están, se usan los defaults):
# manifiestos_path = "/portal_envios"
# excel_path = "/portal_envios/portal/registro.xlsx"

[anthropic]
api_key = "..."
```

> Los secrets se leen con `config.get_secret`, que acepta la forma **anidada**
> (`[dropbox] app_key`) y, como fallback, **planas** legacy (`DROPBOX_APP_KEY`,
> `ANTHROPIC_API_KEY`, …) — que es como HuggingFace Spaces suele cargarlos.

## Dos flags independientes

- **`DATASOURCE_ASTRID`** = `mock` | `excel` | `api` — de dónde salen los manifiestos.
  (`api` aún no existe → error claro.)
- **`DATASOURCE_DROPBOX`** = `mock` | `real` — la persistencia (novedades, gastos,
  cobros, tulas reportadas, tarifario) **y**, en modo `excel`, el origen de los
  manifiestos cuando no hay directorio local.

Ambos por defecto en `mock`. Se setean por variable de entorno.

| Modo | `DATASOURCE_ASTRID` | `DATASOURCE_DROPBOX` | `EXCEL_DIRECTORIO_LOCAL` | Manifiestos | Persistencia |
|---|---|---|---|---|---|
| **Mock** (default) | `mock` | `mock` | — | embebidos en código | en memoria (precargada con demo) |
| **Excel local** | `excel` | `mock` | `/ruta/a/exports` | directorio local | en memoria (precargada) |
| **Real** | `excel` | `real` | *(vacío)* | Dropbox `/portal_envios` | Dropbox `registro.xlsx` |

Los flags son independientes: podés combinar (ej. manifiestos locales + persistencia
real), pero los 3 modos de arriba son los usuales.

## Comandos

### Mock (datos embebidos, sin Dropbox ni API)
```bash
./.venv/bin/streamlit run app.py
```

### Excel local (manifiestos desde un directorio; persistencia mock)
```bash
DATASOURCE_ASTRID=excel EXCEL_DIRECTORIO_LOCAL="/ruta/a/exports" ./.venv/bin/streamlit run app.py
# ej. con el fixture real del repo:  EXCEL_DIRECTORIO_LOCAL=tests/fixtures
```

### Real (manifiestos desde Dropbox + persistencia Dropbox)
```bash
DATASOURCE_ASTRID=excel DATASOURCE_DROPBOX=real ./.venv/bin/streamlit run app.py
```

## Precedencia de `EXCEL_DIRECTORIO_LOCAL` (modo `excel`)

En `DATASOURCE_ASTRID=excel`, el origen de los manifiestos se resuelve así:

1. Si **`EXCEL_DIRECTORIO_LOCAL` está seteado** → **gana el directorio local** (ignora
   Dropbox). Útil para tests/dev.
2. Si está **vacío** y **`DATASOURCE_DROPBOX=real`** → manifiestos desde **Dropbox**.
3. Si está vacío y `DATASOURCE_DROPBOX=mock` → **error** claro (falta un origen).

Por eso, para modo real **no setees** `EXCEL_DIRECTORIO_LOCAL` (o dejalo vacío).

## Notas

- **Primera carga lenta en modo real**: el período por defecto (julio 2026) parsea los
  ~10 manifiestos desde Dropbox (~9 s c/u en la medición → puede rondar **1–2 min** la
  primera vez). Después quedan **cacheados 10 min** (`st.cache_data(ttl=600)`). Para
  probar más rápido, **achicá el rango de fechas** en el sidebar.
- **Manifiestos legacy**: algunos archivos históricos entran por la lista de excepciones
  (cargada por secret/env `MANIFIESTOS_LEGACY` vía `config.get_manifiestos_legacy`, no en
  el código); todo lo demás debe cumplir el patrón estricto.
  Ver [`CONTRATO_DATOS.md`](./CONTRATO_DATOS.md) → "Excepciones legacy (cerradas)".
- **Persistencia real**: el `registro.xlsx` se crea solo en la primera escritura
  (append-only). Si no existe, las lecturas devuelven vacío / tarifario por defaults.
- **Visión**: requiere `[anthropic] api_key`. Si falta, la extracción muestra un error
  puntual y el resto del dashboard sigue operando.
- **Nunca** commitear `.streamlit/secrets.toml` (ya está en `.gitignore`).

## Correr los tests

```bash
./.venv/bin/pip install pytest        # si no está
./.venv/bin/python -m pytest -q
```
