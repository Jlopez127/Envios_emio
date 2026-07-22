"""Tests de Fase 1: interfaz FuenteASTRID y su mock FuenteASTRIDMock."""

from datetime import date

import pytest

from datasources.astrid_mock import FuenteASTRIDMock
from datasources.base import FuenteASTRID, ManifiestoResumen


@pytest.fixture
def fuente():
    return FuenteASTRIDMock()


def test_mock_cumple_la_interfaz(fuente):
    assert isinstance(fuente, FuenteASTRID)


# --- Manifiesto 900007 (escenario DEMO) --------------------------------------- #

def test_900007_conteos(fuente):
    m = fuente.get_manifiesto("900007")
    assert len(m["envios"]) == 316
    assert len(m["tulas"]) == 27


def test_900007_kg_sistema_total(fuente):
    m = fuente.get_manifiesto("900007")
    total = sum(t["kg_sistema"] for t in m["tulas"])
    assert total == pytest.approx(1000.00, abs=0.01)


def test_900007_tula3_diferencia(fuente):
    m = fuente.get_manifiesto("900007")
    tula3 = next(t for t in m["tulas"] if t["numero"] == 3)
    diferencia = tula3["kg_reportado"] - tula3["kg_sistema"]
    assert diferencia == pytest.approx(-230.00, abs=0.1)


def test_900007_guia_990001_error_digitacion(fuente):
    m = fuente.get_manifiesto("900007")
    envio = next(e for e in m["envios"] if e["guia"] == "990001")
    tula3 = next(t for t in m["tulas"] if t["numero"] == 3)
    assert envio["peso_lb"] == 500
    assert envio["tula_codigo"] == tula3["codigo"] == "260714-900007-3"
    assert "Cargador" in envio["contenido"]
    # Se factura con el peso corregido (5.00 lb), no con 500.
    assert envio["valor_cobrado_cliente_usd"] < 60


def test_900007_resumen(fuente):
    resumenes = {r.id: r for r in fuente.get_manifiestos(date(2026, 7, 1), date(2026, 7, 31))}
    r = resumenes["900007"]
    assert isinstance(r, ManifiestoResumen)
    assert r.n_envios == 316
    assert r.n_tulas == 27
    assert r.awb_master == "999-12345678"
    assert r.kg_sistema_total == pytest.approx(1000.00, abs=0.01)


# --- Manifiesto 900009 (escenario limpio, sin alertas) -------------------------- #

def test_900009_kg_reportado_total(fuente):
    m = fuente.get_manifiesto("900009")
    total = sum(t["kg_reportado"] for t in m["tulas"])
    assert total == pytest.approx(300.0, abs=0.01)
    assert len(m["tulas"]) == 11
    assert len(m["envios"]) == 31


def test_900009_sin_alertas_de_peso(fuente):
    m = fuente.get_manifiesto("900009")
    for t in m["tulas"]:
        assert abs(t["kg_reportado"] - t["kg_sistema"]) < 2.0


# --- Interfaz general ----------------------------------------------------- #

def test_get_manifiestos_filtra_por_fechas(fuente):
    resumenes = fuente.get_manifiestos(date(2026, 7, 16), date(2026, 7, 18))
    ids = {r.id for r in resumenes}
    assert "900008" in ids   # 2026-07-16
    assert "900009" in ids   # 2026-07-17
    assert "900007" not in ids  # 2026-07-15, fuera del rango
    assert "900010" not in ids  # 2026-07-20, fuera del rango


def test_get_manifiestos_sin_limites_devuelve_los_8(fuente):
    resumenes = fuente.get_manifiestos()
    assert len(resumenes) == 8
    # Ordenados por fecha ascendente.
    fechas = [r.fecha for r in resumenes]
    assert fechas == sorted(fechas)


def test_get_manifiesto_desconocido_lanza_keyerror(fuente):
    with pytest.raises(KeyError):
        fuente.get_manifiesto("9999999")


def test_datos_deterministicos(fuente):
    a = FuenteASTRIDMock().get_manifiesto("900007")
    b = FuenteASTRIDMock().get_manifiesto("900007")
    assert a == b
