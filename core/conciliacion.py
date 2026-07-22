"""Conciliación (importación y distribución) y P&L, contra las interfaces de datos.

Rige la misma REGLA TRANSVERSAL que core/calculos.py: datos completos o parciales;
faltantes esperados → "no_disponible" con motivo; nunca excepción, nunca inventar.

Los gastos reales se INYECTAN como lista de `GastoReal` (dicts estilo hoja
GASTOS_REALES). El motor no conoce Dropbox: la interfaz concreta se enchufa en Fase 5
sin tocar este módulo.
"""

from __future__ import annotations

from typing import Optional

from core import calculos
from core.calculos import NO_DISPONIBLE, Tarifario


# --------------------------------------------------------------------------- #
# Conciliación importación (FacturaAerolinea vs cálculo propio)
# --------------------------------------------------------------------------- #

def _tolerancia_importacion(esperado: float) -> float:
    return round(max(10.0, 0.015 * esperado), 2)


def _direccion(impacto: float) -> str:
    if impacto > 0:
        return "en_contra"   # la aerolínea cobró de MÁS
    if impacto < 0:
        return "a_favor"     # cobró de MENOS (también se reporta)
    return "neutro"


def _conciliar_contra(factura: dict, kg_base: float, tarifario: Tarifario) -> dict:
    """Concilia la factura contra el esperado propio calculado sobre `kg_base`.

    delta_total = factura.total − esperado, descompuesto EXACTO en tres componentes:
      peso   = imp_tarifa_kg × (kg_cobrados − kg_base)          (a tarifa pactada)
      tarifa = (tarifa_factura − imp_tarifa_kg) × kg_cobrados   (bidireccional)
      cargos = (awb_fee + pickup + otros) − cargos_fijos_tarifario
    """
    esperado = calculos.costo_importacion(kg_base, tarifario).valor
    kg_cob = factura["kg_cobrados"]

    comp_peso = round(tarifario.imp_tarifa_kg * (kg_cob - kg_base), 2)
    comp_tarifa = round((factura["tarifa_kg_usd"] - tarifario.imp_tarifa_kg) * kg_cob, 2)
    otros = sum(c.get("valor", 0) for c in (factura.get("otros_cargos") or []))
    factura_cargos = round(factura.get("awb_fee_usd", 0) + factura.get("pickup_entrega_usd", 0) + otros, 2)
    comp_cargos = round(factura_cargos - tarifario.imp_cargos_fijos, 2)

    delta_total = round(factura["total_usd"] - esperado, 2)
    tol = _tolerancia_importacion(esperado)
    estado = "conciliado" if abs(delta_total) <= tol else "discrepancia"

    return {
        "estado": estado,
        "esperado_usd": esperado,
        "factura_total_usd": factura["total_usd"],
        "delta_total": delta_total,
        "tolerancia": tol,
        "kg_base": round(kg_base, 2),
        "componentes": {
            "peso": {"impacto_usd": comp_peso, "kg_cobrados": kg_cob, "kg_base": round(kg_base, 2)},
            "tarifa": {"impacto_usd": comp_tarifa, "tarifa_factura": factura["tarifa_kg_usd"],
                       "tarifa_pactada": tarifario.imp_tarifa_kg, "direccion": _direccion(comp_tarifa)},
            "cargos_fijos": {"impacto_usd": comp_cargos, "factura_cargos": factura_cargos,
                             "tarifario_cargos": tarifario.imp_cargos_fijos},
        },
    }


def conciliar_importacion(manifiesto: dict, factura: Optional[dict],
                          tarifario: Optional[Tarifario] = None,
                          tulas_reportadas=None) -> dict:
    """Concilia un manifiesto contra su FacturaAerolinea.

    Estados: sin_factura | conciliado | discrepancia. La conciliación primaria usa
    kg_reportado (báscula) si existe — de tulas del datasource o de TULAS_REPORTADAS
    (pantallazo) — con nivel_confianza="reportado"; si no, kg_sistema
    (nivel_confianza="solo_sistema"). Expone `fuente_kg_sistema` y `fuente_kg_reportado`
    (trazables), `sobre_sistema`/`sobre_reportado`, y las advertencias del motor.
    """
    tarifario = tarifario or Tarifario()
    if factura is None:
        return {"estado": "sin_factura", "manifiesto_id": manifiesto.get("id"),
                "motivo": "no hay FacturaAerolinea para el manifiesto"}

    ks = calculos.kg_sistema_total(manifiesto, tarifario)
    kr = calculos.kg_reportado_total(manifiesto, tulas_reportadas, tarifario)

    concil_sistema = None
    if ks.ok:
        concil_sistema = _conciliar_contra(factura, ks.valor, tarifario)
        concil_sistema["fuente_kg"] = ks.detalle.get("fuente")
        concil_sistema["advertencias"] = list(ks.advertencias)

    if kr.ok:
        concil_reportado = _conciliar_contra(factura, kr.valor, tarifario)
        primaria, nivel = concil_reportado, "reportado"
    else:
        concil_reportado = {"estado": NO_DISPONIBLE, "motivo": kr.motivo}
        primaria, nivel = concil_sistema, "solo_sistema"

    advertencias = (list(ks.advertencias) if ks.ok else []) + (list(kr.advertencias) if kr.ok else [])
    resultado = {
        "manifiesto_id": manifiesto.get("id"),
        "nivel_confianza": nivel,
        "fuente_kg_sistema": ks.detalle.get("fuente") if ks.ok else None,
        "fuente_kg_reportado": kr.detalle.get("fuente") if kr.ok else None,
        "advertencias": advertencias,
        "kg_sistema": ks.valor if ks.ok else None,
        "kg_reportado": kr.valor if kr.ok else None,
        "sobre_sistema": concil_sistema,
        "sobre_reportado": concil_reportado,
    }

    if primaria is not None:
        # Enriquecer el componente de peso con ambas referencias (para el dash).
        peso = primaria["componentes"]["peso"]
        peso["kg_sistema"] = ks.valor if ks.ok else None
        peso["kg_reportado"] = kr.valor if kr.ok else None
        peso["dif_vs_sistema"] = round(factura["kg_cobrados"] - ks.valor, 2) if ks.ok else None
        peso["dif_vs_reportado"] = round(factura["kg_cobrados"] - kr.valor, 2) if kr.ok else None
        resultado.update({
            "estado": primaria["estado"],
            "esperado_usd": primaria["esperado_usd"],
            "factura_total_usd": primaria["factura_total_usd"],
            "delta_total": primaria["delta_total"],
            "tolerancia": primaria["tolerancia"],
            "componentes": primaria["componentes"],
        })
    else:
        resultado["estado"] = NO_DISPONIBLE
        resultado["motivo"] = "sin kg para conciliar"

    return resultado


# --------------------------------------------------------------------------- #
# Match de factura → manifiesto por AWB
# --------------------------------------------------------------------------- #

def match_manifiesto_por_awb(awb, manifiestos, tulas_reportadas=None) -> dict:
    """Busca el manifiesto de una factura por AWB.

    Primero en `awb_master` de los manifiestos del datasource; si no hay match, en el
    `awb_master` registrado en TULAS_REPORTADAS (el AWB se asigna al despachar y llega
    por pantallazo). Si el AWB matchea manifiestos DISTINTOS por ambos lados → conflicto
    (no se auto-matchea; el dash muestra los candidatos y pide selección manual).

    Devuelve {estado: "unico"|"conflicto"|"sin_match", manifiesto, candidatos, via}.
    """
    if not awb:
        return {"estado": "sin_match", "manifiesto": None, "candidatos": [], "via": None}

    por_ds = [m for m in manifiestos if m.get("awb_master") == awb]
    ids_tr = {t.get("manifiesto_id") for t in (tulas_reportadas or [])
              if t.get("awb_master") == awb}
    por_tr = [m for m in manifiestos if m.get("id") in ids_tr]

    candidatos = {}
    for m in por_ds + por_tr:
        candidatos.setdefault(m.get("id"), m)
    cand = list(candidatos.values())

    if len(cand) == 1:
        return {"estado": "unico", "manifiesto": cand[0], "candidatos": cand,
                "via": "datasource" if por_ds else "tulas_reportadas"}
    if len(cand) > 1:
        return {"estado": "conflicto", "manifiesto": None, "candidatos": cand, "via": None}
    return {"estado": "sin_match", "manifiesto": None, "candidatos": [], "via": None}


# --------------------------------------------------------------------------- #
# Conciliación distribución (por guía)
# --------------------------------------------------------------------------- #

def conciliar_distribucion(envio: dict, cobro: Optional[dict],
                           tarifario: Optional[Tarifario] = None) -> dict:
    """delta = valor_cobrado − esperado. Estados: sin_cobro | conciliado | discrepancia."""
    tarifario = tarifario or Tarifario()
    esp = calculos.costo_distribucion(envio.get("peso_lb"), tarifario)
    if not esp.ok:
        return {"estado": NO_DISPONIBLE, "guia": envio.get("guia"), "motivo": esp.motivo}

    esperado = esp.valor
    if cobro is None:
        return {"estado": "sin_cobro", "guia": envio.get("guia"), "esperado_usd": esperado}

    valor_cobrado = cobro.get("valor_usd")
    if valor_cobrado is None:
        return {"estado": NO_DISPONIBLE, "guia": envio.get("guia"), "motivo": "cobro sin valor_usd"}

    delta = round(valor_cobrado - esperado, 2)
    # La spec no fija tolerancia de distribución: se considera conciliado si el match
    # es prácticamente exacto (diferencia de centavos por redondeo).
    estado = "conciliado" if abs(delta) <= 0.01 else "discrepancia"
    return {
        "estado": estado,
        "guia": envio.get("guia"),
        "esperado_usd": esperado,
        "valor_cobrado_usd": valor_cobrado,
        "delta": delta,
        "lb_facturadas": cobro.get("lb_facturadas"),
        "lb_facturable_esperada": esp.detalle.get("lb_facturable"),
    }


# --------------------------------------------------------------------------- #
# P&L (por manifiesto y por período)
# --------------------------------------------------------------------------- #

def _gastos(gastos_reales, manifiesto_id, concepto):
    return [g for g in gastos_reales
            if g.get("manifiesto_id") == manifiesto_id and g.get("concepto") == concepto]


def pyl_manifiesto(manifiesto: dict, gastos_reales, tarifario: Optional[Tarifario] = None) -> dict:
    """P&L de un manifiesto: ingresos − gastos reales de importación y distribución.

    Sin valor_cobrado_cliente (caso excel) → ingresos no_disponible, modo "solo_costos".
    utilidad/kg sobre kg_reportado si existe, si no sobre kg_sistema (con nota).
    estado "parcial" si el manifiesto no tiene gasto de importación registrado.
    """
    tarifario = tarifario or Tarifario()
    mid = manifiesto.get("id")
    envios = manifiesto.get("envios") or []

    valores = [e.get("valor_cobrado_cliente_usd") for e in envios]
    hay_valor = any(v is not None for v in valores)
    if hay_valor:
        ingresos = round(sum(v for v in valores if v is not None), 2)
        modo = "completo"
    else:
        ingresos = None
        modo = "solo_costos"

    g_imp = _gastos(gastos_reales, mid, "importacion")
    g_dist = _gastos(gastos_reales, mid, "distribucion")
    gasto_imp = round(sum(g.get("total_usd", 0) for g in g_imp), 2)
    gasto_dist = round(sum(g.get("total_usd", 0) for g in g_dist), 2)
    tiene_gasto_imp = bool(g_imp)

    # Base de peso para utilidad/kg.
    kr = calculos.kg_reportado_total(manifiesto)
    if kr.ok:
        kg_base, nota_kg = kr.valor, "sobre kg_reportado"
    else:
        ks = calculos.kg_sistema_total(manifiesto, tarifario)
        kg_base = ks.valor if ks.ok else None
        fuente = ks.detalle.get("fuente") if ks.ok else "n/d"
        nota_kg = f"sobre kg_sistema (sin kg_reportado; fuente={fuente})"

    if ingresos is not None:
        utilidad = round(ingresos - gasto_imp - gasto_dist, 2)
        margen_pct = round(utilidad / ingresos * 100, 2) if ingresos else None
        utilidad_por_kg = round(utilidad / kg_base, 2) if kg_base else None
    else:
        utilidad = margen_pct = utilidad_por_kg = None

    return {
        "manifiesto_id": mid,
        "modo": modo,
        "estado": "completo" if tiene_gasto_imp else "parcial",
        "ingresos_usd": ingresos,
        "gasto_importacion_usd": gasto_imp,
        "gasto_distribucion_usd": gasto_dist,
        "tiene_gasto_importacion": tiene_gasto_imp,
        "utilidad_usd": utilidad,
        "margen_pct": margen_pct,
        "utilidad_por_kg_usd": utilidad_por_kg,
        "nota_utilidad_kg": nota_kg,
    }


def pyl_periodo(manifiestos, gastos_reales, tarifario: Optional[Tarifario] = None) -> dict:
    """P&L agregado del período. estado "parcial" si algún manifiesto no tiene gasto
    de importación registrado. modo "solo_costos"/"mixto"/"completo" según ingresos."""
    tarifario = tarifario or Tarifario()
    pyls = [pyl_manifiesto(m, gastos_reales, tarifario) for m in manifiestos]

    ingresos_vals = [p["ingresos_usd"] for p in pyls if p["ingresos_usd"] is not None]
    ingresos = round(sum(ingresos_vals), 2) if ingresos_vals else None
    gasto_imp = round(sum(p["gasto_importacion_usd"] for p in pyls), 2)
    gasto_dist = round(sum(p["gasto_distribucion_usd"] for p in pyls), 2)

    algun_sin_gasto_imp = any(not p["tiene_gasto_importacion"] for p in pyls)
    algun_sin_ingreso = any(p["ingresos_usd"] is None for p in pyls)

    if ingresos is not None:
        utilidad = round(ingresos - gasto_imp - gasto_dist, 2)
        margen_pct = round(utilidad / ingresos * 100, 2) if ingresos else None
    else:
        utilidad = margen_pct = None

    if ingresos is None:
        modo = "solo_costos"
    elif algun_sin_ingreso:
        modo = "mixto"
    else:
        modo = "completo"

    return {
        "n_manifiestos": len(pyls),
        "modo": modo,
        "estado": "parcial" if algun_sin_gasto_imp else "completo",
        "ingresos_usd": ingresos,
        "gasto_importacion_usd": gasto_imp,
        "gasto_distribucion_usd": gasto_dist,
        "utilidad_usd": utilidad,
        "margen_pct": margen_pct,
        "por_manifiesto": pyls,
    }
