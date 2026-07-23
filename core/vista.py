"""Agregados de PRESENTACIÓN para el dashboard (KPIs, gráficos, drill-down, sin-cobro).

Funciones PURAS y testeables. NO es el motor de conciliación (core/calculos.py,
core/conciliacion.py); son agregaciones sobre manifiestos/gastos/cobros para la UI.
Respetan el modo parcial: lo que falta → None (nunca inventar).
"""

from __future__ import annotations

from core import calculos
from core.calculos import PAGO_PAGADO, PAGO_VENCIDO, Tarifario


def _envios(manifiestos):
    for m in manifiestos:
        for e in (m.get("envios") or []):
            yield m, e


# --------------------------------------------------------------------------- #
# KPIs de la Vista general
# --------------------------------------------------------------------------- #

def kpis_periodo(manifiestos, gastos, tarifario=None, tulas_reportadas=None) -> dict:
    """KPIs del subconjunto de manifiestos dado (los filtros de la tab lo achican)."""
    tarifario = tarifario or Tarifario()
    ids = {m.get("id") for m in manifiestos}
    envios = [e for _, e in _envios(manifiestos)]
    n_envios = len(envios)
    n_manifiestos = len(manifiestos)

    kg_sistema = 0.0
    kg_bascula = 0.0
    hay_bascula = False
    for m in manifiestos:
        ks = calculos.kg_sistema_total(m, tarifario)
        if ks.ok:
            kg_sistema += ks.valor
        kr = calculos.kg_reportado_total(m, tulas_reportadas, tarifario)
        if kr.ok:
            kg_bascula += kr.valor
            hay_bascula = True

    pesos_lb = [e["peso_lb"] for e in envios if e.get("peso_lb") is not None]
    peso_prom_lb = round(sum(pesos_lb) / len(pesos_lb), 2) if pesos_lb else None

    valores = [e.get("valor_cobrado_cliente_usd") for e in envios]
    hay_ingresos = any(v is not None for v in valores)
    ingresos = round(sum(v for v in valores if v is not None), 2) if hay_ingresos else None

    g_imp = [g for g in gastos if g.get("concepto") == "importacion" and g.get("manifiesto_id") in ids]
    g_dist = [g for g in gastos if g.get("concepto") == "distribucion" and g.get("manifiesto_id") in ids]
    pagado_aerolineas = round(sum(g.get("total_usd") or 0 for g in g_imp), 2)
    pagado_astrid = round(sum(g.get("total_usd") or 0 for g in g_dist), 2)

    if hay_ingresos:
        utilidad = round(ingresos - pagado_aerolineas - pagado_astrid, 2)
        modo_ingresos = "completo"
    else:
        # Honesto: sin ingresos, la "utilidad" es el resultado provisional de solo costos.
        utilidad = round(-(pagado_aerolineas + pagado_astrid), 2)
        modo_ingresos = "solo_costos"

    ids_con_factura = {g["manifiesto_id"] for g in g_imp}
    pct_con_factura = (round(100 * len(ids_con_factura & ids) / n_manifiestos, 1)
                       if n_manifiestos else None)

    return {
        "n_manifiestos": n_manifiestos,
        "n_envios": n_envios,
        "kg_sistema": round(kg_sistema, 2),
        "kg_bascula": round(kg_bascula, 2) if hay_bascula else None,
        "peso_prom_lb": peso_prom_lb,
        "ingresos": ingresos,               # None -> pendiente API ASTRID
        "modo_ingresos": modo_ingresos,
        "pagado_aerolineas": pagado_aerolineas,
        "pagado_astrid": pagado_astrid,
        "utilidad": utilidad,
        "pct_con_factura": pct_con_factura,
    }


# --------------------------------------------------------------------------- #
# Participaciones y rankings (para gráficos)
# --------------------------------------------------------------------------- #

def participacion_por_departamento(manifiestos, top=None) -> dict:
    """{'por_envios': [(depto, n, pct)], 'por_kg': [(depto, kg, pct)]} desc por valor."""
    por_env, por_kg, total_env, total_kg = {}, {}, 0, 0.0
    for _, e in _envios(manifiestos):
        depto = e.get("departamento") or "—"
        por_env[depto] = por_env.get(depto, 0) + 1
        total_env += 1
        kg = e.get("peso_kg") or 0
        por_kg[depto] = por_kg.get(depto, 0.0) + kg
        total_kg += kg

    def rank(d, total):
        filas = sorted(d.items(), key=lambda kv: kv[1], reverse=True)
        out = [(k, round(v, 2), round(100 * v / total, 1) if total else 0.0) for k, v in filas]
        return out[:top] if top else out

    return {"por_envios": rank(por_env, total_env), "por_kg": rank(por_kg, total_kg)}


def top_clientes(manifiestos, n=10) -> dict:
    """Top-n por # envíos + % de concentración. Usa `cliente` si hay, si no `casillero`.
    Devuelve {'items': [(clave, n, pct)], 'campo': 'cliente'|'casillero', 'total': N}."""
    hay_cliente = any(e.get("cliente") for _, e in _envios(manifiestos))
    campo = "cliente" if hay_cliente else "casillero"
    conteo, total = {}, 0
    for _, e in _envios(manifiestos):
        clave = e.get(campo) or "—"
        conteo[clave] = conteo.get(clave, 0) + 1
        total += 1
    filas = sorted(conteo.items(), key=lambda kv: kv[1], reverse=True)[:n]
    items = [(k, v, round(100 * v / total, 1) if total else 0.0) for k, v in filas]
    return {"items": items, "campo": campo, "total": total}


def series_por_manifiesto(manifiestos, tarifario=None) -> list:
    """Por manifiesto (orden por fecha): id, fecha, n_envios, kg_sistema."""
    tarifario = tarifario or Tarifario()
    filas = []
    for m in sorted(manifiestos, key=lambda x: str(x.get("fecha"))):
        ks = calculos.kg_sistema_total(m, tarifario)
        filas.append({
            "id": m.get("id"), "fecha": str(m.get("fecha")),
            "n_envios": len(m.get("envios") or []),
            "kg_sistema": ks.valor if ks.ok else None,
        })
    return filas


# --------------------------------------------------------------------------- #
# Drill-down de tula alertada (con honestidad del dato)
# --------------------------------------------------------------------------- #

def envios_de_tula(manifiesto, tula_codigo, top_n=10) -> dict:
    """Envíos de una tula alertada.

    - Si hay envíos asignados a `tula_codigo` → {confirmado: True, envios: [...] desc}.
    - Si NO (export sin asignación, caso excel) → {confirmado: False, envios: top_n más
      pesados del MANIFIESTO} como HEURÍSTICA de sospecha (NO es el contenido de la tula).
    En ambos casos ordena por peso_lb descendente.
    """
    envios = manifiesto.get("envios") or []
    propios = [e for e in envios if e.get("tula_codigo") == tula_codigo]
    if propios:
        propios.sort(key=lambda e: (e.get("peso_lb") or 0), reverse=True)
        return {"confirmado": True, "envios": propios}
    pesados = sorted(envios, key=lambda e: (e.get("peso_lb") or 0), reverse=True)[:top_n]
    return {"confirmado": False, "envios": pesados}


# --------------------------------------------------------------------------- #
# Manifiestos sin cobro (pendiente de seguimiento, no error)
# --------------------------------------------------------------------------- #

def manifiestos_sin_cobro(manifiestos, gastos, cobros, consolidados=None) -> list:
    """Manifiestos sin factura de aerolínea y/o sin cobro ASTRID registrado.

    Devuelve [{id, fecha, sin_factura_aerolinea, sin_cobro_astrid}] para los que les
    falta alguno — es "no me han cobrado → no he pagado", pendiente de seguimiento.
    Un cobro ASTRID cuenta también si el manifiesto tiene un despacho consolidado.
    """
    ids_factura = {g["manifiesto_id"] for g in gastos if g.get("concepto") == "importacion"}
    ids_cobro_astrid = ({g["manifiesto_id"] for g in gastos if g.get("concepto") == "distribucion"}
                        | {c.get("manifiesto_id") for c in (cobros or [])}
                        | {c.get("manifiesto_id") for c in (consolidados or [])})
    filas = []
    for m in manifiestos:
        sin_fact = m.get("id") not in ids_factura
        sin_astrid = m.get("id") not in ids_cobro_astrid
        if sin_fact or sin_astrid:
            filas.append({"id": m.get("id"), "fecha": str(m.get("fecha")),
                          "sin_factura_aerolinea": sin_fact, "sin_cobro_astrid": sin_astrid})
    return filas


# --------------------------------------------------------------------------- #
# Consolidaciones: guías cubiertas (para NO doble-contar) y ahorro agregado
# --------------------------------------------------------------------------- #

def guias_consolidadas(consolidados) -> set:
    """Set de todas las guías incluidas en algún despacho consolidado. Se usa para
    excluirlas del conteo/conciliación individual (evitar doble conteo)."""
    guias = set()
    for c in consolidados or []:
        for g in c.get("guias") or []:
            guias.add(g)
    return guias


def ahorro_consolidados(consolidados, manifiestos, tarifario=None) -> dict:
    """Ahorro agregado de los despachos consolidados del período: suma de costos
    individuales vs. suma de costos consolidados. {ahorro_usd, individual, consolidado,
    n_consolidados, por_consolidado:[detalle]}."""
    tarifario = tarifario or Tarifario()
    por_id = {m.get("id"): m for m in manifiestos}
    individual = consolidado = 0.0
    por_consolidado = []
    for c in consolidados or []:
        res = calculos.ahorro_consolidado(c, por_id.get(c.get("manifiesto_id")), tarifario)
        if not res.ok:
            continue
        individual += res.detalle["costo_individual_usd"]
        consolidado += res.detalle["costo_consolidado_usd"]
        por_consolidado.append(res.detalle)
    return {
        "n_consolidados": len(por_consolidado),
        "individual_usd": round(individual, 2),
        "consolidado_usd": round(consolidado, 2),
        "ahorro_usd": round(individual - consolidado, 2),
        "por_consolidado": por_consolidado,
    }


# --------------------------------------------------------------------------- #
# Cuentas por pagar (estado de pago de los GastoReal ya consolidados)
# --------------------------------------------------------------------------- #

def cuentas_por_pagar(gastos, hoy=None) -> dict:
    """Cuentas por pagar sobre GastoReal ya consolidados (con estado_pago).

    Devuelve totales facturado/pagado/pendiente (aerolíneas y ASTRID) y vencido. El
    estado efectivo (incluye "vencido") se deriva con calculos.estado_pago_efectivo.
    """
    facturado = pagado = pend_aero = pend_astrid = vencido = 0.0
    n_vencidas = 0
    for g in gastos or []:
        total = g.get("total_usd") or 0
        facturado += total
        efectivo = calculos.estado_pago_efectivo(g, hoy)
        if efectivo == PAGO_PAGADO:
            pagado += total
            continue
        # pendiente o vencido
        if g.get("concepto") == "importacion":
            pend_aero += total
        elif g.get("concepto") == "distribucion":
            pend_astrid += total
        if efectivo == PAGO_VENCIDO:
            vencido += total
            n_vencidas += 1
    return {
        "facturado_usd": round(facturado, 2),
        "pagado_usd": round(pagado, 2),
        "pendiente_aerolineas_usd": round(pend_aero, 2),
        "pendiente_astrid_usd": round(pend_astrid, 2),
        "pendiente_total_usd": round(pend_aero + pend_astrid, 2),
        "vencido_usd": round(vencido, 2),
        "n_vencidas": n_vencidas,
    }
