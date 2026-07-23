"""Portal de Envíos Encargomío — dashboard financiero y de conciliación (Fase 3).

Consume el datasource ASTRID activo (config.DATASOURCE_ASTRID), el motor de cálculo
(core/calculos.py, core/conciliacion.py) y la persistencia Dropbox (dropbox_mock).

MODO PARCIAL: todo Resultado "no_disponible" del motor se muestra como banner/badge
informativo con su motivo y referencia; NUNCA se oculta una tab por falta de datos.
Los textos de faltantes salen de config.PENDIENTES_API (no se hardcodean por tab).
"""

import json
from datetime import date

import pandas as pd
import streamlit as st

import auth
import config
from core import calculos, conciliacion, modelos, vista
from core.calculos import NO_DISPONIBLE
from vision import extractor

# --------------------------------------------------------------------------- #
# Página + CSS (ejecutivo sobrio). SOLO st.markdown(unsafe_allow_html=True):
# st.html() vacía los <style> con DOMPurify.
# --------------------------------------------------------------------------- #

st.set_page_config(page_title="Portal de Envíos Encargomío", page_icon="📦", layout="wide")

_CSS = """
<style>
  /* ==========================================================================
     Sistema de diseño "Portal de Envíos · Encargomío" (tokens .pe-*).
     Fuente: guía visual HTML/CSS. Aquí los tokens visten las clases que ya
     emiten los helpers (.bloque-titulo, .metric-*, .badge*, table.exec,
     .banner*, .heuristica*) y armonizan los widgets nativos de Streamlit.
     Los widgets nativos se scopean a [data-testid="stMain"] para NO tocar el
     sidebar (que se estiliza SOLO por .streamlit/config.toml).
     ========================================================================== */
  :root {
    --pe-canvas:#eef0f3; --pe-surface:#ffffff; --pe-surface-2:#f7f8fa; --pe-surface-3:#eceef1;
    --pe-border:#dcdfe4; --pe-border-strong:#c6cbd2;
    --pe-ink:#1b1e24; --pe-ink-2:#4a515c; --pe-ink-3:#7b828d; --pe-ink-faint:#a3a9b3;
    --pe-accent:#2b4c7e; --pe-accent-ink:#1f3a63; --pe-accent-soft:#e9eef5;
    --pe-ok-ink:#1c6b45; --pe-ok-bg:#e6f4ec; --pe-ok-border:#b3ddc4;
    --pe-err-ink:#a52620; --pe-err-bg:#fbeae8; --pe-err-border:#efc2bd;
    --pe-neutral-ink:#5b636f; --pe-neutral-bg:#eceef1; --pe-neutral-border:#d3d7de;
    --pe-warn-ink:#8a5a00; --pe-warn-bg:#fbf1dd; --pe-warn-border:#ecd39a;
    --pe-heur-ink:#6a4bb0; --pe-heur-bg:#f4f1fb; --pe-heur-border:#d9cff0; --pe-heur-accent:#7c5cc4;
    --pe-radius:4px; --pe-radius-lg:6px;
    --pe-shadow:0 1px 2px rgba(21,28,40,.06), 0 1px 1px rgba(21,28,40,.04);
    --pe-mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;
  }

  /* ---- Título de sección (.pe-section__title) --------------------------- */
  .bloque-titulo { font-size: 15px; font-weight: 600; color: var(--pe-ink);
                   letter-spacing: .01em; margin: 1.5rem 0 .7rem; }

  /* ---- A) Tarjeta KPI (.pe-kpi) ----------------------------------------- */
  .metric-card { background: var(--pe-surface); border: 1px solid var(--pe-border);
                 border-radius: var(--pe-radius-lg); box-shadow: var(--pe-shadow);
                 padding: 14px 16px 16px; margin-bottom: 6px; }
  .metric-label { display: block; font-size: 11px; font-weight: 600; letter-spacing: .04em;
                  text-transform: uppercase; color: var(--pe-ink-3); margin-bottom: 10px; }
  .metric-value { font-size: 26px; font-weight: 650; line-height: 1.1; color: var(--pe-ink);
                  font-variant-numeric: tabular-nums; }
  .metric-sub { margin-top: 10px; font-size: 12px; color: var(--pe-ink-3);
                font-variant-numeric: tabular-nums; }

  /* ---- B) Badges de estado (.pe-badge) — píldora con punto de estado ---- */
  .badge { display: inline-flex; align-items: center; gap: 6px; vertical-align: middle;
           font-size: 11.5px; font-weight: 600; line-height: 1; white-space: nowrap;
           padding: 4px 9px; border-radius: 999px; border: 1px solid transparent; }
  .badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%;
                   background: currentColor; flex: none; }
  .badge-ok   { color: var(--pe-ok-ink);      background: var(--pe-ok-bg);      border-color: var(--pe-ok-border); }
  .badge-bad  { color: var(--pe-err-ink);     background: var(--pe-err-bg);     border-color: var(--pe-err-border); }
  .badge-warn { color: var(--pe-warn-ink);    background: var(--pe-warn-bg);    border-color: var(--pe-warn-border); }
  .badge-info { color: var(--pe-neutral-ink); background: var(--pe-neutral-bg); border-color: var(--pe-neutral-border); }

  /* ---- C) Tabla de datos densa (.pe-table) ------------------------------ */
  .pe-table-wrap { overflow-x: auto; border: 1px solid var(--pe-border);
                   border-radius: var(--pe-radius-lg); box-shadow: var(--pe-shadow);
                   margin: .3rem 0 .7rem; }
  table.exec { width: 100%; border-collapse: collapse; font-size: 13px; margin: 0; }
  table.exec thead th { text-align: left; font-size: 10.5px; font-weight: 700; letter-spacing: .05em;
                        text-transform: uppercase; color: var(--pe-ink-3); background: var(--pe-surface-3);
                        padding: 8px 12px; border-bottom: 1px solid var(--pe-border-strong); white-space: nowrap; }
  table.exec tbody td { padding: 9px 12px; border-bottom: 1px solid var(--pe-border);
                        color: var(--pe-ink-2); vertical-align: middle; font-variant-numeric: tabular-nums; }
  table.exec tbody tr:last-child td { border-bottom: 0; }
  table.exec tbody tr:nth-child(even) td { background: var(--pe-surface-2); }
  table.exec tbody tr:hover td { background: var(--pe-accent-soft); }

  /* ---- E) Banner informativo (.pe-banner) ------------------------------- */
  .banner { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; line-height: 1.5;
            padding: 11px 14px; border-radius: var(--pe-radius-lg); margin: .5rem 0;
            border: 1px solid transparent; }
  .banner-warn { color: var(--pe-warn-ink); background: var(--pe-warn-bg); border-color: var(--pe-warn-border); }
  .banner-info { color: var(--pe-accent-ink); background: var(--pe-accent-soft); border-color: #cdd9ea; }

  /* ---- F) Bloque heurístico (.pe-heuristic) — info NO confirmada -------- */
  .heuristica { border: 1px solid var(--pe-heur-border); border-left: 4px solid var(--pe-heur-accent);
                background: repeating-linear-gradient(135deg, transparent 0 10px, rgba(124,92,196,.03) 10px 20px),
                            var(--pe-heur-bg);
                border-radius: var(--pe-radius-lg); padding: 12px 14px; margin: .5rem 0; }
  .heuristica-titulo { font-size: 13px; font-weight: 700; color: var(--pe-heur-ink); margin-bottom: .35rem; }
  .heuristica .muted { color: var(--pe-heur-ink); opacity: .9; }
  .muted { color: var(--pe-ink-3); font-size: 12px; }

  /* ======================================================================
     Widgets nativos de Streamlit — SOLO área principal (sidebar intacto).
     ====================================================================== */
  /* Título de la app */
  [data-testid="stMain"] h1 { font-size: 1.55rem; font-weight: 650; letter-spacing: -.01em; color: var(--pe-ink); }

  /* Navegación por pestañas (.pe-tab) */
  [data-testid="stMain"] [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--pe-border); }
  [data-testid="stMain"] button[data-baseweb="tab"] { padding: 11px 16px; font-size: 13px; font-weight: 500; color: var(--pe-ink-3); }
  [data-testid="stMain"] button[data-baseweb="tab"]:hover { color: var(--pe-ink); background: transparent; }
  [data-testid="stMain"] button[data-baseweb="tab"][aria-selected="true"] { color: var(--pe-accent-ink) !important; font-weight: 600; }
  [data-testid="stMain"] [data-baseweb="tab-highlight"] { background: var(--pe-accent) !important; height: 2px; }
  [data-testid="stMain"] [data-baseweb="tab-border"] { background: transparent !important; }

  /* Expander (.pe-panel / fila expandible) */
  [data-testid="stMain"] [data-testid="stExpander"] details { border: 1px solid var(--pe-border);
      border-radius: var(--pe-radius-lg); background: var(--pe-surface); box-shadow: var(--pe-shadow); overflow: hidden; }
  [data-testid="stMain"] [data-testid="stExpander"] summary { padding: 10px 14px; font-size: 13px;
      font-weight: 600; color: var(--pe-ink-2); }
  [data-testid="stMain"] [data-testid="stExpander"] summary:hover { color: var(--pe-accent-ink); }

  /* Botones (.pe-btn): st.button = secundario bordeado; submit de forms = CTA acento */
  [data-testid="stMain"] .stButton > button, [data-testid="stMain"] .stFormSubmitButton > button {
      font-size: 13px; font-weight: 600; border-radius: var(--pe-radius); padding: 7px 14px; }
  [data-testid="stMain"] .stButton > button { color: var(--pe-ink-2) !important; background: var(--pe-surface) !important;
      border: 1px solid var(--pe-border-strong) !important; }
  [data-testid="stMain"] .stButton > button:hover { color: var(--pe-ink) !important; background: var(--pe-surface-2) !important; }
  [data-testid="stMain"] .stFormSubmitButton > button { color: #fff !important; background: var(--pe-accent) !important;
      border: 1px solid var(--pe-accent) !important; }
  [data-testid="stMain"] .stFormSubmitButton > button:hover { background: var(--pe-accent-ink) !important; border-color: var(--pe-accent-ink) !important; }

  /* G) Zona de carga (.pe-drop) — dropzone del file_uploader */
  [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] {
      border: 1.5px dashed var(--pe-border-strong) !important; border-radius: var(--pe-radius-lg) !important;
      background: var(--pe-surface-2) !important; }

  /* I) Campos de formulario (.pe-input/.pe-select/.pe-textarea) */
  [data-testid="stMain"] div[data-baseweb="input"],
  [data-testid="stMain"] div[data-baseweb="textarea"],
  [data-testid="stMain"] div[data-baseweb="select"] > div {
      border-color: var(--pe-border-strong) !important; border-radius: var(--pe-radius) !important;
      background-color: var(--pe-surface) !important; }
  [data-testid="stMain"] div[data-baseweb="input"]:focus-within,
  [data-testid="stMain"] div[data-baseweb="textarea"]:focus-within,
  [data-testid="stMain"] div[data-baseweb="select"] > div:focus-within {
      border-color: var(--pe-accent) !important; box-shadow: 0 0 0 3px var(--pe-accent-soft) !important; }
  [data-testid="stMain"] .stCheckbox input { accent-color: var(--pe-accent); }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

# Gate de autenticación (detiene si no está autenticado; None = modo abierto con aviso).
# Devuelve (usuario, rol): el rol gatea TODO el render (aislamiento del proveedor).
usuario_auth, rol_auth = auth.proteger()


# --------------------------------------------------------------------------- #
# Fuentes (singletons) y lecturas cacheadas
# --------------------------------------------------------------------------- #

@st.cache_resource
def _fuente_astrid():
    return config.get_fuente_astrid()


@st.cache_resource
def _fuente_dropbox():
    return config.get_fuente_dropbox()


@st.cache_data(ttl=600)
def cargar_resumenes(desde, hasta):
    return _fuente_astrid().get_manifiestos(desde, hasta)


@st.cache_data(ttl=600)
def cargar_manifiesto(mid):
    return _fuente_astrid().get_manifiesto(mid)


@st.cache_data(ttl=600)
def cargar_novedades():
    return _fuente_dropbox().leer_novedades()


@st.cache_data(ttl=600)
def cargar_gastos():
    return _fuente_dropbox().leer_gastos_reales()


@st.cache_data(ttl=600)
def cargar_cobros():
    return _fuente_dropbox().leer_cobros_distribucion()


@st.cache_data(ttl=600)
def cargar_tarifario():
    return _fuente_dropbox().leer_tarifario()


@st.cache_data(ttl=600)
def cargar_tulas_reportadas():
    return _fuente_dropbox().leer_tulas_reportadas()


@st.cache_data(ttl=600)
def cargar_pagos():
    return _fuente_dropbox().leer_pagos()


@st.cache_data(ttl=600)
def cargar_consolidaciones():
    return _fuente_dropbox().leer_consolidaciones()


@st.cache_data(ttl=600)
def cargar_reajustes():
    return _fuente_dropbox().leer_reajustes()


# --------------------------------------------------------------------------- #
# Helpers de presentación
# --------------------------------------------------------------------------- #

def _usd(x):
    return "—" if x is None else f"${x:,.2f}"


def _num(x, suf=""):
    return "—" if x is None else f"{x:,.2f}{suf}"


def _pct(x):
    return "—" if x is None else f"{x:,.1f}%"


_BADGES = {
    "conciliado": ("badge-ok", "conciliado"),
    "discrepancia": ("badge-bad", "discrepancia"),
    "sin_factura": ("badge-warn", "sin factura"),
    "sin_cobro": ("badge-warn", "sin cobro"),
    "no_disponible": ("badge-warn", "sin datos"),
    "alerta": ("badge-bad", "alerta"),
    "ok": ("badge-ok", "ok"),
    "resuelta": ("badge-ok", "resuelta"),
    "parcial": ("badge-warn", "parcial"),
    "completo": ("badge-ok", "completo"),
}


def badge(estado):
    cls, txt = _BADGES.get(estado, ("badge-info", str(estado)))
    return f'<span class="badge {cls}">{txt}</span>'


def badge_info(texto):
    return f'<span class="badge badge-info">{texto}</span>'


def banner(texto, tono="warn"):
    st.markdown(f'<div class="banner banner-{tono}">{texto}</div>', unsafe_allow_html=True)


def _leer_dropbox(fn, default, etiqueta):
    """Lectura resiliente de Dropbox: si falla, advertencia visible y se continúa en
    solo-lectura con `default` (el resto del dashboard sigue operando)."""
    try:
        return fn()
    except Exception as exc:
        banner(f"⚠️ No se pudo leer {etiqueta} desde Dropbox: {exc}. "
               f"El portal sigue en solo-lectura con lo disponible.", "warn")
        return default


def tarjeta(col, label, value, sub=None):
    extra = f'<div class="metric-sub">{sub}</div>' if sub else ""
    col.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>{extra}</div>',
        unsafe_allow_html=True,
    )


def _tabla_html(cols, filas):
    th = "".join(f"<th>{c}</th>" for c in cols)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in filas)
    return ('<div class="pe-table-wrap"><table class="exec">'
            f'<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')


def tabla(cols, filas):
    if not filas:
        st.caption("Sin filas.")
        return
    st.markdown(_tabla_html(cols, filas), unsafe_allow_html=True)


def _fuente_kg_texto(fuente):
    if fuente == "tulas":
        return badge_info("total por tulas")
    if fuente == "envios":
        return badge_info("total por envíos — asignación incompleta")
    return ""


def _render_conciliacion(r):
    """Presenta la conciliación de importación como DOS CAMINOS: peso (aerolínea vs
    báscula) y cobro (tarifa + cargos). Los estados generales no cambian; cambia la
    semántica de presentación."""
    for adv in r.get("advertencias", []):
        banner(f"⚠️ {adv}", "warn")
    st.markdown(badge_info(f"confianza: {r.get('nivel_confianza')}"), unsafe_allow_html=True)

    comp = r["componentes"]
    kg_cob = comp["peso"]["kg_cobrados"]

    # Camino 1 — Peso: aerolínea vs mi báscula (verificable solo con peso de báscula).
    st.markdown("**⚖️ Peso: aerolínea vs mi báscula**")
    kg_rep = r.get("kg_reportado")
    if kg_rep is not None:
        fuente = r.get("fuente_kg_reportado")
        etiqueta = {"tulas": "tulas del datasource",
                    "tulas_reportadas": "tulas registradas (pantallazo)"}.get(fuente, fuente or "báscula")
        tabla(["", "kg"],
              [["Facturados (aerolínea)", _num(kg_cob)],
               [f"Báscula ({etiqueta})", _num(kg_rep)],
               ["Diferencia", _num(round(kg_cob - kg_rep, 2))]])
    else:
        banner("No verificable — sin pesos de tula registrados (subilos en la tab "
               "⚖️ Novedades de Peso o esperá la API de ASTRID).", "warn")
    # Referencia secundaria: vs peso digitado (kg_sistema). NUNCA es verificación de báscula.
    if r.get("kg_sistema") is not None:
        st.caption("Referencia (no es verificación de báscula) — vs peso digitado "
                   f"(kg_sistema {_num(r['kg_sistema'])}): dif {_num(round(kg_cob - r['kg_sistema'], 2))}")

    # Camino 2 — Cobro: tarifa + cargos fijos (SIEMPRE verificable, con o sin báscula).
    st.markdown("**💲 Cobro: tarifa y cargos**")
    tarifa, cargos = comp["tarifa"], comp["cargos_fijos"]
    tabla(["Concepto", "Impacto USD", "Detalle"],
          [["Tarifa", _usd(tarifa["impacto_usd"]),
            f"factura {tarifa['tarifa_factura']} vs pactada {tarifa['tarifa_pactada']} ({tarifa['direccion']})"],
           ["Cargos fijos", _usd(cargos["impacto_usd"]),
            f"factura {_usd(cargos['factura_cargos'])} vs tarifario {_usd(cargos['tarifario_cargos'])}"]])


# --------------------------------------------------------------------------- #
# Novedades: cruce por llave de idempotencia + bloque "Justificar"
# --------------------------------------------------------------------------- #

ACCIONES = ["Aceptar cargo", "Reclamar a proveedor", "Ajuste interno", "Registrar y monitorear"]


def _novedad_resuelta(novedades, manifiesto_id, discriminador, tipo):
    for n in novedades:
        disc = n.get("tula_codigo") or n.get("guia")
        if (n.get("manifiesto_id"), disc, n.get("tipo")) == (manifiesto_id, discriminador, tipo):
            return n
    return None


def bloque_justificar(*, novedades, usuario, manifiesto_id, tipo, discriminador, campo_disc,
                      valor_esperado, valor_real, delta):
    """Muestra el estado de la novedad: badge 'resuelta' o form para justificar."""
    resuelta = _novedad_resuelta(novedades, manifiesto_id, discriminador, tipo)
    if resuelta:
        st.markdown(
            badge("resuelta") + f' <span class="muted">por {resuelta.get("usuario", "?")} · '
            f'{resuelta.get("fecha", "")}</span>', unsafe_allow_html=True)
        if resuelta.get("justificacion"):
            st.caption(f'“{resuelta["justificacion"]}” — acción: {resuelta.get("accion", "")}')
        return

    key = f"just_{tipo}_{manifiesto_id}_{discriminador}"
    with st.form(key=key):
        st.markdown("**Justificar novedad**")
        justificacion = st.text_area("Justificación", key=key + "_j")
        accion = st.selectbox("Acción", ACCIONES, key=key + "_a")
        if st.form_submit_button("Guardar novedad"):
            # El usuario logueado (o de sesión) queda registrado en la novedad.
            novedad = modelos.construir_novedad(
                usuario=usuario, manifiesto_id=manifiesto_id, tipo=tipo,
                discriminador=discriminador, campo_disc=campo_disc,
                valor_esperado=valor_esperado, valor_real=valor_real, delta=delta,
                justificacion=justificacion, accion=accion)
            try:
                agregada = _fuente_dropbox().agregar_novedad(novedad)
            except Exception as exc:
                st.error(f"No se pudo guardar en Dropbox: {exc}. Tu justificación no se "
                         f"perdió: «{justificacion}» · acción: {accion}. Reintentá.")
                return
            cargar_novedades.clear()  # invalidar SOLO novedades
            if agregada:
                st.success("Novedad registrada.")
            else:
                st.warning("Ya existía una novedad para esta llave.")
            st.rerun()


# --------------------------------------------------------------------------- #
# Visión: extracción de facturas y pantallazos de tulas (API Anthropic)
# --------------------------------------------------------------------------- #

def _panel_datos_extraidos(datos):
    """Muestra SIEMPRE los datos clave extraídos para que el humano compare contra el
    documento antes de firmar (Confirmar gasto es la firma del usuario)."""
    tabla(["Campo", "Valor extraído"], [
        ["N° factura", datos.get("numero_factura")],
        ["Fecha", datos.get("fecha")],
        ["AWB", datos.get("awb")],
        ["kg cobrados", datos.get("kg_cobrados")],
        ["Tarifa/kg USD", datos.get("tarifa_kg_usd")],
        ["AWB fee USD", datos.get("awb_fee_usd")],
        ["Pickup/entrega USD", datos.get("pickup_entrega_usd")],
        ["Otros cargos", datos.get("otros_cargos")],
        ["TOTAL USD", datos.get("total_usd")],
    ])


def _form_corregir_factura(datos):
    with st.form("form_corregir_factura"):
        st.write("Corregí los campos y revalidá (no se registra sin cuadre):")
        kg = st.number_input("kg_cobrados", value=float(datos.get("kg_cobrados") or 0.0), format="%.2f")
        tarifa = st.number_input("tarifa_kg_usd", value=float(datos.get("tarifa_kg_usd") or 0.0), format="%.4f")
        awb_fee = st.number_input("awb_fee_usd", value=float(datos.get("awb_fee_usd") or 0.0), format="%.2f")
        pickup = st.number_input("pickup_entrega_usd", value=float(datos.get("pickup_entrega_usd") or 0.0), format="%.2f")
        total = st.number_input("total_usd", value=float(datos.get("total_usd") or 0.0), format="%.2f")
        awb = st.text_input("awb", value=datos.get("awb") or "")
        numero = st.text_input("numero_factura", value=datos.get("numero_factura") or "")
        if st.form_submit_button("Recalcular / revalidar"):
            datos.update({
                "kg_cobrados": kg, "tarifa_kg_usd": tarifa, "awb_fee_usd": awb_fee,
                "pickup_entrega_usd": pickup, "total_usd": total,
                "awb": awb or None, "numero_factura": numero or None,
            })
            st.session_state["factura_extraida"] = datos
            st.rerun()


def _flujo_confirmar_factura(datos, manifiestos, tarifario, usuario, tulas_reportadas):
    st.markdown('<div class="bloque-titulo">Datos extraídos (verificá contra el documento)</div>',
                unsafe_allow_html=True)
    _panel_datos_extraidos(datos)

    cuadra, motivos = extractor.validar_factura(datos)
    if not cuadra:
        for m in motivos:
            banner(f"⚠️ No cuadra / ilegible: {m}", "warn")
        banner("PROHIBIDO registrar sin cuadre. Corregí los campos abajo.", "warn")
        _form_corregir_factura(datos)
        st.markdown("**JSON crudo extraído:**")
        st.code(json.dumps(datos, ensure_ascii=False, indent=2))
        return

    # Match por AWB: datasource -> tulas_reportadas -> manual. Conflicto si difieren.
    match = conciliacion.match_manifiesto_por_awb(datos.get("awb"), manifiestos, tulas_reportadas)
    if match["estado"] == "unico":
        m = match["manifiesto"]
        st.success(f"Match por AWB {datos.get('awb')} → manifiesto {m['id']} (vía {match['via']})")
    elif match["estado"] == "conflicto":
        banner("Conflicto: el AWB matchea manifiestos DISTINTOS (datasource vs. tulas "
               "registradas). Elegí manualmente cuál corresponde.", "warn")
        etiqueta = st.selectbox("Candidatos en conflicto",
                                [f"{x['id']} · {x['fecha']}" for x in match["candidatos"]],
                                key="sel_manif_conflicto")
        m = next(x for x in match["candidatos"] if etiqueta.startswith(x["id"]))
    else:
        banner("Sin match por AWB (ni datasource ni tulas registradas). Seleccioná manualmente.", "info")
        etiqueta = st.selectbox("Manifiesto", [f"{x['id']} · {x['fecha']}" for x in manifiestos],
                                key="sel_manif_factura")
        m = next(x for x in manifiestos if etiqueta.startswith(x["id"]))

    factura = {
        "numero": datos.get("numero_factura"), "kg_cobrados": datos["kg_cobrados"],
        "tarifa_kg_usd": datos["tarifa_kg_usd"], "awb_fee_usd": datos["awb_fee_usd"],
        "pickup_entrega_usd": datos["pickup_entrega_usd"],
        "otros_cargos": datos.get("otros_cargos") or [], "total_usd": datos["total_usd"],
    }
    r = conciliacion.conciliar_importacion(m, factura, tarifario, tulas_reportadas)
    cc = st.columns(3)
    tarjeta(cc[0], "Esperado", _usd(r.get("esperado_usd")))
    tarjeta(cc[1], "Cobrado (factura)", _usd(datos["total_usd"]))
    tarjeta(cc[2], "Delta", _usd(r.get("delta_total")))
    st.markdown(badge(r["estado"]), unsafe_allow_html=True)
    _render_conciliacion(r)

    if st.button("✍️ Confirmar gasto", key="btn_confirmar_gasto"):
        gasto = extractor.gasto_real_desde_factura(datos, m["id"], origen="vision")
        try:
            agregada = _fuente_dropbox().agregar_gasto_real(gasto)
        except Exception as exc:
            st.error(f"No se pudo registrar el gasto en Dropbox: {exc}. Los datos "
                     f"extraídos siguen cargados; reintentá 'Confirmar gasto'.")
            return  # no se limpia session_state: la factura queda para reintentar
        cargar_gastos.clear()
        if agregada:
            st.success("Gasto registrado (origen visión). P&L y conciliación actualizados.")
        else:
            st.warning("Factura ya registrada (idempotencia por manifiesto+concepto+referencia).")
        st.session_state.pop("factura_extraida", None)
        st.rerun()


def _seccion_vision_factura(manifiestos, tarifario, usuario, tulas_reportadas):
    st.divider()
    st.markdown('<div class="bloque-titulo">Cargar factura por visión (API Anthropic)</div>',
                unsafe_allow_html=True)
    archivo = st.file_uploader("Factura de aerolínea (pdf/png/jpg)",
                               type=["pdf", "png", "jpg", "jpeg"], key="up_factura")
    if archivo is not None and st.button("Extraer factura", key="btn_extraer_factura"):
        with st.spinner("Extrayendo con visión…"):
            try:
                imgs = extractor.preparar(archivo.name, archivo.getvalue())
                st.session_state["factura_extraida"] = extractor.extraer(imgs, "factura_aerolinea")
            except Exception as exc:
                st.error(f"No se pudo extraer: {exc}")
    datos = st.session_state.get("factura_extraida")
    if datos:
        _flujo_confirmar_factura(datos, manifiestos, tarifario, usuario, tulas_reportadas)


def _flujo_registrar_tulas(datos, manifiestos, usuario):
    st.markdown('<div class="bloque-titulo">Datos extraídos (verificá contra la pantalla)</div>',
                unsafe_allow_html=True)
    st.write(f"manifiesto_id: **{datos.get('manifiesto_id')}** · "
             f"piezas: **{datos.get('piezas')}** · total_kg: **{datos.get('total_kg')}**")
    tabla(["Tula", "kg reportado"], [[t.get("numero"), t.get("kg_reportado")]
                                     for t in (datos.get("tulas") or [])])

    cuadra, motivos = extractor.validar_tulas(datos)
    if not cuadra:
        for m in motivos:
            banner(f"⚠️ {m}", "warn")
        st.code(json.dumps(datos, ensure_ascii=False, indent=2))
        with st.form("form_corregir_tulas"):
            total = st.number_input("total_kg", value=float(datos.get("total_kg") or 0.0), format="%.2f")
            piezas = st.number_input("piezas",
                                     value=int(datos.get("piezas") or len(datos.get("tulas") or [])), step=1)
            if st.form_submit_button("Revalidar"):
                datos.update({"total_kg": total, "piezas": int(piezas)})
                st.session_state["tulas_extraidas"] = datos
                st.rerun()
        return

    # Asociar a manifiesto (por manifiesto_id extraído, con selector de respaldo).
    mid = datos.get("manifiesto_id")
    ids = [x["id"] for x in manifiestos]
    if mid in ids:
        m = next(x for x in manifiestos if x["id"] == mid)
        st.success(f"Asociado al manifiesto {mid} (extraído).")
    else:
        banner("El manifiesto_id extraído no está en el período. Seleccioná manualmente.", "info")
        etiqueta = st.selectbox("Manifiesto", [f"{x['id']} · {x['fecha']}" for x in manifiestos],
                                key="sel_manif_tulas")
        m = next(x for x in manifiestos if etiqueta.startswith(x["id"]))
        mid = m["id"]

    # ¿Hay kg_sistema por tula para comparar?
    sistema = {t.get("numero"): t.get("kg_sistema") for t in m.get("tulas", [])
               if t.get("numero") is not None and t.get("kg_sistema") is not None}
    if sistema:
        st.markdown("**Novedades (reportado por visión vs. kg de sistema):**")
        tabla(["Tula", "kg sistema", "kg reportado", "dif"],
              [[t["numero"], _num(sistema.get(t["numero"])), _num(t["kg_reportado"]),
                _num(round(t["kg_reportado"] - sistema[t["numero"]], 2)) if t["numero"] in sistema else "—"]
               for t in datos["tulas"]])
    else:
        banner(config.mensaje_pendiente("kg_reportado")
               + " — se muestran solo los pesos reportados por visión.", "warn")

    if st.button("Registrar pesos", key="btn_registrar_tulas"):
        try:
            n = 0
            for t in datos["tulas"]:
                registro = {"manifiesto_id": mid, "numero_tula": t["numero"],
                            "kg_reportado": t["kg_reportado"], "awb_master": datos.get("awb_master"),
                            "fecha": date.today().isoformat(), "usuario": usuario, "origen": "vision"}
                if _fuente_dropbox().agregar_tulas_reportadas(registro):
                    n += 1
        except Exception as exc:
            st.error(f"No se pudo registrar en Dropbox: {exc}. Los datos siguen "
                     f"cargados; reintentá 'Registrar pesos' (es idempotente).")
            return  # no se limpia session_state
        cargar_tulas_reportadas.clear()
        st.success(f"{n} tula(s) registradas (idempotente por manifiesto+tula).")
        st.session_state.pop("tulas_extraidas", None)
        st.rerun()


def _seccion_vision_tulas(manifiestos, usuario):
    st.divider()
    st.markdown('<div class="bloque-titulo">Cargar pantallazo de tulas por visión (API Anthropic)</div>',
                unsafe_allow_html=True)
    st.caption("Adelanto provisional mientras la API de ASTRID no trae pesos por tula "
               f"({config.REFERENCIA_HU}).")
    archivo = st.file_uploader("Pantalla de tulas (imagen/pdf)",
                               type=["png", "jpg", "jpeg", "pdf"], key="up_tulas")
    if archivo is not None and st.button("Extraer tulas", key="btn_extraer_tulas"):
        with st.spinner("Extrayendo con visión…"):
            try:
                imgs = extractor.preparar(archivo.name, archivo.getvalue())
                st.session_state["tulas_extraidas"] = extractor.extraer(imgs, "pantalla_tulas")
            except Exception as exc:
                st.error(f"No se pudo extraer: {exc}")
    datos = st.session_state.get("tulas_extraidas")
    if datos:
        _flujo_registrar_tulas(datos, manifiestos, usuario)


# --------------------------------------------------------------------------- #
# Estado de pago: badges, registro de pago (comprobante por visión) y comprobante
# --------------------------------------------------------------------------- #

def _badge_pago(gasto):
    """Badge del estado de pago EFECTIVO del gasto (pendiente/pagado/vencido)."""
    efectivo = calculos.estado_pago_efectivo(gasto)
    cls = {"pagado": "badge-ok", "vencido": "badge-bad"}.get(efectivo, "badge-warn")
    return f'<span class="badge {cls}">{efectivo}</span>'


def _clave_gasto_str(g):
    return f"{g.get('manifiesto_id')}|{g.get('concepto')}|{g.get('referencia')}"


def _ver_comprobante(gasto):
    """Muestra la imagen del comprobante de pago (si hay), leída de Dropbox."""
    ref = gasto.get("comprobante_ref")
    if not ref:
        return
    try:
        data = _fuente_dropbox().leer_archivo(ref)
    except Exception as exc:
        st.caption(f"Comprobante registrado ({ref}) — no se pudo leer: {exc}")
        return
    if str(ref).lower().endswith(".pdf"):
        st.caption(f"Comprobante (PDF) registrado: {ref}")
    else:
        try:
            st.image(data, caption="Comprobante de transferencia", width=340)
        except Exception:
            st.caption(f"Comprobante registrado: {ref}")


def _registrar_pago(gasto, usuario):
    """Sube comprobante → visión → valida contra el total de la factura (avisa, no
    bloquea) → confirma → escribe fila PAGO (append-only) + archivo en Dropbox."""
    key = "pago_" + _clave_gasto_str(gasto)
    up = st.file_uploader("Comprobante de transferencia (pdf/imagen)",
                          type=["pdf", "png", "jpg", "jpeg"], key=key + "_up")
    if up is not None and st.button("Extraer comprobante", key=key + "_ext"):
        with st.spinner("Extrayendo con visión…"):
            try:
                imgs = extractor.preparar(up.name, up.getvalue())
                st.session_state[key + "_datos"] = extractor.extraer(imgs, "comprobante_transferencia")
                st.session_state[key + "_arch"] = (up.name, up.getvalue())
            except Exception as exc:
                st.error(f"No se pudo extraer: {exc}")
    datos = st.session_state.get(key + "_datos")
    if not datos:
        return

    tabla(["Campo", "Valor extraído"], [
        ["Fecha", datos.get("fecha")], ["Monto", datos.get("monto")],
        ["Referencia", datos.get("referencia")], ["Banco", datos.get("banco")],
        ["Destinatario", datos.get("destinatario")]])
    cuadra, avisos = extractor.validar_comprobante(datos, gasto.get("total_usd"))
    for a in avisos:
        banner(f"⚠️ {a}", "warn")
    if not cuadra:
        with st.form(key + "_form"):
            monto = st.number_input("Monto (corregir)", value=0.0, format="%.2f")
            ref = st.text_input("Referencia", value=datos.get("referencia") or "")
            if st.form_submit_button("Revalidar"):
                datos.update({"monto": monto, "referencia": ref or None})
                st.session_state[key + "_datos"] = datos
                st.rerun()
        return

    if st.button("✍️ Confirmar pago", key=key + "_ok"):
        comp_ref = None
        try:
            arch = st.session_state.get(key + "_arch")
            if arch is not None:
                nombre, contenido = arch
                comp_ref = _fuente_dropbox().guardar_archivo(
                    "comprobantes", f"{_clave_gasto_str(gasto)}-{nombre}".replace("|", "_"), contenido)
            pago = modelos.construir_pago(
                gasto=gasto, monto_usd=datos.get("monto"),
                referencia_pago=datos.get("referencia"), usuario=usuario,
                banco=datos.get("banco"), destinatario=datos.get("destinatario"),
                comprobante_ref=comp_ref)
            ok = _fuente_dropbox().agregar_pago(pago)
        except Exception as exc:
            st.error(f"No se pudo registrar el pago en Dropbox: {exc}. Reintentá.")
            return
        cargar_pagos.clear()
        st.success("Pago registrado." if ok else "Pago ya registrado (idempotente).")
        for suf in ("_datos", "_arch"):
            st.session_state.pop(key + suf, None)
        st.rerun()


def _seccion_estado_pago(gastos, concepto, entidad, usuario):
    """Estado de pago de los gastos de un concepto: totales + fila por gasto con badge,
    'Registrar pago' (si no está pagado) y comprobante (si está pagado)."""
    sub = [g for g in gastos if g.get("concepto") == concepto]
    cp = vista.cuentas_por_pagar(sub)
    cols = st.columns(4)
    tarjeta(cols[0], "Facturado", _usd(cp["facturado_usd"]))
    tarjeta(cols[1], "Pagado", _usd(cp["pagado_usd"]))
    tarjeta(cols[2], "Pendiente", _usd(cp["pendiente_total_usd"]))
    tarjeta(cols[3], "Vencido", _usd(cp["vencido_usd"]),
            sub=(f"{cp['n_vencidas']} factura(s)" if cp["n_vencidas"] else None))
    if not sub:
        banner(f"Sin facturas de {entidad} registradas todavía.", "info")
        return
    for g in sorted(sub, key=lambda x: str(x.get("fecha"))):
        efectivo = calculos.estado_pago_efectivo(g)
        titulo = (f"{g.get('referencia') or '—'} · {g.get('manifiesto_id')} · "
                  f"{_usd(g.get('total_usd'))} · venc: {g.get('fecha_vencimiento') or '—'}")
        with st.expander(titulo, expanded=(efectivo == "vencido")):
            st.markdown(_badge_pago(g), unsafe_allow_html=True)
            if efectivo == "pagado":
                st.caption(f"Pagado el {g.get('fecha_pago') or '—'} · ref: "
                           f"{g.get('referencia_pago') or '—'}")
                _ver_comprobante(g)
            else:
                _registrar_pago(g, usuario)


# --------------------------------------------------------------------------- #
# Consolidaciones (despacho nacional): listado, ahorro y alta manual (admin)
# --------------------------------------------------------------------------- #

def _seccion_consolidaciones(manifiestos, tarifario, consolidados, usuario):
    st.markdown('<div class="bloque-titulo">Despachos consolidados (varias guías en un despacho)</div>',
                unsafe_allow_html=True)
    por_id = {m["id"]: m for m in manifiestos}
    agg = vista.ahorro_consolidados(consolidados, manifiestos, tarifario)
    if consolidados:
        cc = st.columns(3)
        tarjeta(cc[0], "Costo individual (suma)", _usd(agg["individual_usd"]))
        tarjeta(cc[1], "Costo consolidado", _usd(agg["consolidado_usd"]))
        tarjeta(cc[2], "Ahorro por consolidar", _usd(agg["ahorro_usd"]))
        for c in consolidados:
            r = conciliacion.conciliar_consolidado(c, por_id.get(c.get("manifiesto_id")), tarifario)
            with st.expander(f"{c.get('consolidado_id')} · {c.get('manifiesto_id')} · "
                             f"{len(c.get('guias') or [])} guías · {r['estado']}",
                             expanded=(r["estado"] == "discrepancia")):
                for adv in r.get("advertencias", []):
                    banner(f"⚠️ {adv}", "warn")
                col = st.columns(4)
                tarjeta(col[0], "Esperado (peso total)", _usd(r.get("esperado_usd")))
                tarjeta(col[1], "Cobrado ASTRID", _usd(r.get("valor_cobrado_usd")))
                tarjeta(col[2], "Diferencia", _usd(r.get("delta")))
                tarjeta(col[3], "Ahorro", _usd(r.get("ahorro_usd")))
                st.caption(f"Peso total: {_num(c.get('peso_total_lb'), ' lb')} · "
                           f"guías: {', '.join(str(g) for g in (c.get('guias') or []))}")
    else:
        st.caption("Sin despachos consolidados registrados.")

    with st.expander("➕ Registrar consolidación manual"):
        _form_consolidado_manual(manifiestos, consolidados, usuario)


def _form_consolidado_manual(manifiestos, consolidados, usuario):
    etiqueta = st.selectbox("Manifiesto", [f"{m['id']} · {m['fecha']}" for m in manifiestos],
                            key="cons_manif")
    m = next(x for x in manifiestos if etiqueta.startswith(x["id"]))
    guias = [e.get("guia") for e in m.get("envios", []) if e.get("guia")]
    n_previos = sum(1 for c in consolidados if c.get("manifiesto_id") == m["id"])
    with st.form("form_consolidado"):
        cid = st.text_input("ID de consolidación", value=f"CONS-{m['id']}-{n_previos + 1:02d}")
        sel = st.multiselect("Guías incluidas", guias, key="cons_guias")
        peso = st.number_input("Peso total consolidado (lb)", min_value=0.0, format="%.2f")
        valor = st.number_input("Valor cobrado (USD)", min_value=0.0, format="%.2f")
        transp = st.text_input("Transportadora", value="")
        if st.form_submit_button("Guardar consolidación"):
            if not sel:
                st.warning("Seleccioná al menos una guía.")
                return
            consol = modelos.construir_consolidado(
                consolidado_id=cid, manifiesto_id=m["id"], guias=sel,
                peso_total_lb=peso, valor_cobrado_usd=valor, transportadora=transp or None)
            try:
                ok = _fuente_dropbox().agregar_consolidado(consol)
            except Exception as exc:
                st.error(f"No se pudo guardar en Dropbox: {exc}. Reintentá.")
                return
            cargar_consolidaciones.clear()
            st.success("Consolidación registrada." if ok else "Ya existía (idempotente).")
            st.rerun()


# --------------------------------------------------------------------------- #
# Factura de despacho por visión (proveedor o admin) → CobroDistribucion + GastoReal
# --------------------------------------------------------------------------- #

def _seccion_vision_despacho(usuario, *, proveedor=False, manifiestos=None):
    st.markdown('<div class="bloque-titulo">Cargar factura de despacho (API Anthropic)</div>',
                unsafe_allow_html=True)
    archivo = st.file_uploader("Factura de despacho ASTRID (pdf/png/jpg)",
                               type=["pdf", "png", "jpg", "jpeg"], key="up_despacho")
    if archivo is not None and st.button("Extraer factura de despacho", key="btn_ext_despacho"):
        with st.spinner("Extrayendo con visión…"):
            try:
                imgs = extractor.preparar(archivo.name, archivo.getvalue())
                st.session_state["despacho_extraido"] = extractor.extraer(imgs, "factura_despacho")
            except Exception as exc:
                st.error(f"No se pudo extraer: {exc}")
    datos = st.session_state.get("despacho_extraido")
    if not datos:
        return

    tabla(["Campo", "Valor extraído"], [
        ["N° factura", datos.get("numero_factura")], ["Fecha", datos.get("fecha")],
        ["Manifiesto", datos.get("manifiesto_id")], ["Guía", datos.get("guia")],
        ["Valor guía USD", datos.get("valor_usd")], ["TOTAL USD", datos.get("total_usd")],
        ["Vencimiento", datos.get("fecha_vencimiento")], ["Términos", datos.get("terminos_pago")]])

    cuadra, motivos = extractor.validar_despacho(datos)
    if not cuadra:
        for mo in motivos:
            banner(f"⚠️ {mo}", "warn")
        with st.form("form_despacho"):
            total = st.number_input("total_usd", value=0.0, format="%.2f")
            if st.form_submit_button("Revalidar"):
                datos["total_usd"] = total
                st.session_state["despacho_extraido"] = datos
                st.rerun()
        return

    # Manifiesto: del documento (o selector si es admin y no vino / no matchea).
    mid = datos.get("manifiesto_id")
    if not proveedor and manifiestos:
        ids = [x["id"] for x in manifiestos]
        if mid not in ids:
            banner("Manifiesto no reconocido en el período. Seleccioná manualmente.", "info")
            etiqueta = st.selectbox("Manifiesto", [f"{x['id']} · {x['fecha']}" for x in manifiestos],
                                    key="sel_manif_despacho")
            mid = next(x["id"] for x in manifiestos if etiqueta.startswith(x["id"]))
    elif proveedor and not mid:
        mid = st.text_input("ID de manifiesto (no vino en el documento)", value="", key="prov_mid") or None

    if st.button("✍️ Confirmar factura de despacho", key="btn_conf_despacho"):
        if not mid:
            st.warning("Falta el manifiesto de la factura.")
            return
        try:
            gasto = extractor.gasto_real_desde_despacho(datos, mid, usuario=usuario)
            ok = _fuente_dropbox().agregar_gasto_real(gasto)
            # Si la factura es de una sola guía, registrar también el CobroDistribucion.
            if datos.get("guia") and datos.get("valor_usd") is not None:
                _fuente_dropbox().agregar_cobro_distribucion({
                    "guia": datos["guia"], "manifiesto_id": mid, "transportadora": "ASTRID",
                    "lb_facturadas": datos.get("lb_facturadas"), "valor_usd": datos["valor_usd"]})
        except Exception as exc:
            st.error(f"No se pudo registrar en Dropbox: {exc}. Reintentá.")
            return
        cargar_gastos.clear()
        cargar_cobros.clear()
        st.success("Factura de despacho registrada (pendiente de pago)." if ok
                   else "Factura de despacho ya registrada (idempotente).")
        st.session_state.pop("despacho_extraido", None)
        st.rerun()


# --------------------------------------------------------------------------- #
# Reajustes (recepción + archivo; formato desconocido → extractor genérico)
# --------------------------------------------------------------------------- #

def _seccion_vision_reajuste(usuario):
    st.markdown('<div class="bloque-titulo">Cargar reajuste (recepción y archivo)</div>',
                unsafe_allow_html=True)
    st.caption("Formato desconocido: la extracción es best-effort (puede quedar en null). "
               "Solo se archiva el documento y se registra lo extraído (editable).")
    archivo = st.file_uploader("Documento de reajuste (pdf/png/jpg)",
                               type=["pdf", "png", "jpg", "jpeg"], key="up_reajuste")
    if archivo is not None and st.button("Extraer reajuste", key="btn_ext_reajuste"):
        with st.spinner("Extrayendo con visión…"):
            try:
                imgs = extractor.preparar(archivo.name, archivo.getvalue())
                st.session_state["reajuste_extraido"] = extractor.extraer(imgs, "reajuste")
                st.session_state["reajuste_arch"] = (archivo.name, archivo.getvalue())
            except Exception as exc:
                st.error(f"No se pudo extraer: {exc}")
    datos = st.session_state.get("reajuste_extraido")
    if not datos:
        return
    st.markdown("**Campos extraídos (editables — la extracción es imprecisa):**")
    with st.form("form_reajuste"):
        mid = st.text_input("manifiesto_id", value=datos.get("manifiesto_id") or "")
        guia = st.text_input("guia", value=datos.get("guia") or "")
        valor = st.text_input("valor_usd", value=str(datos.get("valor_usd") or ""))
        motivo = st.text_input("motivo", value=datos.get("motivo") or "")
        resumen = st.text_area("texto_resumen", value=datos.get("texto_resumen") or "")
        if st.form_submit_button("Archivar reajuste"):
            try:
                nombre, contenido = st.session_state.get("reajuste_arch", ("reajuste", b""))
                ruta = _fuente_dropbox().guardar_archivo("reajustes", f"{mid or 'sin_manif'}-{nombre}", contenido)
                try:
                    valor_num = float(valor) if str(valor).strip() else None
                except ValueError:
                    valor_num = None
                reg = modelos.construir_reajuste(
                    usuario=usuario, archivo_ref=ruta, manifiesto_id=mid or None,
                    guia=guia or None, valor_usd=valor_num, motivo=motivo or None,
                    texto_resumen=resumen or None)
                ok = _fuente_dropbox().agregar_reajuste(reg)
            except Exception as exc:
                st.error(f"No se pudo archivar en Dropbox: {exc}. Reintentá.")
                return
            cargar_reajustes.clear()
            st.success("Reajuste archivado." if ok else "Reajuste ya archivado (idempotente).")
            for k in ("reajuste_extraido", "reajuste_arch"):
                st.session_state.pop(k, None)
            st.rerun()


def _seccion_reajustes_listado(reajustes):
    st.markdown('<div class="bloque-titulo">Reajustes recibidos</div>', unsafe_allow_html=True)
    if not reajustes:
        st.info("No hay reajustes recibidos todavía.")
        return
    filas = [[r.get("fecha", ""), r.get("manifiesto_id") or "—", r.get("guia") or "—",
              _usd(r.get("valor_usd")) if isinstance(r.get("valor_usd"), (int, float)) else "—",
              r.get("motivo") or "—", r.get("usuario", ""),
              (r.get("texto_resumen") or "")[:80]] for r in reajustes]
    tabla(["Fecha", "Manifiesto", "Guía", "Valor", "Motivo", "Subido por", "Resumen"], filas)


# --------------------------------------------------------------------------- #
# PORTAL DE PROVEEDOR — vista EXCLUSIVA del rol proveedor (aislamiento en el RENDER).
# No construye manifiestos, P&L, conciliación de aerolínea, clientes ni destinos.
# --------------------------------------------------------------------------- #

def _portal_proveedor(usuario):
    st.caption("Portal de proveedor (ASTRID) · solo tus facturas de despacho y su estado de pago")
    gastos = _leer_dropbox(cargar_gastos, [], "los gastos")
    pagos = _leer_dropbox(cargar_pagos, [], "los pagos")
    gastos = modelos.consolidar_estado_pago(gastos, pagos)
    mis = [g for g in gastos if g.get("concepto") == "distribucion"]

    st.markdown('<div class="bloque-titulo">Mis facturas de despacho</div>', unsafe_allow_html=True)
    cp = vista.cuentas_por_pagar(mis)
    cols = st.columns(4)
    tarjeta(cols[0], "Facturado", _usd(cp["facturado_usd"]))
    tarjeta(cols[1], "Pagado", _usd(cp["pagado_usd"]))
    tarjeta(cols[2], "Pendiente", _usd(cp["pendiente_total_usd"]))
    tarjeta(cols[3], "Vencido", _usd(cp["vencido_usd"]))
    if not mis:
        st.info("No tenés facturas de despacho registradas todavía.")
    else:
        filas = [[g.get("referencia") or "—", g.get("fecha", ""), _usd(g.get("total_usd")),
                  g.get("fecha_vencimiento") or "—", _badge_pago(g),
                  g.get("fecha_pago") or "—", g.get("referencia_pago") or "—"] for g in mis]
        tabla(["N° factura", "Fecha", "Monto", "Vencimiento", "Estado", "Fecha pago", "Ref. pago"], filas)
        pagadas = [g for g in mis if calculos.estado_pago_efectivo(g) == "pagado" and g.get("comprobante_ref")]
        for g in pagadas:
            with st.expander(f"Comprobante de {g.get('referencia') or g.get('manifiesto_id')}"):
                _ver_comprobante(g)

    st.divider()
    _seccion_vision_despacho(usuario, proveedor=True)
    st.divider()
    _seccion_vision_reajuste(usuario)


# --------------------------------------------------------------------------- #
# Sidebar: usuario, período, datasource
# --------------------------------------------------------------------------- #

st.title("📦 Portal de Envíos Encargomío")

with st.sidebar:
    st.subheader("Sesión")
    if usuario_auth:
        usuario = usuario_auth
    else:
        usuario = st.text_input("Usuario (modo abierto)", value="admin1")

rol = rol_auth or auth.ROL_ADMIN

# AISLAMIENTO POR ROL. El proveedor (acceso EXTERNO) SOLO ve su portal: acá se corta el
# render y NUNCA se construyen manifiestos, P&L, conciliación de aerolínea, tarifas,
# clientes, destinos ni novedades. La restricción es en el RENDER, no visual. El
# subtítulo con "P&L/conciliación" es admin-only (abajo), no lo ve el proveedor.
if rol == auth.ROL_PROVEEDOR:
    _portal_proveedor(usuario)
    st.stop()

st.caption("Miami → Colombia · conciliación y P&L · USD")

with st.sidebar:
    st.subheader("Período")
    desde = st.date_input("Desde", value=date(2026, 7, 1))
    hasta = st.date_input("Hasta", value=date(2026, 7, 31))
    st.divider()
    st.caption(f"Datasource ASTRID: **{config.DATASOURCE_ASTRID}**")

# Datos base del período.
try:
    resumenes = cargar_resumenes(desde, hasta)
except Exception as exc:  # datasource mal configurado (ej. excel sin directorio)
    st.error(f"No se pudo cargar el datasource ASTRID: {exc}")
    st.stop()

if not resumenes:
    st.info("No hay manifiestos en el período seleccionado.")
    st.stop()

manifiestos = [cargar_manifiesto(r.id) for r in resumenes]
tarifario = _leer_dropbox(cargar_tarifario, calculos.Tarifario(), "el tarifario")
gastos = _leer_dropbox(cargar_gastos, [], "los gastos reales")
cobros = _leer_dropbox(cargar_cobros, [], "los cobros de distribución")
novedades = _leer_dropbox(cargar_novedades, [], "las novedades")
tulas_reportadas = _leer_dropbox(cargar_tulas_reportadas, [], "las tulas reportadas")
pagos = _leer_dropbox(cargar_pagos, [], "los pagos")
consolidados = _leer_dropbox(cargar_consolidaciones, [], "las consolidaciones")
reajustes = _leer_dropbox(cargar_reajustes, [], "los reajustes")
# Estado de pago: consolidar las filas PAGO sobre los gastos (append-only; último gana).
gastos = modelos.consolidar_estado_pago(gastos, pagos)

# Diagnóstico del datasource excel (archivos omitidos / advertencias).
fuente = _fuente_astrid()
if hasattr(fuente, "diagnostico"):
    diag = fuente.diagnostico()
    if diag.get("archivos_omitidos") or diag.get("advertencias"):
        with st.sidebar.expander("Diagnóstico datasource"):
            for o in diag.get("archivos_omitidos", []):
                st.caption(f"omitido: {o.nombre} — {o.motivo}")
            for a in diag.get("advertencias", []):
                st.caption(f"⚠️ {a}")

def _factura_desde_gasto(gasto):
    """Reconstruye la FacturaAerolinea desde el GastoReal de importación (detalle_json)."""
    detalle = json.loads(gasto.get("detalle_json") or "{}")
    return {
        "numero": gasto.get("referencia"), "kg_cobrados": detalle.get("kg_cobrados"),
        "tarifa_kg_usd": detalle.get("tarifa_kg_usd"), "awb_fee_usd": detalle.get("awb_fee_usd", 0),
        "pickup_entrega_usd": detalle.get("pickup_entrega_usd", 0),
        "otros_cargos": detalle.get("otros_cargos", []), "total_usd": gasto.get("total_usd"),
    }


def _pagos_cronologico(gastos, concepto, entidad, mostrar_awb):
    """Listado cronológico de GASTOS_REALES (lo efectivamente pagado)."""
    pagos = sorted([g for g in gastos if g.get("concepto") == concepto],
                   key=lambda g: str(g.get("fecha")))
    if not pagos:
        banner(f"Sin pagos a {entidad} registrados todavía.", "info")
        return
    filas = []
    for g in pagos:
        detalle = {}
        try:
            detalle = json.loads(g.get("detalle_json") or "{}")
        except Exception:
            pass
        fila = [g.get("fecha", ""), g.get("referencia", "")]
        if mostrar_awb:
            fila.append(detalle.get("awb") or "—")
        fila += [g.get("manifiesto_id", ""), _usd(g.get("total_usd"))]
        filas.append(fila)
    cols = ["Fecha", "Factura/Ref"] + (["AWB"] if mostrar_awb else []) + ["Manifiesto", "Total"]
    tabla(cols, filas)


def _drilldown_tula(m, novedad):
    """Envíos de la tula alertada. Confirmado (asignación real) vs heurística de sospecha
    (sin asignación en el export) — visualmente diferenciada y honesta sobre el dato."""
    dd = vista.envios_de_tula(m, novedad["codigo"], config.TOP_N_ENVIOS_SOSPECHA)
    tabla_html = _tabla_html(
        ["Guía", "Contenido", "peso lb", "peso kg"],
        [[e.get("guia"), e.get("contenido"), _num(e.get("peso_lb")), _num(e.get("peso_kg"))]
         for e in dd["envios"]])
    if dd["confirmado"]:
        st.caption(f"Envíos confirmados de la tula {novedad['numero']} — ordenados por peso:")
        st.markdown(tabla_html, unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="heuristica">'
            '<div class="heuristica-titulo">⚠️ Estos envíos NO están confirmados como parte de esta tula</div>'
            '<div class="muted">El export no trae asignación de envíos por tula (PENDIENTE_API). Se listan '
            'los más pesados del manifiesto como apoyo para inspección manual — no es el contenido de la tula.</div>'
            + tabla_html +
            '<div class="muted">Subir el pantallazo de tulas NO resuelve esto (ese trae pesos, no asignación '
            'de envíos): solo la API de ASTRID o un export con la columna Tula llena identificarían los '
            'envíos de cada tula.</div></div>',
            unsafe_allow_html=True)


def _seccion_sin_cobro(manifiestos, gastos, cobros, consolidados=None):
    st.markdown('<div class="bloque-titulo">Manifiestos sin cobro (pendiente de seguimiento)</div>',
                unsafe_allow_html=True)
    sin = vista.manifiestos_sin_cobro(manifiestos, gastos, cobros, consolidados)
    if not sin:
        st.info("Todos los manifiestos del período tienen factura de aerolínea y cobro de ASTRID.")
        return
    banner("«No me han cobrado → no he pagado». No es error: es seguimiento de pendientes.", "info")
    filas = [[s["id"], s["fecha"],
              "⛔ falta" if s["sin_factura_aerolinea"] else "✓",
              "⛔ falta" if s["sin_cobro_astrid"] else "✓"] for s in sin]
    tabla(["Manifiesto", "Fecha", "Factura aerolínea", "Cobro ASTRID"], filas)


tab_gen, tab_ent, tab_desp, tab_nov, tab_carga, tab_reaj = st.tabs(
    ["📊 Vista general", "✈️ Entrada a Colombia", "🚚 Despacho en Colombia",
     "⚖️ Novedades", "📤 Cargar archivos", "🧾 Reajustes"])


# --------------------------------------------------------------------------- #
# TAB 1 — Vista general (filtros propios + KPIs + gráficos)
# --------------------------------------------------------------------------- #

with tab_gen:
    st.markdown('<div class="bloque-titulo">Filtros</div>', unsafe_allow_html=True)
    fc1, fc2 = st.columns([1, 2])
    with fc1:
        rango = st.date_input("Rango de fechas", value=(desde, hasta), key="vg_fechas")
    with fc2:
        ids_todos = [m["id"] for m in manifiestos]
        sel_ids = st.multiselect("Manifiestos", ids_todos, default=ids_todos, key="vg_manifiestos")

    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        f_desde, f_hasta = rango
    else:
        f_desde, f_hasta = desde, hasta

    def _en_rango(m):
        f = m.get("fecha")
        try:
            fdate = f if hasattr(f, "year") else date.fromisoformat(str(f))
        except Exception:
            return True
        return f_desde <= fdate <= f_hasta

    manif_vg = [m for m in manifiestos if m["id"] in set(sel_ids) and _en_rango(m)]

    if not manif_vg:
        st.info("Ningún manifiesto con los filtros actuales.")
    else:
        k = vista.kpis_periodo(manif_vg, gastos, tarifario, tulas_reportadas)

        c1 = st.columns(4)
        val_cobrado = badge_info("pendiente API ASTRID") if k["ingresos"] is None else _usd(k["ingresos"])
        tarjeta(c1[0], "Valor cobrado al cliente", val_cobrado)
        tarjeta(c1[1], "Pagado a aerolíneas", _usd(k["pagado_aerolineas"]))
        tarjeta(c1[2], "Pagado a ASTRID", _usd(k["pagado_astrid"]))
        util_lbl = "Utilidad" if k["modo_ingresos"] == "completo" else "Resultado (solo costos)"
        tarjeta(c1[3], util_lbl, _usd(k["utilidad"]))

        c2 = st.columns(4)
        tarjeta(c2[0], "Manifiestos", str(k["n_manifiestos"]))
        tarjeta(c2[1], "Envíos", f"{k['n_envios']:,}")
        kg_txt = _num(k["kg_sistema"]) + (f" · báscula {_num(k['kg_bascula'])}"
                                          if k["kg_bascula"] is not None else "")
        tarjeta(c2[2], "kg totales (sistema)", kg_txt)
        tarjeta(c2[3], "% con factura", _pct(k["pct_con_factura"]))

        c3 = st.columns(4)
        tarjeta(c3[0], "Peso prom / envío",
                f"{k['peso_prom_lb']} lb" if k["peso_prom_lb"] is not None else "—")
        if k["ingresos"] is None:
            with c3[1]:
                banner(config.mensaje_pendiente("valor_cobrado"), "info")

        # --- Cuentas por pagar (estado de pago de los gastos del período) ---
        st.markdown('<div class="bloque-titulo">Cuentas por pagar</div>', unsafe_allow_html=True)
        ids_vg = {m["id"] for m in manif_vg}
        gastos_vg = [g for g in gastos if g.get("manifiesto_id") in ids_vg]
        cp = vista.cuentas_por_pagar(gastos_vg)
        cpc = st.columns(4)
        tarjeta(cpc[0], "Pendiente aerolíneas", _usd(cp["pendiente_aerolineas_usd"]))
        tarjeta(cpc[1], "Pendiente ASTRID", _usd(cp["pendiente_astrid_usd"]))
        tarjeta(cpc[2], "Pendiente total", _usd(cp["pendiente_total_usd"]))
        tarjeta(cpc[3], "Vencido", _usd(cp["vencido_usd"]),
                sub=(f"{cp['n_vencidas']} factura(s)" if cp["n_vencidas"] else None))

        cons_vg = [c for c in consolidados if c.get("manifiesto_id") in ids_vg]
        if cons_vg:
            agg = vista.ahorro_consolidados(cons_vg, manif_vg, tarifario)
            st.markdown('<div class="bloque-titulo">Ahorro por consolidación</div>',
                        unsafe_allow_html=True)
            ac = st.columns(3)
            tarjeta(ac[0], "Costo individual (suma)", _usd(agg["individual_usd"]))
            tarjeta(ac[1], "Costo consolidado", _usd(agg["consolidado_usd"]))
            tarjeta(ac[2], "Ahorro", _usd(agg["ahorro_usd"]),
                    sub=f"{agg['n_consolidados']} despacho(s)")

        _seccion_sin_cobro(manif_vg, gastos_vg, cobros, cons_vg)

        # --- Gráficos nativos (sobrios) ---
        part = vista.participacion_por_departamento(manif_vg, top=12)
        st.markdown('<div class="bloque-titulo">Destinos principales por envíos</div>', unsafe_allow_html=True)
        if part["por_envios"]:
            st.bar_chart(pd.DataFrame({"envíos": {d: n for d, n, _ in part["por_envios"]}}), horizontal=True)
            tabla(["Departamento", "Envíos", "%"], [[d, n, _pct(p)] for d, n, p in part["por_envios"]])
        st.markdown('<div class="bloque-titulo">Destinos principales por kg</div>', unsafe_allow_html=True)
        if part["por_kg"]:
            st.bar_chart(pd.DataFrame({"kg": {d: kg for d, kg, _ in part["por_kg"][:12]}}), horizontal=True)

        st.markdown('<div class="bloque-titulo">Clientes principales (top 10)</div>', unsafe_allow_html=True)
        tc = vista.top_clientes(manif_vg, n=10)
        if tc["items"]:
            st.caption(f"Agrupado por «{tc['campo']}»." +
                       ("" if tc["campo"] == "cliente"
                        else " (sin hoja CLIENTES en el export → se usa el casillero.)"))
            st.bar_chart(pd.DataFrame({"envíos": {c: n for c, n, _ in tc["items"]}}), horizontal=True)
            tabla([tc["campo"], "Envíos", "% concentración"], [[c, n, _pct(p)] for c, n, p in tc["items"]])

        st.markdown('<div class="bloque-titulo">Envíos y kg por manifiesto</div>', unsafe_allow_html=True)
        serie = vista.series_por_manifiesto(manif_vg, tarifario)
        if serie:
            dfs = pd.DataFrame(serie).set_index("id")
            st.bar_chart(dfs[["n_envios"]])
            st.bar_chart(dfs[["kg_sistema"]])


# --------------------------------------------------------------------------- #
# TAB 2 — Entrada a Colombia (aerolínea)
# --------------------------------------------------------------------------- #

with tab_ent:
    st.markdown('<div class="bloque-titulo">Entrada a Colombia — pactado vs cobrado por aerolínea</div>',
                unsafe_allow_html=True)
    gasto_por_manif = {g["manifiesto_id"]: g for g in gastos if g.get("concepto") == "importacion"}

    resumen_imp, detalles = [], []
    for m in manifiestos:
        g = gasto_por_manif.get(m["id"])
        factura = _factura_desde_gasto(g) if g else None
        r = conciliacion.conciliar_importacion(m, factura, tarifario, tulas_reportadas)
        detalles.append((m, r))
        estado_badge = (badge_info("sin cobro aún — sin pago") if r["estado"] == "sin_factura"
                        else badge(r["estado"]))
        resumen_imp.append([m["id"], estado_badge, _usd(r.get("esperado_usd")),
                            _usd(r.get("factura_total_usd")), _usd(r.get("delta_total"))])
    tabla(["Manifiesto", "Estado", "Pactado (esperado)", "Cobrado (aerolínea)", "Diferencia"], resumen_imp)

    st.markdown('<div class="bloque-titulo">Detalle por manifiesto</div>', unsafe_allow_html=True)
    for m, r in detalles:
        cab = "sin cobro aún — sin pago" if r["estado"] == "sin_factura" else r["estado"]
        with st.expander(f"{m['id']} · {cab}", expanded=(r["estado"] == "discrepancia")):
            if r["estado"] == "sin_factura":
                banner("Sin factura de aerolínea todavía — «no me han cobrado → no he pagado».", "info")
                continue
            _render_conciliacion(r)
            if r["estado"] == "discrepancia":
                bloque_justificar(
                    novedades=novedades, usuario=usuario, manifiesto_id=m["id"],
                    tipo="cobro_aerolinea", discriminador=None, campo_disc="guia",
                    valor_esperado=r["esperado_usd"], valor_real=r["factura_total_usd"],
                    delta=r["delta_total"])

    st.markdown('<div class="bloque-titulo">Estado de pago a aerolíneas</div>', unsafe_allow_html=True)
    _seccion_estado_pago(gastos, "importacion", "aerolíneas", usuario)

    st.markdown('<div class="bloque-titulo">Pagos a aerolínea (cronológico)</div>', unsafe_allow_html=True)
    _pagos_cronologico(gastos, "importacion", "aerolíneas", mostrar_awb=True)


# --------------------------------------------------------------------------- #
# TAB 3 — Despacho en Colombia (ASTRID)
# --------------------------------------------------------------------------- #

with tab_desp:
    st.markdown('<div class="bloque-titulo">Despacho en Colombia — esperado vs cobro de ASTRID (por guía)</div>',
                unsafe_allow_html=True)
    st.caption("La distribución nacional la factura ASTRID (mismo proveedor del sistema).")

    indice_envios = {}
    for m in manifiestos:
        for e in m["envios"]:
            indice_envios[e["guia"]] = (m["id"], e)

    ver_todas = st.toggle("Ver todas (incluye conciliadas)", value=False)

    # Las guías dentro de un despacho consolidado NO se cuentan como individuales
    # (evitar doble conteo): se concilian en la sección de consolidaciones.
    guias_consol = vista.guias_consolidadas(consolidados)
    if guias_consol:
        st.caption(f"{len(guias_consol)} guía(s) en despachos consolidados — no se listan "
                   "individualmente (ver «Despachos consolidados» abajo).")

    conciliaciones = []
    for c in cobros:
        if c["guia"] in guias_consol:
            continue  # cubierta por un consolidado
        info = indice_envios.get(c["guia"])
        if not info:
            continue  # guía sin envío en el datasource/período actual
        mid, envio = info
        r = conciliacion.conciliar_distribucion(envio, c, tarifario)
        conciliaciones.append((mid, c, r))

    if not conciliaciones:
        banner("Sin cobro aún — sin pago: no hay cobros de ASTRID que crucen con guías del período.", "info")
    else:
        visibles = [x for x in conciliaciones if ver_todas or x[2]["estado"] != "conciliado"]
        st.caption(f"{len(visibles)} de {len(conciliaciones)} cobros mostrados.")
        for mid, c, r in visibles:
            with st.expander(
                    f"Guía {c['guia']} · ASTRID (transp.: {c.get('transportadora', '—')}) · {r['estado']}",
                    expanded=(r["estado"] == "discrepancia")):
                cc = st.columns(3)
                tarjeta(cc[0], "Esperado (8 lb mín.)", _usd(r.get("esperado_usd")))
                tarjeta(cc[1], "Cobrado ASTRID", _usd(r.get("valor_cobrado_usd")))
                tarjeta(cc[2], "Diferencia", _usd(r.get("delta")))
                if r["estado"] == "discrepancia":
                    bloque_justificar(
                        novedades=novedades, usuario=usuario, manifiesto_id=mid,
                        tipo="cobro_distribucion", discriminador=c["guia"], campo_disc="guia",
                        valor_esperado=r["esperado_usd"], valor_real=r["valor_cobrado_usd"],
                        delta=r["delta"])

    st.divider()
    _seccion_consolidaciones(manifiestos, tarifario, consolidados, usuario)

    st.divider()
    st.markdown('<div class="bloque-titulo">Estado de pago a ASTRID</div>', unsafe_allow_html=True)
    _seccion_estado_pago(gastos, "distribucion", "ASTRID", usuario)

    st.markdown('<div class="bloque-titulo">Pagos a ASTRID (cronológico)</div>', unsafe_allow_html=True)
    _pagos_cronologico(gastos, "distribucion", "ASTRID", mostrar_awb=False)


# --------------------------------------------------------------------------- #
# TAB 4 — Novedades (peso con drill-down + justificar + sin cobro + resueltas)
# --------------------------------------------------------------------------- #

with tab_nov:
    st.markdown('<div class="bloque-titulo">Novedades de peso por tula</div>', unsafe_allow_html=True)
    opciones = {f"{m['id']} · {m['fecha']}": m for m in manifiestos}
    etiqueta = st.selectbox("Manifiesto", list(opciones), key="nov_manif")
    m = opciones[etiqueta]

    nov = calculos.novedades_peso_manifiesto(m, tarifario)
    if nov.estado == NO_DISPONIBLE:
        banner(config.mensaje_pendiente("kg_reportado"), "warn")
    else:
        det = nov.detalle
        st.caption(f"{det['n_alertas']} alerta(s) · impacto total {_usd(det['impacto_total_usd'])}")
        filas = [[
            n["numero"], _num(n["kg_sistema"]), _num(n["kg_reportado"]),
            _num(n["dif_kg"]), _pct(n["dif_pct"]), _usd(n["impacto_usd"]),
            badge("alerta" if n["es_alerta"] else "ok"),
        ] for n in det["novedades"]]
        tabla(["Tula", "kg sistema", "kg reportado", "dif kg", "dif %", "Impacto USD", "Estado"], filas)

        alertas = [n for n in det["novedades"] if n["es_alerta"]]
        if alertas:
            st.markdown('<div class="bloque-titulo">Alertas — expandir para ver envíos y justificar</div>',
                        unsafe_allow_html=True)
            for n in alertas:
                with st.expander(f"Tula {n['numero']} ({n['codigo']}) · impacto {_usd(n['impacto_usd'])}",
                                 expanded=False):
                    _drilldown_tula(m, n)          # envíos de la tula (o heurística honesta)
                    bloque_justificar(
                        novedades=novedades, usuario=usuario, manifiesto_id=m["id"],
                        tipo="peso_tula", discriminador=n["codigo"], campo_disc="tula_codigo",
                        valor_esperado=n["kg_sistema"], valor_real=n["kg_reportado"],
                        delta=n["dif_kg"])

    st.divider()
    _seccion_sin_cobro(manifiestos, gastos, cobros, consolidados)

    st.divider()
    st.markdown('<div class="bloque-titulo">Historial de novedades resueltas</div>', unsafe_allow_html=True)
    if not novedades:
        st.info("No hay novedades resueltas todavía. Se registran justificando aquí y en Entrada/Despacho.")
    else:
        filas = [[
            n.get("fecha", ""), n.get("usuario", ""), n.get("manifiesto_id", ""),
            n.get("tipo", ""), n.get("tula_codigo") or n.get("guia") or "—",
            _usd(n.get("delta")) if isinstance(n.get("delta"), (int, float)) else _num(n.get("delta")),
            n.get("accion", ""), badge(n.get("estado", "resuelta")),
        ] for n in novedades]
        tabla(["Fecha", "Usuario", "Manifiesto", "Tipo", "Ref.", "Delta", "Acción", "Estado"], filas)


# --------------------------------------------------------------------------- #
# TAB 5 — Cargar archivos (todos los uploads centralizados)
# --------------------------------------------------------------------------- #

with tab_carga:
    st.markdown('<div class="bloque-titulo">Cargar archivos por visión</div>', unsafe_allow_html=True)
    st.caption("Todas las cargas se centralizan aquí. Tras cada carga exitosa, el resultado se ve "
               "en la tab indicada.")

    _seccion_vision_factura(manifiestos, tarifario, usuario, tulas_reportadas)
    st.caption("↑ La factura confirmada se refleja en «✈️ Entrada a Colombia» y en «📊 Vista general».")

    _seccion_vision_tulas(manifiestos, usuario)
    st.caption("↑ Los pesos registrados se ven en «⚖️ Novedades» y habilitan la báscula en «✈️ Entrada».")

    st.divider()
    _seccion_vision_despacho(usuario, proveedor=False, manifiestos=manifiestos)
    st.caption("↑ Si el proveedor no sube su factura de despacho, la subimos nosotros "
               "(misma lógica). Se refleja en «🚚 Despacho en Colombia».")


# --------------------------------------------------------------------------- #
# TAB 6 — Reajustes (recepción, archivo y listado editable)
# --------------------------------------------------------------------------- #

with tab_reaj:
    st.markdown('<div class="bloque-titulo">Reajustes de despacho</div>', unsafe_allow_html=True)
    banner("Fase de recepción y archivo únicamente: sin flujo de negocio (notificación, "
           "quién asume la pérdida, cobro). Ver docs/PENDIENTES_API.md (módulo futuro).", "info")
    _seccion_vision_reajuste(usuario)
    st.divider()
    _seccion_reajustes_listado(reajustes)
