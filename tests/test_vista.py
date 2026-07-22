"""Tests del rediseño: agregados de presentación (core/vista.py)."""

import pytest

from core import vista
from core.calculos import Tarifario
from datasources.astrid_mock import FuenteASTRIDMock


@pytest.fixture(scope="module")
def mock():
    return FuenteASTRIDMock()


@pytest.fixture(scope="module")
def m7(mock):
    return mock.get_manifiesto("900007")


# --- KPIs: los filtros (subset) cambian los KPIs ------------------------- #

def test_kpis_cambian_con_subset(mock):
    m7 = mock.get_manifiesto("900007")
    m9 = mock.get_manifiesto("900009")
    ambos = vista.kpis_periodo([m7, m9], [], Tarifario())
    solo7 = vista.kpis_periodo([m7], [], Tarifario())
    assert ambos["n_manifiestos"] == 2 and solo7["n_manifiestos"] == 1
    assert ambos["n_envios"] > solo7["n_envios"]        # el filtro cambia los KPIs
    assert solo7["n_envios"] == 316


def test_kpis_pagos_utilidad_y_factura(m7):
    gastos = [{"manifiesto_id": "900007", "concepto": "importacion", "total_usd": 834.00},
              {"manifiesto_id": "900007", "concepto": "distribucion", "total_usd": 50.0}]
    k = vista.kpis_periodo([m7], gastos, Tarifario())
    assert k["pagado_aerolineas"] == 834.00 and k["pagado_astrid"] == 50.0
    assert k["ingresos"] is not None and k["modo_ingresos"] == "completo"   # mock trae valor_cobrado
    assert k["pct_con_factura"] == 100.0
    assert k["kg_sistema"] == pytest.approx(1000.00, abs=0.01)


def test_kpis_ingresos_none_solo_costos_honesto():
    manif = {"id": "X", "fecha": "2026-07-01", "tulas": [],
             "envios": [{"peso_lb": 5, "peso_kg": 2.3, "valor_cobrado_cliente_usd": None,
                         "departamento": "Antioquia", "casillero": "C1"}]}
    gastos = [{"manifiesto_id": "X", "concepto": "importacion", "total_usd": 100.0}]
    k = vista.kpis_periodo([manif], gastos, Tarifario())
    assert k["ingresos"] is None and k["modo_ingresos"] == "solo_costos"
    assert k["utilidad"] == -100.0                       # resultado provisional de solo costos


# --- Participaciones y rankings ------------------------------------------ #

def test_participacion_por_departamento_suma_100(m7):
    part = vista.participacion_por_departamento([m7])
    assert part["por_envios"] and part["por_envios"][0][2] > 0
    total = sum(p for _, _, p in part["por_envios"])
    assert 99.0 <= total <= 101.0                        # % suman ~100


def test_top_clientes(m7):
    tc = vista.top_clientes([m7], n=10)
    assert 0 < len(tc["items"]) <= 10
    assert tc["campo"] in ("cliente", "casillero")


# --- Drill-down de tula: confirmado (mock) vs heurística (excel) ---------- #

def test_drilldown_confirmado_con_tula(m7):
    tula3 = next(t for t in m7["tulas"] if t["numero"] == 3)
    dd = vista.envios_de_tula(m7, tula3["codigo"])
    assert dd["confirmado"] is True
    # El error de 500 lb (guía 990001) debe saltar primero (orden por peso desc).
    assert dd["envios"][0]["peso_lb"] == 500
    assert dd["envios"][0]["guia"] == "990001"


def test_drilldown_heuristica_sin_asignacion():
    envios = [{"guia": f"g{i}", "contenido": "x", "peso_lb": float(i), "peso_kg": i * 0.45,
               "tula_codigo": None} for i in range(1, 20)]
    manif = {"id": "E", "envios": envios, "tulas": []}
    dd = vista.envios_de_tula(manif, "codigo-inexistente", top_n=5)
    assert dd["confirmado"] is False                     # sin asignación -> heurística
    assert len(dd["envios"]) == 5
    assert dd["envios"][0]["peso_lb"] == 19.0            # ordenado por peso desc


# --- Manifiestos sin cobro ----------------------------------------------- #

def test_manifiestos_sin_cobro():
    manifiestos = [{"id": "A", "fecha": "2026-07-01"}, {"id": "B", "fecha": "2026-07-02"}]
    gastos = [{"manifiesto_id": "A", "concepto": "importacion", "total_usd": 10}]
    cobros = [{"manifiesto_id": "A", "guia": "g"}]
    sin = vista.manifiestos_sin_cobro(manifiestos, gastos, cobros)
    ids = {s["id"] for s in sin}
    assert "B" in ids                                     # B no tiene nada
    assert "A" not in ids                                 # A tiene factura y cobro ASTRID
