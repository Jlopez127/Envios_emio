# Deploy a HuggingFace Spaces — checklist

## ⛔ REGLA CRÍTICA

**Merge a `main` en GitHub NO despliega a HuggingFace.** GitHub y el Space son remotos
git distintos. Después de CADA merge a `main` hay que ejecutar **siempre**:

```bash
git push hf main
```

Recién ahí el Space hace rebuild (~30–50 s) y publica los cambios. Si no ves tus cambios
en el Space, casi seguro es que faltó este push.

## Remotos git

```bash
git remote -v
# origin  -> GitHub (código, PRs)
# hf      -> HuggingFace Space (deploy)

# Si falta el remoto hf (una vez):
git remote add hf https://huggingface.co/spaces/<usuario>/<space>
```

## Flujo de deploy

1. Trabajar en una rama, PR y merge a `main` en GitHub (`origin`).
2. `git checkout main && git pull origin main`.
3. **`git push hf main`**  ← el paso que despliega. Esperar el rebuild (~30–50 s).
4. Abrir el Space y verificar el arranque (ver abajo).

## Secrets en el Space

Space → **Settings → Variables and secrets**. Cargar (forma plana, que es como HF los
inyecta; `config.get_secret` también acepta la anidada):

- `ANTHROPIC_API_KEY`
- `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`
- Auth: subir la sección `[auth]` (credenciales hasheadas + cookie). En HF, si no se
  puede cargar TOML anidado como secret plano, usar un **Secret File** `secrets.toml` con
  la sección `[auth]` (y opcionalmente el resto), montado en `.streamlit/secrets.toml`.
- Flags como **Variables** (no secretas): `DATASOURCE_ASTRID=excel`,
  `DATASOURCE_DROPBOX=real`. **No** setear `EXCEL_DIRECTORIO_LOCAL`.

> **En producción `[auth]` DEBE estar configurado.** Sin `[auth]`, el portal arranca en
> **modo abierto** (con aviso visible), sin login — aceptable solo en desarrollo local.

## Verificar el arranque

1. El Space queda en estado **Running** (verde).
2. Aparece el **login** (usuario en minúsculas). Loguearse con `admin1`/`admin2`/`admin3` (o los reales configurados en `AUTH_USERS`).
3. Cargan las 5 tabs. En modo real, la **primera carga** parsea los manifiestos desde
   Dropbox (~1–2 min la primera vez; luego cacheado 10 min). Achicar el rango de fechas
   para probar más rápido.
4. Revisar los **logs** del Space (pestaña *Logs*) si algo falla — un secret faltante
   sale como advertencia visible en el dashboard, no como crash.

## Si el CSS se ve raro tras un rebuild

El CSS ejecutivo depende de la estructura del DOM de Streamlit. Por eso `streamlit` está
**pinneado a `1.50.0`** en `requirements.txt`.

- Verificar que `requirements.txt` sigue con `streamlit==1.50.0` (un rebuild no debe
  cambiar la versión).
- El sidebar se estiliza **solo** vía `.streamlit/config.toml` (`[theme.sidebar]`), nunca
  con CSS: si el sidebar se ve mal, revisar `config.toml`, no el CSS.
- El CSS global va con `st.markdown(unsafe_allow_html=True)` (nunca `st.html`, que vacía
  los `<style>`).
- Forzar un rebuild limpio: *Settings → Factory reboot* del Space.

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
