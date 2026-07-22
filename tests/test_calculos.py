"""Tests de Fase 2: core/calculos.py."""

import pytest

from core import calculos
from core.calculos import NO_DISPONIBLE, Tarifario
from datasources.astrid_mock import FuenteASTRIDMock


@pytest.fixture(scope="module")
def manifiesto_mock():
    return FuenteASTRIDMock().get_manifiesto("900007")


# --- Importación (cálculo puro) ------------------------------------------- #

def test_costo_importacion_sobre_1000():
    assert calculos.costo_importacion(1000).valor == 1060.00  # 1000*1.00 + 60


def test_costo_importacion_sobre_774():
    assert calculos.costo_importacion(774).valor == 834.00  # 774*1.00 + 60


def test_costo_importacion_sin_kg_no_disponible():
    r = calculos.costo_importacion(None)
    assert r.estado == NO_DISPONIBLE and r.motivo


# --- kg totales con fuente trazable --------------------------------------- #

def test_kg_sistema_total_mock_fuente_tulas(manifiesto_mock):
    r = calculos.kg_sistema_total(manifiesto_mock)
    assert r.ok
    assert r.valor == pytest.approx(1000.00, abs=0.01)
    assert r.detalle["fuente"] == "tulas"
    assert not r.advertencias


def test_kg_sistema_total_fuente_envios_con_advertencia():
    # Cobertura de tulas 10% (<80%) -> fuente envios + advertencia registrada.
    envios = [{"peso_kg": 2.0, "tula_codigo": None} for _ in range(9)]
    envios.append({"peso_kg": 5.0, "tula_codigo": "T-1"})
    manif = {"id": "X", "envios": envios,
             "tulas": [{"codigo": "T-1", "kg_sistema": 5.0, "kg_reportado": None}]}
    r = calculos.kg_sistema_total(manif)
    assert r.ok
    assert r.valor == 23.0                       # 9*2 + 5, por envíos
    assert r.detalle["fuente"] == "envios"
    assert r.advertencias
    assert "incompleta" in r.advertencias[0]


def test_kg_reportado_total_mock_ok(manifiesto_mock):
    r = calculos.kg_reportado_total(manifiesto_mock)
    assert r.ok
    assert 700 < r.valor < 780  # ~737 kg


def test_kg_reportado_total_sin_reportado_no_disponible():
    manif = {"id": "X", "envios": [], "tulas": [{"codigo": "T", "kg_sistema": 10, "kg_reportado": None}]}
    r = calculos.kg_reportado_total(manif)
    assert r.estado == NO_DISPONIBLE and "PENDIENTE_API" in r.motivo


# --- kg_reportado desde TULAS_REPORTADAS (pantallazo) --------------------- #

_TULAS_REP_900009 = [
    {"manifiesto_id": "900009", "numero_tula": i + 1, "kg_reportado": kg, "awb_master": "999-11112222"}
    for i, kg in enumerate([28.0, 27.0, 29.0, 26.0, 25.0, 30.0, 24.0, 28.0, 31.0, 22.0, 30.0])
]


def test_kg_reportado_usa_tulas_reportadas_en_excel():
    # Manifiesto excel-like: tulas sin peso reportado.
    manif = {"id": "900009", "envios": [{"guia": "g", "peso_kg": 300.0}],
             "tulas": [{"codigo": "T", "numero": 1, "kg_sistema": 300.0, "kg_reportado": None}]}
    r = calculos.kg_reportado_total(manif, _TULAS_REP_900009)
    assert r.ok
    assert r.valor == pytest.approx(300.0, abs=0.01)
    assert r.detalle["fuente"] == "tulas_reportadas"


def test_kg_reportado_prioriza_datasource(manifiesto_mock):
    # El mock ya trae tula.kg_reportado -> fuente "tulas" aunque haya reportadas.
    reportadas = [{"manifiesto_id": "900007", "numero_tula": 1, "kg_reportado": 9999.0}]
    r = calculos.kg_reportado_total(manifiesto_mock, reportadas)
    assert r.detalle["fuente"] == "tulas"


def test_kg_reportado_conflicto_de_fuentes_advertencia():
    # datasource 300.0 vs pantallazo 320.0 -> dif > 2 kg -> advertencia (no error).
    manif = {"id": "M", "envios": [],
             "tulas": [{"numero": 1, "kg_sistema": 300.0, "kg_reportado": 300.0}]}
    reportadas = [{"manifiesto_id": "M", "numero_tula": 1, "kg_reportado": 320.0}]
    r = calculos.kg_reportado_total(manif, reportadas)
    assert r.ok and r.valor == 300.0 and r.detalle["fuente"] == "tulas"   # prioridad datasource
    assert r.advertencias and "difieren" in r.advertencias[0]
    assert "300.0" in r.advertencias[0] and "320.0" in r.advertencias[0]


def test_kg_reportado_dentro_de_umbral_sin_advertencia():
    manif = {"id": "M", "envios": [],
             "tulas": [{"numero": 1, "kg_sistema": 300.0, "kg_reportado": 300.0}]}
    reportadas = [{"manifiesto_id": "M", "numero_tula": 1, "kg_reportado": 301.0}]  # dif 1 (<2 y <10%)
    r = calculos.kg_reportado_total(manif, reportadas)
    assert r.ok and not r.advertencias


# --- Distribución --------------------------------------------------------- #

@pytest.mark.parametrize("lb, esperado", [(5, 5), (8, 8), (8.2, 9), (9, 9), (10, 10)])
def test_costo_distribucion(lb, esperado):
    assert calculos.costo_distribucion(lb).valor == esperado


def test_costo_distribucion_sin_peso_no_disponible():
    assert calculos.costo_distribucion(None).estado == NO_DISPONIBLE


# --- Novedades de peso por tula ------------------------------------------- #

def test_novedad_tula3_alerta(manifiesto_mock):
    tula3 = next(t for t in manifiesto_mock["tulas"] if t["numero"] == 3)
    r = calculos.novedad_peso_tula(tula3)
    assert r.detalle["es_alerta"] is True
    assert r.detalle["dif_kg"] == pytest.approx(-230.00, abs=0.1)
    assert r.detalle["impacto_usd"] == pytest.approx(-230.00, abs=0.1)  # dif_kg * 1.00


def test_novedades_manifiesto_mock_tiene_alertas(manifiesto_mock):
    r = calculos.novedades_peso_manifiesto(manifiesto_mock)
    assert r.ok
    numeros_alerta = {n["numero"] for n in r.detalle["alertas"]}
    assert 3 in numeros_alerta    # error 500 lb (digitación)
    assert 15 in numeros_alerta   # +3.85 kg inyectado


def test_novedades_sin_reportado_no_disponible():
    manif = {"id": "X", "envios": [],
             "tulas": [{"codigo": "T", "kg_sistema": 10, "kg_reportado": None}]}
    r = calculos.novedades_peso_manifiesto(manif)
    assert r.estado == NO_DISPONIBLE
