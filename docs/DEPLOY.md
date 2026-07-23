# Deploy a Streamlit Community Cloud — checklist

## ✅ Auto-deploy desde `main`

El portal se despliega en **Streamlit Community Cloud** desde el **repo público** de
GitHub. **No hay un remoto de deploy aparte**: Community Cloud observa la rama `main` y
**redespliega solo** en cada push.

```bash
git checkout main && git pull origin main
git push origin main        # ← esto dispara el redeploy
```

Tras el push, Community Cloud detecta el commit y hace rebuild (**~1–2 min**). Si no ves
tus cambios, esperá el rebuild o revisá los logs (ver abajo).

## Alta de la app (una sola vez)

1. Entrar a **[share.streamlit.io](https://share.streamlit.io)** y loguearse con GitHub.
2. **Create app → Deploy a public app from GitHub**.
3. Repo: `Jlopez127/Envios_emio` · Branch: `main` · Main file path: `app.py`.
4. **Deploy**. La app queda en una URL `*.streamlit.app`.

> El repo debe ser **público** (Community Cloud gratuito). `requirements.txt` se instala
> automáticamente en el build; `streamlit` está pinneado a `1.50.0` (ver más abajo).

## Secrets (App settings → Secrets)

En la app: **⋮ → Settings → Secrets**. Se pega **un TOML** (Community Cloud lo expone como
`st.secrets`; `config.get_secret` acepta la forma anidada y también las formas planas). Los
**flags** van como claves top-level del TOML — `config._flag` los lee de `st.secrets`
cuando no hay variable de entorno:

```toml
# Flags de datasource (producción típica)
DATASOURCE_ASTRID = "excel"
DATASOURCE_DROPBOX = "real"
# NO setear EXCEL_DIRECTORIO_LOCAL (así los manifiestos salen de Dropbox)

[anthropic]
api_key = "sk-ant-..."

[dropbox]
app_key = "..."
app_secret = "..."
refresh_token = "..."
# opcionales: manifiestos_path / excel_path

# Auth (login obligatorio en producción; usernames y roles en minúsculas)
[auth]
usuarios = "admin1,admin2,proveedor1"   # o AUTH_USERS
roles = "proveedor1:proveedor"          # o campo `role` por usuario (ver abajo)

[auth.cookie]
name = "encargomio_portal"
key = "una-clave-larga-aleatoria"
expiry_days = 7

[auth.credentials.usernames.admin1]
name = "Admin Uno"
password = "$2b$..."   # hash bcrypt
role = "admin"

[auth.credentials.usernames.proveedor1]
name = "ASTRID"
password = "$2b$..."
role = "proveedor"     # acceso EXTERNO: solo su vista propia
```

Guardar los secrets **reinicia la app** automáticamente.

> **En producción `[auth]` DEBE estar configurado.** Sin `[auth]`, el portal arranca en
> **modo abierto** (con aviso visible), sin login — aceptable solo en desarrollo local.
> **Roles:** ver README → "Roles y aislamiento". El rol `proveedor` ve SOLO su vista.

## Verificar el arranque

1. La app queda **Running** en el dashboard de share.streamlit.io.
2. Aparece el **login** (usuario en minúsculas). Loguearse con un admin (`admin1`…) o el
   proveedor, según `AUTH_USERS`/`AUTH_ROLES`.
3. Cargan las tabs según el rol (6 tabs admin; el proveedor ve solo su vista). En modo
   real, la **primera carga** parsea los manifiestos desde Dropbox (~1–2 min la primera
   vez; luego cacheado 10 min). Achicar el rango de fechas para probar más rápido.

## Revisar los logs si falla el arranque

Si la app no levanta o muestra un error:

- **Desde la app en vivo:** botón **"Manage app"** (abajo a la derecha) → abre el panel de
  **logs** en tiempo real.
- **Desde el dashboard** [share.streamlit.io](https://share.streamlit.io): en el tile de
  la app, **⋮ → Manage app** → mismo panel de logs.
- Ahí se ven el traceback del build/arranque y los `print`/warnings. Un **secret faltante**
  sale como advertencia visible en el dashboard (no como crash) — igual conviene revisar
  los logs para confirmar `DATASOURCE_*` y credenciales.
- **Reboot / rebuild limpio:** en **Manage app → ⋮ → Reboot app** (fuerza reinstalar
  dependencias y reiniciar). Útil si un secret nuevo no se tomó.

## Si el CSS se ve raro tras un rebuild

El CSS ejecutivo depende de la estructura del DOM de Streamlit. Por eso `streamlit` está
**pinneado a `1.50.0`** en `requirements.txt`.

- Verificar que `requirements.txt` sigue con `streamlit==1.50.0` (un rebuild no debe
  cambiar la versión).
- El sidebar se estiliza **solo** vía `.streamlit/config.toml` (`[theme.sidebar]`), nunca
  con CSS: si el sidebar se ve mal, revisar `config.toml`, no el CSS.
- El CSS global va con `st.markdown(unsafe_allow_html=True)` (nunca `st.html`, que vacía
  los `<style>`).
- Forzar un rebuild limpio: **Manage app → ⋮ → Reboot app**.

## 🔒 Datos de clientes — verificar ANTES de cada push

**Los datos reales de clientes NUNCA se commitean.** `tests/fixtures/*.xlsx` y
`.streamlit/secrets.toml` están en `.gitignore`. Antes de cada `git push`:

```bash
# No debe listar ningún .xlsx real ni secrets.toml:
git ls-files | grep -E '\.xlsx$|secrets\.toml' || echo "OK: sin xlsx reales ni secrets"

# Y confirmar que git los está ignorando:
git check-ignore .streamlit/secrets.toml docs_internos tests/fixtures/EJEMPLO.xlsx
```

Si aparece un `.xlsx` real o `secrets.toml` en `git ls-files`, **detener el push**,
sacarlo del índice (`git rm --cached <archivo>`) y revisar `.gitignore`.

> **Repo público:** como el deploy es desde el repo público, cualquier cosa commiteada es
> visible. Doble cuidado con secrets y PII.
