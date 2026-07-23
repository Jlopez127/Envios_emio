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
from core.calculos import Tarifario
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
    # Estado de pago: nace pendiente, con vencimiento (Net 30 desde la fecha).
    "estado_pago": "pendiente",
    "fecha_pago": None,
    "referencia_pago": None,
    "fecha_vencimiento": date(2026, 8, 15).isoformat(),
    "comprobante_ref": None,
}

# Despacho consolidado DEMO sobre guías del mock 900007 (comercial 100006/7/8): muestra
# el ahorro y evita el doble conteo (esas guías NO figuran como pendientes individuales).
_CONSOLIDADOS_PRECARGA = [
    {"consolidado_id": "CONS-900007-01", "manifiesto_id": "900007",
     "guias": ["100006", "100007", "100008"], "peso_total_lb": 24.0,
     "valor_cobrado_usd": 21.0, "transportadora": "TransConsol"},
]

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


def _llave_pago(p: dict) -> tuple:
    return (p.get("manifiesto_id"), p.get("concepto"), p.get("referencia"), p.get("referencia_pago"))


def _llave_consolidado(c: dict) -> tuple:
    return (c.get("manifiesto_id"), c.get("consolidado_id"))


def _llave_reajuste(r: dict) -> tuple:
    return (r.get("archivo_ref"),)


class FuenteDropboxMock(FuenteDropbox):
    """Persistencia en memoria (ver docstring del módulo)."""

    def __init__(self) -> None:
        self._novedades: list = []
        self._gastos: list = [copy.deepcopy(_GASTO_DEMO)]
        self._cobros: list = [copy.deepcopy(c) for c in _COBROS_PRECARGA]
        self._tulas_reportadas: list = []
        self._pagos: list = []
        self._consolidaciones: list = [copy.deepcopy(c) for c in _CONSOLIDADOS_PRECARGA]
        self._reajustes: list = []
        self._archivos: dict = {}
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

    def leer_pagos(self) -> list:
        return copy.deepcopy(self._pagos)

    def leer_consolidaciones(self) -> list:
        return copy.deepcopy(self._consolidaciones)

    def leer_reajustes(self) -> list:
        return copy.deepcopy(self._reajustes)

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

    def agregar_pago(self, pago) -> bool:
        llave = _llave_pago(pago)
        if any(_llave_pago(p) == llave for p in self._pagos):
            return False
        self._pagos.append(copy.deepcopy(pago))
        return True

    def agregar_consolidado(self, consolidado) -> bool:
        llave = _llave_consolidado(consolidado)
        if any(_llave_consolidado(c) == llave for c in self._consolidaciones):
            return False
        self._consolidaciones.append(copy.deepcopy(consolidado))
        return True

    def agregar_reajuste(self, reajuste) -> bool:
        llave = _llave_reajuste(reajuste)
        if any(_llave_reajuste(r) == llave for r in self._reajustes):
            return False
        self._reajustes.append(copy.deepcopy(reajuste))
        return True

    # -- Archivos adjuntos (en memoria) ----------------------------------- #
    def guardar_archivo(self, subcarpeta: str, nombre: str, datos: bytes) -> str:
        ruta = f"/portal_envios/{subcarpeta.strip('/')}/{nombre}"
        self._archivos[ruta] = bytes(datos)
        return ruta

    def leer_archivo(self, ruta: str) -> bytes:
        return self._archivos[ruta]
