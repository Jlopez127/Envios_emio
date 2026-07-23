"""Consolidaciones de despacho (nuevo alcance): costo consolidado sobre el peso total,
métrica de ahorro, conciliación y no-doble-conteo de guías."""

from core import calculos, conciliacion, modelos, vista
from core.calculos import Tarifario

TAR = Tarifario()  # DEMO: dist_base 5 USD hasta 5 lb, +1 USD/lb (ceil)


def _manif():
    """Manifiesto con 3 guías de 4 lb c/u (costo individual = 5 USD c/u = 15)."""
    return {"id": "M1", "envios": [
        {"guia": "g1", "peso_lb": 4.0}, {"guia": "g2", "peso_lb": 4.0},
        {"guia": "g3", "peso_lb": 4.0}, {"guia": "g4", "peso_lb": 2.0}]}


def _consol(guias, peso, valor=None):
    return modelos.construir_consolidado(
        consolidado_id="C1", manifiesto_id="M1", guias=guias,
        peso_total_lb=peso, valor_cobrado_usd=valor, transportadora="T")


# --- costo consolidado: MISMA regla sobre el peso TOTAL -------------------- #

def test_costo_consolidado_usa_peso_total():
    # 12 lb total -> 5 (base 5 lb) + (12-5)*1 = 12.00
    r = calculos.costo_consolidado(_consol(["g1", "g2", "g3"], 12.0), TAR)
    assert r.ok and r.valor == 12.0
    assert r.detalle["lb_facturable"] == 12


def test_costo_consolidado_sin_peso_no_disponible():
    r = calculos.costo_consolidado(_consol(["g1"], None), TAR)
    assert not r.ok


# --- ahorro: suma individual vs consolidado -------------------------------- #

def test_ahorro_individual_vs_consolidado():
    # Individual: 3 guías de 4 lb -> 5 USD c/u = 15. Consolidado 12 lb -> 12. Ahorro 3.
    r = calculos.ahorro_consolidado(_consol(["g1", "g2", "g3"], 12.0), _manif(), TAR)
    assert r.ok
    assert r.detalle["costo_individual_usd"] == 15.0
    assert r.detalle["costo_consolidado_usd"] == 12.0
    assert r.detalle["ahorro_usd"] == 3.0


def test_ahorro_guias_sin_peso_se_excluyen_con_aviso():
    r = calculos.ahorro_consolidado(_consol(["g1", "gX"], 8.0), _manif(), TAR)
    assert r.ok
    assert r.detalle["guias_sin_peso"] == ["gX"]
    assert r.advertencias                                   # aviso trazable


# --- conciliación del consolidado ------------------------------------------ #

def test_conciliar_consolidado_conciliado():
    r = conciliacion.conciliar_consolidado(_consol(["g1", "g2", "g3"], 12.0, valor=12.0), _manif(), TAR)
    assert r["estado"] == "conciliado"
    assert r["esperado_usd"] == 12.0 and r["delta"] == 0.0
    assert r["ahorro_usd"] == 3.0


def test_conciliar_consolidado_discrepancia():
    r = conciliacion.conciliar_consolidado(_consol(["g1", "g2", "g3"], 12.0, valor=20.0), _manif(), TAR)
    assert r["estado"] == "discrepancia" and r["delta"] == 8.0


def test_conciliar_consolidado_sin_cobro():
    r = conciliacion.conciliar_consolidado(_consol(["g1"], 12.0, valor=None), _manif(), TAR)
    assert r["estado"] == "sin_cobro"


# --- no doble conteo: guías del consolidado quedan fuera del individual ----- #

def test_guias_consolidadas_para_excluir():
    cons = [_consol(["g1", "g2"], 8.0), modelos.construir_consolidado(
        consolidado_id="C2", manifiesto_id="M1", guias=["g3"], peso_total_lb=4.0,
        valor_cobrado_usd=5.0)]
    assert vista.guias_consolidadas(cons) == {"g1", "g2", "g3"}


def test_ahorro_agregado_periodo():
    cons = [_consol(["g1", "g2", "g3"], 12.0, valor=12.0)]
    agg = vista.ahorro_consolidados(cons, [_manif()], TAR)
    assert agg["n_consolidados"] == 1
    assert agg["individual_usd"] == 15.0
    assert agg["consolidado_usd"] == 12.0
    assert agg["ahorro_usd"] == 3.0


def test_manifiesto_con_consolidado_no_figura_sin_cobro():
    manifiestos = [{"id": "M1", "fecha": "2026-07-01"}]
    gastos = [{"manifiesto_id": "M1", "concepto": "importacion", "total_usd": 10}]
    cons = [_consol(["g1"], 4.0, valor=5.0)]
    sin = vista.manifiestos_sin_cobro(manifiestos, gastos, [], cons)
    # M1 tiene factura (gasto import) y cobro ASTRID (vía consolidado) -> no aparece.
    assert not any(s["id"] == "M1" for s in sin)
