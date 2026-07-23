"""Modelos de dominio del portal (Manifiesto, Tula, Envio, FacturaAerolinea,
CobroDistribucion, Novedad, GastoReal, Pago, DespachoConsolidado, Reajuste, Tarifario).

Estructura canonica definida en docs/CONTRATO_DATOS.md.
"""

import json
from datetime import date

# Estados de pago de un GastoReal (ver docs/CONTRATO_DATOS.md).
PAGO_PENDIENTE = "pendiente"
PAGO_PAGADO = "pagado"


def construir_novedad(*, usuario, manifiesto_id, tipo, discriminador, campo_disc,
                      valor_esperado, valor_real, delta, justificacion, accion, fecha=None):
    """Construye el dict de una Novedad resuelta (ver docs/CONTRATO_DATOS.md).

    `usuario` es quien justifica: queda REGISTRADO en la novedad (auditoría). `campo_disc`
    indica si `discriminador` va como `tula_codigo` o como `guia`. `fecha` por defecto hoy.
    """
    return {
        "fecha": fecha or date.today().isoformat(),
        "usuario": usuario,
        "manifiesto_id": manifiesto_id,
        "tula_codigo": discriminador if campo_disc == "tula_codigo" else None,
        "guia": discriminador if campo_disc == "guia" else None,
        "tipo": tipo,
        "valor_esperado": valor_esperado,
        "valor_real": valor_real,
        "delta": delta,
        "justificacion": justificacion,
        "accion": accion,
        "estado": "resuelta",
    }


def gasto_real(*, manifiesto_id, concepto, referencia, total_usd, proveedor=None,
               detalle=None, origen="manual", fecha=None, estado_pago=PAGO_PENDIENTE,
               fecha_pago=None, referencia_pago=None, fecha_vencimiento=None,
               comprobante_ref=None):
    """Construye el dict de un GastoReal (ver docs/CONTRATO_DATOS.md).

    Nace `pendiente` de pago por defecto. `detalle` (dict) se serializa a
    `detalle_json` (fuente canónica de la factura). Los campos de pago se pueden
    consolidar luego con `consolidar_estado_pago` a partir de la hoja PAGOS.
    """
    return {
        "fecha": fecha or date.today().isoformat(),
        "manifiesto_id": manifiesto_id,
        "proveedor": proveedor or "Aerolínea",
        "concepto": concepto,
        "referencia": referencia,
        "detalle_json": detalle if isinstance(detalle, str) else json.dumps(detalle or {}, ensure_ascii=False),
        "total_usd": total_usd,
        "origen": origen,
        "estado_pago": estado_pago,
        "fecha_pago": fecha_pago,
        "referencia_pago": referencia_pago,
        "fecha_vencimiento": fecha_vencimiento,
        "comprobante_ref": comprobante_ref,
    }


def llave_gasto(g):
    """Llave de un gasto (y de los pagos que lo referencian): (manifiesto_id, concepto, referencia)."""
    return (g.get("manifiesto_id"), g.get("concepto"), g.get("referencia"))


def construir_pago(*, gasto, monto_usd, referencia_pago, usuario, banco=None,
                   destinatario=None, comprobante_ref=None, fecha=None):
    """Fila de PAGO que marca un gasto como pagado SIN editar la fila del gasto
    (append-only). Referencia el gasto por su llave (manifiesto_id, concepto, referencia)."""
    return {
        "fecha": fecha or date.today().isoformat(),
        "manifiesto_id": gasto.get("manifiesto_id"),
        "concepto": gasto.get("concepto"),
        "referencia": gasto.get("referencia"),
        "monto_usd": monto_usd,
        "referencia_pago": referencia_pago,
        "banco": banco,
        "destinatario": destinatario,
        "comprobante_ref": comprobante_ref,
        "usuario": usuario,
        "estado_pago": PAGO_PAGADO,
    }


def consolidar_estado_pago(gastos, pagos):
    """Aplica los PAGOS sobre los GASTOS (append-only: la fila del gasto no se edita).

    Devuelve una lista NUEVA de gastos con `estado_pago`/`fecha_pago`/`referencia_pago`/
    `comprobante_ref` actualizados. Regla: **último pago gana** (orden de aparición en
    la hoja PAGOS). No muta las entradas de entrada.
    """
    ultimo = {}
    for p in pagos or []:
        ultimo[llave_gasto(p)] = p  # el último de la hoja para esa llave gana
    salida = []
    for g in gastos or []:
        g = dict(g)
        p = ultimo.get(llave_gasto(g))
        if p is not None:
            g["estado_pago"] = p.get("estado_pago", PAGO_PAGADO)
            g["fecha_pago"] = p.get("fecha")
            g["referencia_pago"] = p.get("referencia_pago")
            g["comprobante_ref"] = p.get("comprobante_ref")
        else:
            g.setdefault("estado_pago", PAGO_PENDIENTE)
        salida.append(g)
    return salida


def construir_consolidado(*, consolidado_id, manifiesto_id, guias, peso_total_lb,
                          valor_cobrado_usd, transportadora=None):
    """DespachoConsolidado: varios envíos consolidados en un despacho (rompe el 1:1
    guía↔cobro). `guias` es la lista de guías incluidas."""
    return {
        "consolidado_id": consolidado_id,
        "manifiesto_id": manifiesto_id,
        "guias": list(guias or []),
        "peso_total_lb": peso_total_lb,
        "valor_cobrado_usd": valor_cobrado_usd,
        "transportadora": transportadora,
    }


def construir_reajuste(*, usuario, archivo_ref, manifiesto_id=None, guia=None,
                       valor_usd=None, motivo=None, texto_resumen=None, fecha=None,
                       origen="vision"):
    """Reajuste recibido (solo recepción/archivo en esta fase). Campos best-effort:
    todo puede ser None si la extracción no reconoce el formato (NUNCA inventar)."""
    return {
        "fecha": fecha or date.today().isoformat(),
        "manifiesto_id": manifiesto_id,
        "guia": guia,
        "valor_usd": valor_usd,
        "motivo": motivo,
        "texto_resumen": texto_resumen,
        "archivo_ref": archivo_ref,
        "usuario": usuario,
        "origen": origen,
    }
