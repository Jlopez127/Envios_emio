# Portal de Envíos Encargomío — Reglas del proyecto

Dashboard financiero y de conciliación para la línea de envíos **Miami → Colombia**.

- **Stack:** Streamlit + Python.
- **Deploy:** Streamlit Community Cloud (desde el repo público).
- **Sin base de datos.** Los datos operativos se consultan en vivo contra la API de
  ASTRID (aún no disponible). La única persistencia es un archivo Excel en Dropbox
  escrito por API.

Este documento define cómo se trabaja en el repo. Es de cumplimiento obligatorio.

---

## 1. Paso 0 — Análisis de solo lectura

**Siempre**, antes de implementar cualquier cosa: hacer un análisis de solo lectura.
Leer el código y los documentos relevantes, entender el estado actual y el impacto del
cambio **antes** de escribir o modificar nada. No se edita en el mismo paso en que se
está entendiendo el problema.

## 2. Alcance — no expandir sin instrucción explícita

**Prohibido expandir el alcance sin instrucción explícita del owner del proyecto.** No agregar
features, refactors, dependencias, archivos ni "mejoras" que no fueron pedidas.

Ante **ambigüedad**, el protocolo es exactamente:

1. **Parar.**
2. **Preguntar UNA vez** (una sola pregunta, concreta).
3. **Ejecutar** según la respuesta.

## 3. Arquitectura de datos — contra interfaces, nunca contra fuentes concretas

- Toda la lógica se construye contra **INTERFACES de datasources**
  (`datasources/base.py`, `datasources/dropbox_base.py`), nunca contra una fuente
  concreta. Las implementaciones (`*_mock.py`, `*_api.py`) son intercambiables.
- **La API de ASTRID no existe todavía.** Todo el desarrollo se hace con **mocks
  embebidos en código** (`datasources/astrid_mock.py`).
- **Nunca** usar archivos externos como fuente de datos operativos. Los datos de mock
  viven embebidos en el código, no en CSV/JSON/Excel sueltos.

## 4. Persistencia — Excel en Dropbox, append-only

- El **Excel de Dropbox es la ÚNICA persistencia** del sistema.
- Guarda dos cosas: **novedades resueltas** y **gastos reales confirmados**.
- **Append-only siempre.** No se editan ni se borran filas existentes; solo se agregan.
- El contrato de las hojas y las reglas de idempotencia están en
  [`CONTRATO_DATOS.md`](./CONTRATO_DATOS.md).

## 5. Deploy — Streamlit Community Cloud (auto-deploy desde `main`)

- El portal se despliega en **Streamlit Community Cloud** desde el **repo público**.
- **Push a `main` en GitHub → Community Cloud redespliega solo** (~1–2 min). No hay un
  remoto de deploy aparte ni un paso manual de publicación.
- Los secrets (credenciales, flags, auth) se pegan en **App settings → Secrets** de la
  app, nunca en el repo. Ver [`DEPLOY.md`](./DEPLOY.md).

## 6. Moneda y unidades de peso

- **Moneda:** USD en todo el sistema.
- **Peso:** **kg** para importación (tramo aéreo Miami → Colombia); **lb** para
  distribución nacional dentro de Colombia.

## 7. Datos reales de clientes (PII)

- **PROHIBIDO commitear archivos con datos reales de clientes** (manifiestos, exports).
- `tests/fixtures/*.xlsx` permanece en `.gitignore`.
- Los tests que dependen de fixtures reales hacen **skip** con motivo claro si el
  archivo no está (ver `tests/fixtures/README.md`).
