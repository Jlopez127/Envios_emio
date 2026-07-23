"""Estado de pago (nuevo alcance): consolidación append-only de PAGOS sobre GASTOS,
estado efectivo (pendiente/pagado/vencido) y cuentas por pagar."""

from datetime import date

from core import calculos, modelos, vista


def _gasto(mid, concepto, ref, total, **extra):
    return modelos.gasto_real(manifiesto_id=mid, concepto=concepto, referencia=ref,
                              total_usd=total, **extra)


# --- consolidar_estado_pago: append-only, último gana --------------------- #

def test_gasto_nace_pendiente():
    g = _gasto("M1", "importacion", "F1", 100.0)
    assert g["estado_pago"] == "pendiente"
    assert g["fecha_pago"] is None and g["comprobante_ref"] is None


def test_consolidar_marca_pagado_sin_editar_gasto():
    gasto = _gasto("M1", "importacion", "F1", 100.0)
    pago = modelos.construir_pago(gasto=gasto, monto_usd=100.0, referencia_pago="OP-1",
                                  usuario="admin1", comprobante_ref="/x/comp.png")
    fusion = modelos.consolidar_estado_pago([gasto], [pago])
    assert fusion[0]["estado_pago"] == "pagado"
    assert fusion[0]["referencia_pago"] == "OP-1"
    assert fusion[0]["comprobante_ref"] == "/x/comp.png"
    # la fila del gasto original NO se editó (append-only).
    assert gasto["estado_pago"] == "pendiente"


def test_consolidar_ultimo_pago_gana():
    gasto = _gasto("M1", "distribucion", "F2", 50.0)
    p1 = modelos.construir_pago(gasto=gasto, monto_usd=25.0, referencia_pago="P1", usuario="a")
    p2 = modelos.construir_pago(gasto=gasto, monto_usd=50.0, referencia_pago="P2", usuario="a")
    fusion = modelos.consolidar_estado_pago([gasto], [p1, p2])
    assert fusion[0]["referencia_pago"] == "P2"           # el último de la hoja gana


# --- estado efectivo: vencido ---------------------------------------------- #

def test_estado_vencido_si_vencimiento_pasado_y_no_pagado():
    g = _gasto("M1", "importacion", "F1", 100.0, fecha_vencimiento="2026-07-01")
    assert calculos.estado_pago_efectivo(g, hoy=date(2026, 7, 23)) == "vencido"


def test_estado_pendiente_si_vencimiento_futuro():
    g = _gasto("M1", "importacion", "F1", 100.0, fecha_vencimiento="2026-08-30")
    assert calculos.estado_pago_efectivo(g, hoy=date(2026, 7, 23)) == "pendiente"


def test_estado_pagado_no_es_vencido_aunque_pase_la_fecha():
    g = _gasto("M1", "importacion", "F1", 100.0, fecha_vencimiento="2026-07-01",
               estado_pago="pagado")
    assert calculos.estado_pago_efectivo(g, hoy=date(2026, 7, 23)) == "pagado"


def test_estado_pendiente_sin_vencimiento():
    g = _gasto("M1", "importacion", "F1", 100.0)
    assert calculos.estado_pago_efectivo(g, hoy=date(2026, 7, 23)) == "pendiente"


# --- cuentas por pagar ----------------------------------------------------- #

def test_cuentas_por_pagar_totales():
    gastos = [
        _gasto("M1", "importacion", "F1", 100.0, fecha_vencimiento="2026-07-01"),  # vencido
        _gasto("M2", "importacion", "F2", 200.0, fecha_vencimiento="2026-08-30"),  # pendiente
        _gasto("M1", "distribucion", "D1", 40.0, estado_pago="pagado"),            # pagado
        _gasto("M2", "distribucion", "D2", 60.0),                                  # pendiente
    ]
    cp = vista.cuentas_por_pagar(gastos, hoy=date(2026, 7, 23))
    assert cp["facturado_usd"] == 400.0
    assert cp["pagado_usd"] == 40.0
    assert cp["pendiente_aerolineas_usd"] == 300.0        # 100 + 200
    assert cp["pendiente_astrid_usd"] == 60.0
    assert cp["pendiente_total_usd"] == 360.0
    assert cp["vencido_usd"] == 100.0 and cp["n_vencidas"] == 1
