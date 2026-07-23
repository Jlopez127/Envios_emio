"""Comprobante de transferencia (nuevo alcance): extracción por visión, validación de
monto contra la factura (avisa, no bloquea) y registro del pago."""

import json

from core import modelos
from datasources.dropbox_mock import FuenteDropboxMock
from vision import extractor


def _invocar(payload):
    return lambda prompt, imagenes: json.dumps(payload)


# --- Extracción ------------------------------------------------------------ #

def test_extraer_comprobante():
    payload = {"fecha": "2026-07-20", "monto": 834.0, "referencia": "OP-12345",
               "banco": "Bancolombia", "destinatario": "ASTRID"}
    datos = extractor.extraer([], "comprobante_transferencia", invocar=_invocar(payload))
    assert datos["monto"] == 834.0 and datos["referencia"] == "OP-12345"


def test_extraer_comprobante_campos_null():
    payload = {"fecha": None, "monto": 500.0, "referencia": None, "banco": None,
               "destinatario": None}
    datos = extractor.extraer([], "comprobante_transferencia", invocar=_invocar(payload))
    assert datos["monto"] == 500.0 and datos["referencia"] is None


# --- Validación de monto contra la factura --------------------------------- #

def test_validar_comprobante_monto_coincide():
    datos = {"monto": 834.0, "referencia": "OP-1"}
    ok, avisos = extractor.validar_comprobante(datos, factura_total=834.0)
    assert ok and avisos == []


def test_validar_comprobante_monto_difiere_avisa_no_bloquea():
    datos = {"monto": 400.0, "referencia": "OP-1"}
    ok, avisos = extractor.validar_comprobante(datos, factura_total=834.0)
    assert ok is True                                    # NO bloquea (pago parcial/agrupado)
    assert any("difiere" in a for a in avisos)


def test_validar_comprobante_sin_monto_no_registrable():
    ok, avisos = extractor.validar_comprobante({"monto": None}, factura_total=834.0)
    assert ok is False and avisos


def test_validar_comprobante_sin_referencia_avisa():
    ok, avisos = extractor.validar_comprobante({"monto": 834.0, "referencia": None}, 834.0)
    assert ok is True and any("referencia" in a for a in avisos)


# --- Registro del pago (append-only + idempotencia + archivo) -------------- #

def test_registrar_pago_marca_gasto_pagado():
    dbx = FuenteDropboxMock()
    gasto = modelos.gasto_real(manifiesto_id="M1", concepto="distribucion",
                               referencia="F1", total_usd=100.0)
    dbx.agregar_gasto_real(gasto)
    ruta = dbx.guardar_archivo("comprobantes", "comp.png", b"bytes-imagen")
    assert dbx.leer_archivo(ruta) == b"bytes-imagen"

    pago = modelos.construir_pago(gasto=gasto, monto_usd=100.0, referencia_pago="OP-9",
                                  usuario="admin1", comprobante_ref=ruta)
    assert dbx.agregar_pago(pago) is True
    assert dbx.agregar_pago(dict(pago)) is False          # idempotente

    gastos = modelos.consolidar_estado_pago(dbx.leer_gastos_reales(), dbx.leer_pagos())
    pagado = next(g for g in gastos if g["referencia"] == "F1")
    assert pagado["estado_pago"] == "pagado"
    assert pagado["comprobante_ref"] == ruta
