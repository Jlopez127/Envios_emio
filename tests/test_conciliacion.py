"""Tests de Fase 2: core/conciliacion.py."""

from datetime import date
from pathlib import Path

import pytest

from core import calculos, conciliacion
from core.calculos import NO_DISPONIBLE
from datasources.astrid_excel import FuenteASTRIDExcel
from datasources.astrid_mock import FuenteASTRIDMock

DIR_FIXTURES = Path(__file__).parent / "fixtures"

# Factura DemoAir DEMO-0001: 774 kg × 1.00 + 10 + 50 = 834.00 (tarifa == pactada).
FACTURA_DEMO = {
    "numero": "DEMO-0001", "fecha": date(2026, 7, 16), "awb": "999-12345678",
    "kg_cobrados": 774.0, "tarifa_kg_usd": 1.00, "awb_fee_usd": 10.0,
    "pickup_entrega_usd": 50.0, "otros_cargos": [], "total_usd": 834.00,
}
# Idéntica pero a 1.10/kg: 774 × 1.10 + 60 = 911.40.
FACTURA_TARIFA_110 = {**FACTURA_DEMO, "tarifa_kg_usd": 1.10, "total_usd": 911.40}


@pytest.fixture(scope="module")
def manifiesto_mock():
    return FuenteASTRIDMock().get_manifiesto("900007")


# --- Conciliación importación --------------------------------------------- #

def test_sin_factura(manifiesto_mock):
    r = conciliacion.conciliar_importacion(manifiesto_mock, None)
    assert r["estado"] == "sin_factura"


def test_demo_sistema_vs_reportado(manifiesto_mock):
    r = conciliacion.conciliar_importacion(manifiesto_mock, FACTURA_DEMO)

    # Sobre kg_sistema: esperado 1060.00 -> delta -226.00 -> discrepancia (por peso).
    assert r["sobre_sistema"]["delta_total"] == pytest.approx(-226.00, abs=0.05)
    assert r["sobre_sistema"]["estado"] == "discrepancia"
    assert r["sobre_sistema"]["componentes"]["peso"]["impacto_usd"] == pytest.approx(-226.00, abs=0.05)

    # Sobre kg_reportado (774 kg): delta 0 -> conciliado (dentro de tolerancia).
    assert r["sobre_reportado"]["estado"] == "conciliado"
    assert abs(r["sobre_reportado"]["delta_total"]) <= r["sobre_reportado"]["tolerancia"]

    # Primaria = reportado; tarifa factura == pactada -> componente tarifa en cero.
    assert r["nivel_confianza"] == "reportado"
    assert r["estado"] == "conciliado"
    assert r["componentes"]["tarifa"]["impacto_usd"] == pytest.approx(0.0, abs=0.01)
    assert r["fuente_kg_sistema"] == "tulas"


def test_tarifa_110_discrepancia_por_tarifa(manifiesto_mock):
    r = conciliacion.conciliar_importacion(manifiesto_mock, FACTURA_TARIFA_110)
    tarifa = r["componentes"]["tarifa"]
    assert tarifa["impacto_usd"] == pytest.approx(77.40, abs=0.05)  # (1.10-1.00)*774
    assert tarifa["direccion"] == "en_contra"
    assert r["estado"] == "discrepancia"
    # El peso cuadra: el componente peso es chico frente a la discrepancia de tarifa.
    assert abs(r["componentes"]["peso"]["impacto_usd"]) < 15


def test_tarifa_menor_marcada_a_favor(manifiesto_mock):
    factura = {**FACTURA_DEMO, "tarifa_kg_usd": 0.90,
               "total_usd": round(774 * 0.90 + 60, 2)}
    r = conciliacion.conciliar_importacion(manifiesto_mock, factura)
    assert r["componentes"]["tarifa"]["impacto_usd"] < 0
    assert r["componentes"]["tarifa"]["direccion"] == "a_favor"


# --- Match de factura por AWB (datasource / tulas_reportadas / conflicto) - #

_TULAS_REP_900009 = [
    {"manifiesto_id": "900009", "numero_tula": i + 1, "kg_reportado": kg, "awb_master": "999-11112222"}
    for i, kg in enumerate([28.0, 27.0, 29.0, 26.0, 25.0, 30.0, 24.0, 28.0, 31.0, 22.0, 30.0])
]


def _manif_excel_900009():
    """Manifiesto estilo excel: sin awb_master ni peso reportado por tula."""
    return {"id": "900009", "fecha": "2026-07-17", "awb_master": None, "pallets": None,
            "envios": [{"guia": "g", "peso_kg": 300.0}],
            "tulas": [{"codigo": "T", "numero": 1, "kg_sistema": 300.0, "kg_reportado": None}]}


def test_match_por_awb_datasource():
    manif = {"id": "900007", "awb_master": "999-12345678", "fecha": "2026-07-15"}
    m = conciliacion.match_manifiesto_por_awb("999-12345678", [manif], [])
    assert m["estado"] == "unico" and m["via"] == "datasource" and m["manifiesto"]["id"] == "900007"


def test_match_por_awb_via_tulas_reportadas():
    m = conciliacion.match_manifiesto_por_awb("999-11112222", [_manif_excel_900009()], _TULAS_REP_900009)
    assert m["estado"] == "unico" and m["via"] == "tulas_reportadas"
    assert m["manifiesto"]["id"] == "900009"


def test_match_por_awb_conflicto_manifiestos_distintos():
    a = {"id": "900009", "awb_master": "AWB1", "fecha": "2026-07-17"}
    b = {"id": "900010", "awb_master": None, "fecha": "2026-07-20"}
    tr = [{"manifiesto_id": "900010", "awb_master": "AWB1"}]   # apunta a OTRO manifiesto
    m = conciliacion.match_manifiesto_por_awb("AWB1", [a, b], tr)
    assert m["estado"] == "conflicto"
    assert {x["id"] for x in m["candidatos"]} == {"900009", "900010"}


def test_match_por_awb_sin_match_o_null():
    manifiestos = [{"id": "X", "awb_master": "OTRA"}]
    assert conciliacion.match_manifiesto_por_awb("NADA", manifiestos, [])["estado"] == "sin_match"
    assert conciliacion.match_manifiesto_por_awb(None, manifiestos, [])["estado"] == "sin_match"


def test_conciliar_importacion_usa_tulas_reportadas():
    manif = _manif_excel_900009()
    factura = {"numero": "F9", "kg_cobrados": 300.0, "tarifa_kg_usd": 1.00, "awb_fee_usd": 10,
               "pickup_entrega_usd": 50, "otros_cargos": [], "total_usd": round(300.0 * 1.00 + 60, 2)}
    r = conciliacion.conciliar_importacion(manif, factura, None, _TULAS_REP_900009)
    assert r["kg_reportado"] == pytest.approx(300.0, abs=0.01)
    assert r["fuente_kg_reportado"] == "tulas_reportadas"     # fuente trazable
    assert r["nivel_confianza"] == "reportado"               # confianza alta con báscula
    assert r["estado"] == "conciliado"


# --- Conciliación distribución -------------------------------------------- #

def test_distribucion_sin_cobro():
    envio = {"guia": "1", "peso_lb": 5.0}
    r = conciliacion.conciliar_distribucion(envio, None)
    assert r["estado"] == "sin_cobro"
    assert r["esperado_usd"] == 5.0


def test_distribucion_conciliado():
    envio = {"guia": "1", "peso_lb": 10.0}          # esperado 10.0
    cobro = {"guia": "1", "valor_usd": 10.0, "lb_facturadas": 10}
    r = conciliacion.conciliar_distribucion(envio, cobro)
    assert r["estado"] == "conciliado" and r["delta"] == 0.0


def test_distribucion_discrepancia():
    envio = {"guia": "1", "peso_lb": 10.0}          # esperado 10.0
    cobro = {"guia": "1", "valor_usd": 14.0, "lb_facturadas": 14}
    r = conciliacion.conciliar_distribucion(envio, cobro)
    assert r["estado"] == "discrepancia" and r["delta"] == 4.0


# --- P&L ------------------------------------------------------------------ #

def _gasto_imp(mid, total):
    return {"fecha": date(2026, 7, 16), "manifiesto_id": mid, "proveedor": "DemoAir",
            "concepto": "importacion", "referencia": "DEMO-0001", "detalle_json": "{}",
            "total_usd": total, "origen": "manual"}


def test_pyl_manifiesto_completo(manifiesto_mock):
    r = conciliacion.pyl_manifiesto(manifiesto_mock, [_gasto_imp("900007", 834.00)])
    assert r["modo"] == "completo"
    assert r["ingresos_usd"] > 0
    assert r["tiene_gasto_importacion"] is True
    assert r["estado"] == "completo"
    assert r["utilidad_usd"] == pytest.approx(r["ingresos_usd"] - 834.00, abs=0.01)
    assert r["utilidad_por_kg_usd"] is not None


def test_pyl_manifiesto_parcial_sin_gasto_importacion(manifiesto_mock):
    r = conciliacion.pyl_manifiesto(manifiesto_mock, [])
    assert r["estado"] == "parcial"
    assert r["tiene_gasto_importacion"] is False


def test_pyl_periodo_parcial(manifiesto_mock):
    r = conciliacion.pyl_periodo([manifiesto_mock], [])
    assert r["estado"] == "parcial"
    assert r["n_manifiestos"] == 1


# --- Datasource excel (sintetico 900007, cobertura parcial): datos parciales - #

@pytest.fixture
def manifiesto_excel(directorio_sintetico):
    directorio, _ = directorio_sintetico
    return FuenteASTRIDExcel(directorio).get_manifiesto("900007")


def test_excel_novedades_no_disponible(manifiesto_excel):
    r = calculos.novedades_peso_manifiesto(manifiesto_excel)
    assert r.estado == NO_DISPONIBLE


def test_excel_pyl_solo_costos(manifiesto_excel):
    r = conciliacion.pyl_manifiesto(manifiesto_excel, [])
    assert r["modo"] == "solo_costos"
    assert r["ingresos_usd"] is None


def test_excel_conciliacion_solo_sistema(manifiesto_excel):
    r = conciliacion.conciliar_importacion(manifiesto_excel, FACTURA_DEMO)
    assert r["nivel_confianza"] == "solo_sistema"
    assert r["fuente_kg_sistema"] == "envios"
    assert r["advertencias"]  # "asignación de tulas incompleta ..."
    assert r["sobre_reportado"]["estado"] == NO_DISPONIBLE
