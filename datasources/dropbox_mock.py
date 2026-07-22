"""Implementación mock de la persistencia Dropbox (en memoria, sin archivos).

Permite desarrollar el dashboard y la lógica de append-only/idempotencia sin tocar
Dropbox real. Cumple la interfaz de datasources/dropbox_base.py.

Precargado (datos DEMO sintéticos) para que el dashboard muestre datos al abrir:
  - GASTOS_REALES: la factura DEMO (proveedor DemoAir, DEMO-0001) como gasto de
    importación del manifiesto 900007 (total 834.00, cuadra con el tarifario DEMO). El
    detalle viaja en `detalle_json` para reconstruir la FacturaAerolinea en la conciliación.
  - COBROS_DISTRIBUCION: 3 cobros sobre guías del mock 900007, con valores no enteros
    (el esperado de distribución siempre es entero) → discrepancias visibles.
  - NOVEDADES: vacío (se llenan justificando desde el dashboard).
"""

from __future__ import annotations

import copy
from datetime import date

import config
from datasources.dropbox_base import CobroDistribucion, FuenteDropbox, GastoReal, Novedad

# --- Precarga (DEMO sintético; cuadra con el tarifario DEMO 1.00/10/50) ---- #

_GASTO_DEMO = {
    "fecha": date(2026, 7, 16).isoformat(),
    "manifiesto_id": "900007",
    "proveedor": "DemoAir",
    "concepto": "importacion",
    "referencia": "DEMO-0001",
    "detalle_json": ('{"kg_cobrados": 774.0, "tarifa_kg_usd": 1.00, '
                     '"awb_fee_usd": 10.0, "pickup_entrega_usd": 50.0, "otros_cargos": []}'),
    "total_usd": 834.00,
    "origen": "manual",
}

# Guías que existen en el mock 900007 (rango comercial/estándar). Valores NO enteros
# para garantizar delta != 0 contra el esperado (que siempre es entero).
_COBROS_PRECARGA = [
    {"guia": "100005", "manifiesto_id": "900007", "transportadora": "TransA",
     "lb_facturadas": 6, "valor_usd": 12.50},
    {"guia": "100150", "manifiesto_id": "900007", "transportadora": "TransB",
     "lb_facturadas": 22, "valor_usd": 26.75},
    {"guia": "100250", "manifiesto_id": "900007", "transportadora": "TransC",
     "lb_facturadas": 3, "valor_usd": 6.25},
]


def _llave_novedad(n: dict) -> tuple:
    return (n.get("manifiesto_id"), n.get("tula_codigo") or n.get("guia"), n.get("tipo"))


def _llave_gasto(g: dict) -> tuple:
    return (g.get("manifiesto_id"), g.get("concepto"), g.get("referencia"))


def _llave_cobro(c: dict) -> tuple:
    return (c.get("manifiesto_id"), c.get("guia"))


def _llave_tula_reportada(t: dict) -> tuple:
    return (t.get("manifiesto_id"), t.get("numero_tula"))


class FuenteDropboxMock(FuenteDropbox):
    """Persistencia en memoria (ver docstring del módulo)."""

    def __init__(self) -> None:
        self._novedades: list = []
        self._gastos: list = [copy.deepcopy(_GASTO_DEMO)]
        self._cobros: list = [copy.deepcopy(c) for c in _COBROS_PRECARGA]
        self._tulas_reportadas: list = []
        self._tarifario = config.tarifario_base()

    # -- Lecturas (copias defensivas) ------------------------------------- #
    def leer_novedades(self) -> list:
        return copy.deepcopy(self._novedades)

    def leer_gastos_reales(self) -> list:
        return copy.deepcopy(self._gastos)

    def leer_cobros_distribucion(self) -> list:
        return copy.deepcopy(self._cobros)

    def leer_tulas_reportadas(self) -> list:
        return copy.deepcopy(self._tulas_reportadas)

    def leer_tarifario(self) -> Tarifario:
        return self._tarifario

    # -- Escrituras (append-only + idempotencia) -------------------------- #
    def agregar_novedad(self, novedad: Novedad) -> bool:
        llave = _llave_novedad(novedad)
        if any(_llave_novedad(n) == llave for n in self._novedades):
            return False
        self._novedades.append(copy.deepcopy(novedad))
        return True

    def agregar_gasto_real(self, gasto: GastoReal) -> bool:
        llave = _llave_gasto(gasto)
        if any(_llave_gasto(g) == llave for g in self._gastos):
            return False
        self._gastos.append(copy.deepcopy(gasto))
        return True

    def agregar_cobro_distribucion(self, cobro: CobroDistribucion) -> bool:
        llave = _llave_cobro(cobro)
        if any(_llave_cobro(c) == llave for c in self._cobros):
            return False
        self._cobros.append(copy.deepcopy(cobro))
        return True

    def agregar_tulas_reportadas(self, registro) -> bool:
        llave = _llave_tula_reportada(registro)
        if any(_llave_tula_reportada(t) == llave for t in self._tulas_reportadas):
            return False
        self._tulas_reportadas.append(copy.deepcopy(registro))
        return True
