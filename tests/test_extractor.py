"""Tests de Fase 4: vision/extractor.py (cliente Anthropic mockeado, sin API real)."""

import json
import sys
import types

import pytest

from datasources.dropbox_mock import FuenteDropboxMock
from vision import extractor

# Factura DemoAir DEMO-0001 (774 kg × 1.00 + 10 + 50 = 834.00).
FACTURA = {
    "numero_factura": "DEMO-0001", "fecha": "2026-07-16", "awb": "999-12345678",
    "kg_cobrados": 774, "tarifa_kg_usd": 1.00, "awb_fee_usd": 10, "pickup_entrega_usd": 50,
    "otros_cargos": [], "total_usd": 834.00,
}

TULAS_900009 = {
    "manifiesto_id": "900009", "awb_master": "999-11112222", "piezas": 11,
    "guias_hijas": None,
    "tulas": [{"numero": i + 1, "kg_reportado": kg} for i, kg in enumerate(
        [28.0, 27.0, 29.0, 26.0, 25.0, 30.0, 24.0, 28.0, 31.0, 22.0, 30.0])],
    "total_kg": 300.0,
}


def _invocar_fence(datos):
    """Simula al modelo devolviendo el JSON envuelto en fences ```json."""
    return lambda prompt, imagenes: "```json\n" + json.dumps(datos) + "\n```"


# --- Extracción / parseo -------------------------------------------------- #

def test_extraer_factura_parsea_fences():
    datos = extractor.extraer([], "factura_aerolinea", invocar=_invocar_fence(FACTURA))
    assert datos["numero_factura"] == "DEMO-0001"
    assert datos["kg_cobrados"] == 774
    assert datos["total_usd"] == 834.00


def test_parsear_json_con_texto_alrededor():
    invocar = lambda p, i: "Aquí está el JSON:\n" + json.dumps(FACTURA) + "\nGracias."
    datos = extractor.extraer([], "factura_aerolinea", invocar=invocar)
    assert datos["awb"] == "999-12345678"


def test_factura_transportadora_no_implementada():
    with pytest.raises(NotImplementedError):
        extractor.extraer([], "factura_transportadora", invocar=lambda p, i: "{}")


def test_tipo_desconocido():
    with pytest.raises(ValueError):
        extractor.extraer([], "otra_cosa", invocar=lambda p, i: "{}")


# --- Validación de factura ------------------------------------------------ #

def test_validar_factura_cuadra():
    cuadra, motivos = extractor.validar_factura(FACTURA)
    assert cuadra and not motivos


def test_factura_no_cuadra_total_alterado():
    malo = {**FACTURA, "total_usd": 1100.0}   # total alterado, aritmética interna rota
    cuadra, motivos = extractor.validar_factura(malo)
    assert not cuadra and any("no cuadra" in m for m in motivos)


def test_factura_null_no_cuadra():
    malo = {**FACTURA, "tarifa_kg_usd": None}
    cuadra, motivos = extractor.validar_factura(malo)
    assert not cuadra and any("ilegible" in m for m in motivos)


# --- GastoReal + idempotencia --------------------------------------------- #

def test_gasto_real_desde_factura_y_idempotencia():
    datos = extractor.extraer([], "factura_aerolinea", invocar=_invocar_fence(FACTURA))
    gasto = extractor.gasto_real_desde_factura(datos, "900007", origen="vision")

    assert gasto["concepto"] == "importacion"
    assert gasto["referencia"] == "DEMO-0001"
    assert gasto["origen"] == "vision"
    assert gasto["total_usd"] == 834.00
    # detalle_json es la fuente canónica de la factura (reconstruible por conciliación).
    detalle = json.loads(gasto["detalle_json"])
    assert detalle["kg_cobrados"] == 774 and detalle["tarifa_kg_usd"] == 1.00

    dropbox = FuenteDropboxMock()
    # El 900007 ya trae la DemoAir DEMO-0001 precargada -> idempotencia.
    assert dropbox.agregar_gasto_real(gasto) is False
    assert dropbox.agregar_gasto_real({**gasto, "referencia": "99999"}) is True


# --- Extracción y validación de tulas ------------------------------------- #

def test_extraer_tulas_900009_cuadra():
    datos = extractor.extraer([], "pantalla_tulas", invocar=_invocar_fence(TULAS_900009))
    assert len(datos["tulas"]) == 11
    cuadra, motivos = extractor.validar_tulas(datos)
    assert cuadra and not motivos


def test_extraer_tulas_incluye_awb_master():
    datos = extractor.extraer([], "pantalla_tulas", invocar=_invocar_fence(TULAS_900009))
    assert datos["awb_master"] == "999-11112222"


def test_extraer_tulas_sin_awb_queda_null():
    sin_awb = {**TULAS_900009, "awb_master": None}
    datos = extractor.extraer([], "pantalla_tulas", invocar=_invocar_fence(sin_awb))
    assert datos["awb_master"] is None
    assert extractor.validar_tulas(datos)[0] is True   # awb no afecta el cuadre


def test_tulas_no_cuadra_total():
    malo = {**TULAS_900009, "total_kg": 305.0}
    cuadra, motivos = extractor.validar_tulas(malo)
    assert not cuadra and any("no cuadra" in m for m in motivos)


def test_tulas_no_cuadra_piezas():
    malo = {**TULAS_900009, "piezas": 12}   # 12 ≠ 11 tulas
    cuadra, motivos = extractor.validar_tulas(malo)
    assert not cuadra and any("piezas" in m for m in motivos)


# --- Secrets: forma anidada + plana, y mensaje claro si falta ------------- #

def _fake_streamlit(secrets):
    fake = types.ModuleType("streamlit")
    fake.secrets = secrets   # dict-like: soporta [] e `in`
    return fake


def test_get_secret_anidado_y_plano(monkeypatch):
    import config
    # Forma anidada [anthropic] api_key (secrets.toml local).
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit({"anthropic": {"api_key": "K-anidada"}}))
    assert config.get_secret("anthropic", "api_key", "ANTHROPIC_API_KEY") == "K-anidada"
    # Forma plana legacy (por si algún host inyecta los secrets planos).
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit({"ANTHROPIC_API_KEY": "K-plana"}))
    assert config.get_secret("anthropic", "api_key", "ANTHROPIC_API_KEY") == "K-plana"
    # Ausente en ambas formas.
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit({}))
    assert config.get_secret("anthropic", "api_key", "ANTHROPIC_API_KEY") is None


def test_sin_api_key_mensaje_claro(monkeypatch):
    """Sin la key en ninguna forma, _invocar_anthropic lanza un error legible que la
    sección de visión captura y muestra puntualmente (no rompe el resto del dash)."""
    monkeypatch.setitem(sys.modules, "streamlit", _fake_streamlit({}))
    with pytest.raises(RuntimeError) as exc:
        extractor._invocar_anthropic("prompt", [])
    assert "ANTHROPIC_API_KEY" in str(exc.value)
    assert "secrets.toml" in str(exc.value)
