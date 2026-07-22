"""Tests de Fase 3: FuenteDropboxMock (precarga + idempotencia)."""

import pytest

from core.calculos import Tarifario
from datasources.dropbox_base import FuenteDropbox
from datasources.dropbox_mock import FuenteDropboxMock


@pytest.fixture
def dropbox():
    return FuenteDropboxMock()


def test_cumple_la_interfaz(dropbox):
    assert isinstance(dropbox, FuenteDropbox)


# --- Precarga ------------------------------------------------------------- #

def test_precarga_gasto_demo(dropbox):
    gastos = dropbox.leer_gastos_reales()
    demo = next(g for g in gastos if g["referencia"] == "DEMO-0001")
    assert demo["manifiesto_id"] == "900007"
    assert demo["concepto"] == "importacion"
    assert demo["total_usd"] == 834.00


def test_precarga_cobros_con_delta(dropbox):
    cobros = dropbox.leer_cobros_distribucion()
    assert len(cobros) == 3
    # Valores NO enteros -> siempre habrá delta (el esperado de distribución es entero).
    assert all(c["valor_usd"] != round(c["valor_usd"]) for c in cobros)
    assert all(c["manifiesto_id"] == "900007" for c in cobros)


def test_novedades_vacio_al_inicio(dropbox):
    assert dropbox.leer_novedades() == []


def test_leer_tarifario(dropbox):
    t = dropbox.leer_tarifario()
    assert isinstance(t, Tarifario)
    assert t.imp_tarifa_kg == 1.00


# --- Idempotencia --------------------------------------------------------- #

def test_idempotencia_gasto(dropbox):
    g = {"manifiesto_id": "900009", "concepto": "importacion", "referencia": "X1",
         "total_usd": 500.0}
    assert dropbox.agregar_gasto_real(g) is True
    assert dropbox.agregar_gasto_real(dict(g)) is False           # misma llave
    assert dropbox.agregar_gasto_real({**g, "referencia": "X2"}) is True  # otra llave


def test_idempotencia_novedad(dropbox):
    n = {"manifiesto_id": "900007", "tula_codigo": "T-3", "guia": None,
         "tipo": "peso_tula", "estado": "resuelta"}
    assert dropbox.agregar_novedad(n) is True
    assert dropbox.agregar_novedad(dict(n)) is False
    assert dropbox.agregar_novedad({**n, "tula_codigo": "T-4"}) is True
    assert len(dropbox.leer_novedades()) == 2


def test_idempotencia_novedad_discrimina_guia(dropbox):
    n = {"manifiesto_id": "900007", "tula_codigo": None, "guia": "100005",
         "tipo": "cobro_distribucion"}
    assert dropbox.agregar_novedad(n) is True
    assert dropbox.agregar_novedad(dict(n)) is False


def test_idempotencia_cobro(dropbox):
    c = {"manifiesto_id": "900007", "guia": "100005", "valor_usd": 9.99}
    assert dropbox.agregar_cobro_distribucion(c) is False  # ya precargado (100005)
    c2 = {"manifiesto_id": "900007", "guia": "999999", "valor_usd": 5.0}
    assert dropbox.agregar_cobro_distribucion(c2) is True


def test_lectura_es_copia_defensiva(dropbox):
    gastos = dropbox.leer_gastos_reales()
    gastos.append({"basura": 1})
    assert len(dropbox.leer_gastos_reales()) == 1  # no se mutó el estado interno


# --- Tulas reportadas (hoja provisional por visión) ----------------------- #

def test_tulas_reportadas_vacio_al_inicio(dropbox):
    assert dropbox.leer_tulas_reportadas() == []


def test_idempotencia_tula_reportada(dropbox):
    r = {"manifiesto_id": "900009", "numero_tula": 1, "kg_reportado": 38.6, "origen": "vision"}
    assert dropbox.agregar_tulas_reportadas(r) is True
    assert dropbox.agregar_tulas_reportadas(dict(r)) is False              # misma llave
    assert dropbox.agregar_tulas_reportadas({**r, "numero_tula": 2}) is True
    assert len(dropbox.leer_tulas_reportadas()) == 2
