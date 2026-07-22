"""Configuración central del Portal de Envíos Encargomío."""

import os

# --------------------------------------------------------------------------- #
# Flags de datasource
#   DATASOURCE_ASTRID:  "mock" | "excel" | "api"
#   DATASOURCE_DROPBOX: "mock" | "real"   (persistencia y, en excel, origen de manifiestos)
#
# Se leen de variable de entorno (prioridad) O de st.secrets top-level: Streamlit
# Community Cloud carga los secrets como st.secrets (TOML), NO como env vars, así que los
# flags puestos en Secrets deben poder leerse por esta vía.
# --------------------------------------------------------------------------- #

def _flag(nombre, default=None):
    """Flag desde env var (prioridad) o st.secrets top-level; `default` si falta en ambos."""
    valor = os.environ.get(nombre)
    if valor is not None:
        return valor
    try:
        import streamlit as st  # import perezoso
        if nombre in st.secrets:
            return st.secrets[nombre]
    except Exception:
        pass
    return default


DATASOURCE_ASTRID = _flag("DATASOURCE_ASTRID", "mock")
DATASOURCE_DROPBOX = _flag("DATASOURCE_DROPBOX", "mock")

# Modo "excel" LOCAL: directorio con los exports (inyectable, para tests/dev).
EXCEL_DIRECTORIO_LOCAL = _flag("EXCEL_DIRECTORIO_LOCAL") or None

# Novedades de peso — cuando el export no trae asignación de tulas por envío, se listan
# los N envíos más pesados del manifiesto como HEURÍSTICA de sospecha (no es el contenido
# de la tula). Configurable, no hardcodeado en la vista.
TOP_N_ENVIOS_SOSPECHA = int(_flag("TOP_N_ENVIOS_SOSPECHA", "10"))

# Defaults GENÉRICOS de rutas Dropbox (las reales van en secrets [dropbox]
# manifiestos_path / excel_path, nunca en el código).
DROPBOX_MANIFIESTOS_PATH_DEFAULT = "/portal_envios"
DROPBOX_EXCEL_PATH_DEFAULT = "/portal_envios/portal/registro.xlsx"

# Excepciones legacy CERRADAS: manifiestos históricos de ANTES de fijarse la convención
# de nombres. Se incluyen pese a NO matchear el patrón estricto. Mapea nombre EXACTO de
# archivo -> (id, fecha). La lista REAL se carga por secret/env (es dato operativo); en
# el código solo queda un EJEMPLO de formato (comentado). Regla dura (en astrid_excel):
# se omite SIEMPRE cualquier archivo cuyo nombre contenga "DIAN".
# Formato del secret [manifiestos] legacy (o env MANIFIESTOS_LEGACY), JSON:
#   {"2026-01-01-900001-EJEMPLO.xlsx": ["900001", "2026-01-01"], ...}
_MANIFIESTOS_LEGACY_EJEMPLO: dict = {}


def get_manifiestos_legacy():
    """Lista de excepciones legacy real desde secret/env (JSON); si no hay, el ejemplo
    genérico (vacío). Todo archivo nuevo debe cumplir YYYY-MM-DD-<id>-ASTRID.xlsx."""
    import json
    crudo = get_secret("manifiestos", "legacy", "MANIFIESTOS_LEGACY")
    if crudo:
        try:
            data = crudo if isinstance(crudo, dict) else json.loads(crudo)
            return {k: (v[0], v[1]) for k, v in data.items()}
        except Exception:
            pass
    return dict(_MANIFIESTOS_LEGACY_EJEMPLO)


# --------------------------------------------------------------------------- #
# Secrets: forma anidada [seccion] clave, con fallback a formas planas legacy.
# Así el secrets.toml local ([dropbox]/[anthropic]) funciona tal cual, y si en
# HuggingFace Spaces los secrets se cargan planos (ANTHROPIC_API_KEY, etc.) también.
# --------------------------------------------------------------------------- #

def get_secret(seccion, clave, *nombres_legacy):
    """Devuelve el secret buscando primero st.secrets[seccion][clave] y luego las
    formas planas legacy indicadas. None si no se encuentra en ninguna forma."""
    import streamlit as st  # import perezoso

    try:
        seg = st.secrets[seccion]
        if clave in seg:
            return seg[clave]
    except Exception:
        pass
    for nombre in nombres_legacy:
        try:
            return st.secrets[nombre]
        except Exception:
            continue
    return None


def dropbox_manifiestos_path():
    return (get_secret("dropbox", "manifiestos_path", "DROPBOX_MANIFIESTOS_PATH")
            or DROPBOX_MANIFIESTOS_PATH_DEFAULT)


def dropbox_excel_path():
    return (get_secret("dropbox", "excel_path", "DROPBOX_EXCEL_PATH")
            or DROPBOX_EXCEL_PATH_DEFAULT)


# Tarifario: overrides por env/secret sobre los defaults DEMO de core.calculos.Tarifario.
# Precedencia FINAL (aplicada en dropbox_api.leer_tarifario):
#   hoja TARIFARIO (Dropbox)  >  env/secret (esto)  >  default DEMO
_TARIFARIO_ENV = {
    "imp_tarifa_kg": "TARIFA_IMP_KG",
    "imp_awb_fee": "TARIFA_IMP_AWB_FEE",
    "imp_pickup": "TARIFA_IMP_PICKUP",
    "dist_base_usd": "TARIFA_DIST_BASE_USD",
    "dist_base_lb": "TARIFA_DIST_BASE_LB",
    "dist_usd_lb_extra": "TARIFA_DIST_USD_LB_EXTRA",
    "alerta_peso_kg": "TARIFA_ALERTA_PESO_KG",
    "alerta_peso_pct": "TARIFA_ALERTA_PESO_PCT",
    "cobertura_tulas_minima": "TARIFA_COBERTURA_TULAS_MIN",
    "cobro_comercial_usd_lb": "TARIFA_COBRO_COMERCIAL_USD_LB",
    "cobro_estandar_usd_lb": "TARIFA_COBRO_ESTANDAR_USD_LB",
}


def _tarifario_overrides():
    """Overrides de tarifario por env var directa, luego secret [tarifario] <campo>."""
    overrides = {}
    for campo, var in _TARIFARIO_ENV.items():
        crudo = os.environ.get(var)
        if crudo is None:
            crudo = get_secret("tarifario", campo, var)
        if crudo is not None:
            try:
                overrides[campo] = float(crudo)
            except (TypeError, ValueError):
                pass
    return overrides


def tarifario_base():
    """Tarifario con precedencia env/secret > default DEMO. La hoja TARIFARIO de Dropbox
    (si existe) tiene aún MÁS prioridad y se aplica en dropbox_api.leer_tarifario."""
    from core.calculos import Tarifario  # perezoso (evita ciclo de import)
    return Tarifario(**_tarifario_overrides())


def cliente_dropbox():
    """Cliente Dropbox por refresh token OAuth (el SDK refresca el access token solo)."""
    import dropbox  # import perezoso

    app_key = get_secret("dropbox", "app_key", "DROPBOX_APP_KEY")
    app_secret = get_secret("dropbox", "app_secret", "DROPBOX_APP_SECRET")
    refresh_token = get_secret("dropbox", "refresh_token", "DROPBOX_REFRESH_TOKEN")
    if not (app_key and app_secret and refresh_token):
        raise RuntimeError(
            "Faltan credenciales de Dropbox en secrets: [dropbox] app_key / app_secret / "
            "refresh_token (o sus formas planas)."
        )
    return dropbox.Dropbox(app_key=app_key, app_secret=app_secret,
                           oauth2_refresh_token=refresh_token)


# --------------------------------------------------------------------------- #
# Factories de datasources
# --------------------------------------------------------------------------- #

def get_fuente_astrid():
    """Devuelve la FuenteASTRID activa según DATASOURCE_ASTRID (y DATASOURCE_DROPBOX)."""
    if DATASOURCE_ASTRID == "mock":
        from datasources.astrid_mock import FuenteASTRIDMock
        return FuenteASTRIDMock()
    if DATASOURCE_ASTRID == "excel":
        from datasources.astrid_excel import FuenteASTRIDExcel, ProveedorDropbox
        legacy = get_manifiestos_legacy()
        if EXCEL_DIRECTORIO_LOCAL:
            return FuenteASTRIDExcel(EXCEL_DIRECTORIO_LOCAL, legacy=legacy)
        if DATASOURCE_DROPBOX == "real":
            proveedor = ProveedorDropbox(cliente_dropbox(), dropbox_manifiestos_path())
            return FuenteASTRIDExcel(proveedor=proveedor, legacy=legacy)
        raise ValueError(
            "DATASOURCE_ASTRID='excel' requiere EXCEL_DIRECTORIO_LOCAL (local) o "
            "DATASOURCE_DROPBOX='real' (Dropbox)."
        )
    if DATASOURCE_ASTRID == "api":
        raise NotImplementedError(
            "La API de ASTRID aún no está disponible (ver docs/PENDIENTES_API.md)."
        )
    raise ValueError(f"DATASOURCE_ASTRID desconocido: {DATASOURCE_ASTRID!r}")


def get_fuente_dropbox():
    """Devuelve la persistencia Dropbox activa según DATASOURCE_DROPBOX."""
    if DATASOURCE_DROPBOX == "real":
        from datasources.dropbox_api import FuenteDropboxAPI
        return FuenteDropboxAPI(cliente_dropbox(), dropbox_excel_path())
    from datasources.dropbox_mock import FuenteDropboxMock
    return FuenteDropboxMock()


# --------------------------------------------------------------------------- #
# Modo parcial: mensajes de faltantes (alimentado de docs/PENDIENTES_API.md).
# --------------------------------------------------------------------------- #

REFERENCIA_HU = "HU 21/07/2026"
DEPENDENCIA_API = "API ASTRID"

PENDIENTES_API = {
    "kg_reportado": {
        "mensaje": "Pesos por tula no disponibles en el export; no se pueden calcular novedades de peso.",
        "referencia": REFERENCIA_HU, "depende": DEPENDENCIA_API},
    "valor_cobrado": {
        "mensaje": "Valor cobrado al cliente no disponible en el export; ingresos en modo solo-costos.",
        "referencia": REFERENCIA_HU, "depende": DEPENDENCIA_API},
    "tipo": {
        "mensaje": "Tipo estándar/comercial no disponible en el export.",
        "referencia": REFERENCIA_HU, "depende": DEPENDENCIA_API},
    "tula_codigo": {
        "mensaje": "Asignación de tulas incompleta en el export; total de kg calculado por envíos.",
        "referencia": REFERENCIA_HU, "depende": DEPENDENCIA_API},
    "pallets": {
        "mensaje": "Cantidad de pallets no disponible en el export.",
        "referencia": REFERENCIA_HU, "depende": DEPENDENCIA_API},
}


def mensaje_pendiente(clave):
    p = PENDIENTES_API.get(clave)
    if not p:
        return None
    return f"⚠️ Pendiente {p['depende']}: {p['mensaje']} ({p['referencia']})"
