"""Extracción de datos de documentos con visión de la API de Anthropic.

`extraer(imagenes, tipo_documento)` soporta:
  - "factura_aerolinea": FacturaAerolinea (ver docs/CONTRATO_DATOS.md).
  - "pantalla_tulas": pesos reportados por tula (flujo provisional, ver
    docs/PENDIENTES_API.md).
  - "factura_transportadora": DECLARADO pero NO implementado -> NotImplementedError.

Reglas duras:
  - El prompt pide SOLO JSON; un campo ilegible es null. NUNCA inventar valores.
  - `validar_*` protege la aritmética interna del JSON, NO la fidelidad de la lectura:
    por eso el PDF se renderiza a buena resolución (~180 DPI) y se reescala hacia abajo
    (nunca se recorta) si excede el limite de la API — un número mal leído por baja
    resolución cuadraría igual con los demás campos mal.

El cliente Anthropic es inyectable (`invocar`) para poder testear sin llamadas reales.
"""

from __future__ import annotations

import base64
import io
import json
import re
from datetime import date

# Modelo con visión.
MODELO = "claude-sonnet-4-6"

# Límite de lado largo efectivo de claude-sonnet-4-6 (px). Renderizar/enviar por encima
# no aporta: el servidor reescala igual. Reescalamos nosotros (LANCZOS) para controlar
# la calidad del resampleo.
MAX_LADO_PX = 1568
# ~180 DPI a 72 de base: suficiente para leer tarifas con decimales y números de factura.
ESCALA_PDF = 2.5
# Margen bajo el límite de 5 MB/imagen de la API (base64 infla ~33%).
MAX_BYTES = 3_800_000


# --------------------------------------------------------------------------- #
# Prompts por tipo (piden SOLO JSON, ilegible -> null, nunca inventar)
# --------------------------------------------------------------------------- #

_PROMPT_FACTURA = """Sos un extractor de datos de facturas de aerolínea de carga.
Devolvé EXCLUSIVAMENTE un JSON válido con esta forma exacta, sin texto adicional ni
explicaciones:

{"numero_factura": string|null, "fecha": string|null, "awb": string|null,
 "kg_cobrados": number|null, "tarifa_kg_usd": number|null, "awb_fee_usd": number|null,
 "pickup_entrega_usd": number|null,
 "otros_cargos": [{"concepto": string, "valor": number}],
 "total_usd": number|null}

Reglas:
- Si un campo no se lee con CERTEZA, poné null. NUNCA inventes ni estimes un valor.
- Números sin símbolo de moneda ni separadores de miles; usá punto como decimal.
- otros_cargos: lista vacía [] si no hay cargos adicionales."""

_PROMPT_TULAS = """Sos un extractor de una pantalla/correo de tulas del sistema ASTRID.
Devolvé EXCLUSIVAMENTE un JSON válido con esta forma exacta, sin texto adicional:

{"manifiesto_id": string|null, "awb_master": string|null, "piezas": number|null,
 "guias_hijas": [string]|null,
 "tulas": [{"numero": number, "kg_reportado": number}], "total_kg": number|null}

Reglas:
- Si un campo no se lee con CERTEZA, poné null. NUNCA inventes valores.
- awb_master: el AWB que aparece como "guía Master Asignada <awb>" (ej. 999-11112222);
  si no aparece en el documento, poné null.
- guias_hijas: lista de guías hijas si el documento las trae; si no, null.
- kg_reportado con punto como decimal.
- Incluí una entrada por cada tula visible."""

_PROMPTS = {
    "factura_aerolinea": _PROMPT_FACTURA,
    "pantalla_tulas": _PROMPT_TULAS,
}

CAMPOS_FACTURA_CRITICOS = [
    "kg_cobrados", "tarifa_kg_usd", "awb_fee_usd", "pickup_entrega_usd", "total_usd",
]


# --------------------------------------------------------------------------- #
# Preparación de imágenes (PDF -> imágenes; reescalado a límite de la API)
# --------------------------------------------------------------------------- #

def _codificar(pil_img) -> dict:
    """PIL Image -> {media_type, data} respetando el límite de bytes."""
    from PIL import Image  # import perezoso (Pillow llega vía streamlit)

    if pil_img.mode not in ("RGB", "RGBA", "L"):
        pil_img = pil_img.convert("RGB")

    lado = max(pil_img.size)
    if lado > MAX_LADO_PX:  # reescalar hacia abajo, nunca recortar
        factor = MAX_LADO_PX / lado
        nuevo = (max(1, round(pil_img.width * factor)), max(1, round(pil_img.height * factor)))
        pil_img = pil_img.resize(nuevo, Image.LANCZOS)

    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    data = buf.getvalue()
    if len(data) <= MAX_BYTES:
        return {"media_type": "image/png", "data": data}

    # PNG demasiado grande: recodificar a JPEG (sin recortar).
    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, format="JPEG", quality=85)
    return {"media_type": "image/jpeg", "data": buf.getvalue()}


def pdf_a_imagenes(pdf_bytes: bytes) -> list:
    """Renderiza cada página del PDF a imagen (~180 DPI) con pypdfium2."""
    import pypdfium2 as pdfium  # import perezoso

    pdf = pdfium.PdfDocument(pdf_bytes)
    imagenes = []
    for i in range(len(pdf)):
        bitmap = pdf[i].render(scale=ESCALA_PDF)
        imagenes.append(_codificar(bitmap.to_pil()))
    return imagenes


def preparar(nombre: str, datos: bytes) -> list:
    """Convierte un archivo subido (pdf/png/jpg) a la lista de imágenes de la API."""
    if nombre.lower().endswith(".pdf"):
        return pdf_a_imagenes(datos)
    from PIL import Image  # import perezoso
    return [_codificar(Image.open(io.BytesIO(datos)))]


# --------------------------------------------------------------------------- #
# Invocación del modelo (inyectable para tests)
# --------------------------------------------------------------------------- #

ERROR_SIN_KEY = (
    "Falta la API key de Anthropic en secrets: agregá [anthropic] api_key "
    "(o ANTHROPIC_API_KEY) en .streamlit/secrets.toml."
)


def _invocar_anthropic(prompt: str, imagenes: list) -> str:
    """Llama a la API real de Anthropic. Key vía config.get_secret (forma anidada
    [anthropic] api_key o plana ANTHROPIC_API_KEY)."""
    import config  # import perezoso

    # Chequeo de key primero, con mensaje claro: la sección de visión captura esto y
    # lo muestra como error puntual, sin reventar el resto del dashboard.
    api_key = config.get_secret("anthropic", "api_key", "ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(ERROR_SIN_KEY)

    import anthropic  # import perezoso

    cliente = anthropic.Anthropic(api_key=api_key)
    contenido = []
    for img in imagenes:
        contenido.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": base64.standard_b64encode(img["data"]).decode("ascii"),
            },
        })
    contenido.append({"type": "text", "text": prompt})

    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=2048,
        messages=[{"role": "user", "content": contenido}],
    )
    return "".join(b.text for b in respuesta.content if b.type == "text")


def _parsear_json(texto: str) -> dict:
    """Parsea JSON tolerando fences ```json ... ``` o texto alrededor."""
    if not texto or not texto.strip():
        raise ValueError("respuesta vacía del modelo")
    t = texto.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL | re.IGNORECASE)
    if m:
        t = m.group(1).strip()
    else:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            t = t[i:j + 1]
    return json.loads(t)


def extraer(imagenes: list, tipo_documento: str, *, invocar=None) -> dict:
    """Extrae datos estructurados del documento. `invocar` inyectable para tests."""
    if tipo_documento == "factura_transportadora":
        raise NotImplementedError(
            "factura_transportadora: extracción declarada pero no implementada "
            "(prevista para una fase futura)."
        )
    if tipo_documento not in _PROMPTS:
        raise ValueError(f"tipo_documento desconocido: {tipo_documento!r}")

    invocar = invocar or _invocar_anthropic
    texto = invocar(_PROMPTS[tipo_documento], imagenes)
    return _parsear_json(texto)


# --------------------------------------------------------------------------- #
# Validaciones duras (protegen la aritmética interna del JSON)
# --------------------------------------------------------------------------- #

def validar_factura(datos: dict, tol: float = 0.02):
    """(cuadra, motivos). No cuadra si hay nulls críticos o kg·tarifa+fees+otros ≠ total."""
    faltantes = [c for c in CAMPOS_FACTURA_CRITICOS if datos.get(c) is None]
    if faltantes:
        return False, [f"campos ilegibles (null): {', '.join(faltantes)}"]

    otros = sum((c.get("valor") or 0) for c in (datos.get("otros_cargos") or []))
    esperado = (datos["kg_cobrados"] * datos["tarifa_kg_usd"]
                + datos["awb_fee_usd"] + datos["pickup_entrega_usd"] + otros)
    if abs(esperado - datos["total_usd"]) > tol:
        return False, [f"no cuadra: kg·tarifa+fees+otros = {round(esperado, 2)} "
                       f"≠ total {datos['total_usd']}"]
    return True, []


def validar_tulas(datos: dict, tol: float = 0.1):
    """(cuadra, motivos). ∑tulas ≈ total_kg y len(tulas) == piezas (si viene piezas)."""
    tulas = datos.get("tulas") or []
    if not tulas:
        return False, ["sin tulas legibles"]
    kgs = [t.get("kg_reportado") for t in tulas]
    if any(k is None for k in kgs):
        return False, ["alguna tula con kg_reportado ilegible (null)"]
    total = datos.get("total_kg")
    if total is None:
        return False, ["total_kg ilegible (null)"]
    if abs(sum(kgs) - total) > tol:
        return False, [f"no cuadra: ∑tulas {round(sum(kgs), 2)} ≠ total_kg {total}"]
    piezas = datos.get("piezas")
    if piezas is not None and piezas != len(tulas):
        return False, [f"piezas ({piezas}) ≠ nº de tulas ({len(tulas)})"]
    return True, []


# --------------------------------------------------------------------------- #
# Construcción del GastoReal (detalle_json = fuente canónica de la factura)
# --------------------------------------------------------------------------- #

def gasto_real_desde_factura(datos: dict, manifiesto_id: str, *, proveedor=None,
                             origen: str = "vision", fecha=None) -> dict:
    """GastoReal de importación. `detalle_json` guarda la FacturaAerolinea completa
    (fuente canónica; no hay almacén de facturas aparte — ver docs/CONTRATO_DATOS.md)."""
    detalle = {
        "kg_cobrados": datos.get("kg_cobrados"),
        "tarifa_kg_usd": datos.get("tarifa_kg_usd"),
        "awb_fee_usd": datos.get("awb_fee_usd"),
        "pickup_entrega_usd": datos.get("pickup_entrega_usd"),
        "otros_cargos": datos.get("otros_cargos") or [],
        "awb": datos.get("awb"),
    }
    return {
        "fecha": fecha or datos.get("fecha") or date.today().isoformat(),
        "manifiesto_id": manifiesto_id,
        "proveedor": proveedor or "Aerolínea",
        "concepto": "importacion",
        "referencia": datos.get("numero_factura"),
        "detalle_json": json.dumps(detalle, ensure_ascii=False),
        "total_usd": datos.get("total_usd"),
        "origen": origen,
    }
