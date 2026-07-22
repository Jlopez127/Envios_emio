"""Cálculos financieros del portal: costos esperados de importación y distribución,
y novedades de peso por tula. En USD; kg para importación, lb para distribución.

REGLA TRANSVERSAL DEL MOTOR: funciona con datos completos (mock/API) Y parciales
(excel). Todo cálculo imposible por un campo faltante retorna un `Resultado` con
estado "no_disponible" y un `motivo` legible. Nunca se lanza excepción por un
faltante esperado; nunca se inventan valores.

Tarifas y reglas de derivación: ver docs/CONTRATO_DATOS.md. Faltantes del export
ASTRID: ver docs/PENDIENTES_API.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

OK = "ok"
NO_DISPONIBLE = "no_disponible"


# --------------------------------------------------------------------------- #
# Tarifario y Resultado
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Tarifario:
    """Parámetros de cálculo. Todos configurables.

    Los valores por defecto de acá son **DEMO genéricos** (no reales). La precedencia de
    carga (ver `config.tarifario_base` y `dropbox_api.leer_tarifario`) es:

        hoja TARIFARIO (Dropbox)  >  env/secret  >  estos defaults DEMO

    Los valores reales de negocio (tarifa pactada, cargos, umbrales) se cargan por
    variable de entorno / secret del host y/o en la hoja TARIFARIO del Excel de Dropbox;
    nunca viven en el código.
    """

    imp_awb_fee: float = 10.0            # DEMO
    imp_pickup: float = 50.0             # DEMO
    imp_tarifa_kg: float = 1.00          # DEMO (la real vía secret/env o hoja TARIFARIO)
    dist_base_usd: float = 5.0           # DEMO
    dist_base_lb: float = 5.0            # DEMO
    dist_usd_lb_extra: float = 1.0       # DEMO
    alerta_peso_kg: float = 2.0
    alerta_peso_pct: float = 10.0
    # Umbral de cobertura de tulas para elegir la fuente del kg_sistema total
    # (ver docs/CONTRATO_DATOS.md, "Reglas de derivación").
    cobertura_tulas_minima: float = 0.80
    # Cobro al cliente (USD/lb) por tipo de envío. Hoy solo lo usa la generación del mock;
    # cuando llegue la API sirven para conciliar lo cobrado vs. lo que debió cobrarse.
    cobro_comercial_usd_lb: float = 5.0  # DEMO
    cobro_estandar_usd_lb: float = 4.0   # DEMO

    @property
    def imp_cargos_fijos(self) -> float:
        return round(self.imp_awb_fee + self.imp_pickup, 2)


@dataclass
class Resultado:
    """Envoltura única de todo cálculo del motor.

    estado="ok" con `valor` (y `detalle`), o estado="no_disponible" con `motivo`.
    `advertencias` traza avisos no bloqueantes (ej. total calculado por envíos).
    """

    estado: str
    valor: Optional[Any] = None
    motivo: Optional[str] = None
    detalle: dict = field(default_factory=dict)
    advertencias: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.estado == OK

    @classmethod
    def disponible(cls, valor, detalle=None, advertencias=None) -> "Resultado":
        return cls(OK, valor=valor, detalle=dict(detalle or {}), advertencias=list(advertencias or []))

    @classmethod
    def no_disponible(cls, motivo, detalle=None) -> "Resultado":
        return cls(NO_DISPONIBLE, motivo=motivo, detalle=dict(detalle or {}))


# --------------------------------------------------------------------------- #
# Pesos totales del manifiesto (con fuente trazable)
# --------------------------------------------------------------------------- #

def kg_sistema_total(manifiesto: dict, tarifario: Optional[Tarifario] = None) -> Resultado:
    """kg de sistema del manifiesto, con la fuente explícita en `detalle["fuente"]`.

    - "tulas": suma de `tula.kg_sistema`, si las tulas cubren el manifiesto
      (cobertura de envíos con tula >= tarifario.cobertura_tulas_minima) — mock/API.
    - "envios": suma de `envio.peso_kg`, cuando la asignación de tulas está incompleta
      (ej. export excel, ~9%). En ese caso se registra una advertencia.

    Ver docs/CONTRATO_DATOS.md, "Reglas de derivación".
    """
    tarifario = tarifario or Tarifario()
    envios = manifiesto.get("envios") or []
    tulas = manifiesto.get("tulas") or []
    tulas_con_peso = [t for t in tulas if t.get("kg_sistema") is not None]

    n_env = len(envios)
    con_tula = sum(1 for e in envios if e.get("tula_codigo"))
    cobertura = (con_tula / n_env) if n_env else 0.0

    if tulas_con_peso and cobertura >= tarifario.cobertura_tulas_minima:
        total = round(sum(t["kg_sistema"] for t in tulas_con_peso), 2)
        return Resultado.disponible(total, detalle={
            "fuente": "tulas",
            "cobertura_tulas": round(cobertura, 4),
            "n_tulas": len(tulas_con_peso),
        })

    pesos = [e["peso_kg"] for e in envios if e.get("peso_kg") is not None]
    if not pesos:
        return Resultado.no_disponible("sin pesos para calcular kg_sistema (ni tulas ni envíos)")

    total = round(sum(pesos), 2)
    advertencias = []
    if tulas_con_peso:  # había asignación de tulas, pero incompleta
        advertencias.append(
            f"asignación de tulas incompleta ({round(cobertura * 100, 1)}%) — "
            "total calculado por envíos"
        )
    return Resultado.disponible(total, detalle={
        "fuente": "envios",
        "cobertura_tulas": round(cobertura, 4),
        "n_envios_con_peso": len(pesos),
    }, advertencias=advertencias)


def kg_reportado_total(manifiesto: dict, tulas_reportadas=None,
                       tarifario: Optional[Tarifario] = None) -> Resultado:
    """kg reportado (báscula) del manifiesto, con fuente trazable en `detalle["fuente"]`:

    - "tulas": `tula.kg_reportado` del datasource (mock/API).
    - "tulas_reportadas": suma de TULAS_REPORTADAS del manifiesto (cargadas por
      pantallazo), cuando el datasource no trae pesos por tula (caso excel).

    Prioridad: datasource sobre pantallazo. Si existen AMBAS y difieren más que el
    umbral de alerta de peso, se registra una advertencia visible (posible repesaje
    legítimo, pero debe verse). Sin ninguna fuente → no_disponible.
    """
    tarifario = tarifario or Tarifario()
    mid = manifiesto.get("id")
    tulas = manifiesto.get("tulas") or []
    con_rep = [t for t in tulas if t.get("kg_reportado") is not None]

    reportadas = [t for t in (tulas_reportadas or [])
                  if t.get("manifiesto_id") == mid and t.get("kg_reportado") is not None]
    total_reportadas = round(sum(t["kg_reportado"] for t in reportadas), 2) if reportadas else None

    if con_rep:
        total = round(sum(t["kg_reportado"] for t in con_rep), 2)
        advertencias = []
        if total_reportadas is not None:
            dif = abs(total - total_reportadas)
            dif_pct = (dif / total * 100) if total else 0.0
            if dif > tarifario.alerta_peso_kg or dif_pct > tarifario.alerta_peso_pct:
                advertencias.append(
                    "pesos de báscula del datasource difieren de los registrados por "
                    f"pantallazo ({total} vs {total_reportadas} kg)")
        return Resultado.disponible(total, detalle={"fuente": "tulas", "n_tulas": len(con_rep)},
                                    advertencias=advertencias)

    if total_reportadas is not None:
        return Resultado.disponible(total_reportadas,
                                    detalle={"fuente": "tulas_reportadas", "n_tulas": len(reportadas)})

    return Resultado.no_disponible(
        "sin pesos reportados de tula (ni datasource ni pantallazo) — PENDIENTE_API")


# --------------------------------------------------------------------------- #
# Importación USA -> CO
# --------------------------------------------------------------------------- #

def costo_importacion(kg: Optional[float], tarifario: Optional[Tarifario] = None) -> Resultado:
    """Costo esperado de importación = awb_fee + pickup + tarifa_kg × kg."""
    tarifario = tarifario or Tarifario()
    if kg is None:
        return Resultado.no_disponible("sin kg para calcular importación")
    tarifa_total = round(tarifario.imp_tarifa_kg * kg, 2)
    total = round(tarifario.imp_cargos_fijos + tarifa_total, 2)
    return Resultado.disponible(total, detalle={
        "awb_fee": tarifario.imp_awb_fee,
        "pickup": tarifario.imp_pickup,
        "cargos_fijos": tarifario.imp_cargos_fijos,
        "tarifa_kg": tarifario.imp_tarifa_kg,
        "tarifa_total": tarifa_total,
        "kg": round(kg, 2),
    })


def importacion_manifiesto(manifiesto: dict, tarifario: Optional[Tarifario] = None) -> dict:
    """Importación del manifiesto en DOS versiones: sobre kg_sistema (siempre) y sobre
    kg_reportado (si hay tulas con peso reportado; si no → no_disponible)."""
    tarifario = tarifario or Tarifario()
    ks = kg_sistema_total(manifiesto, tarifario)
    if ks.ok:
        sobre_sistema = costo_importacion(ks.valor, tarifario)
        sobre_sistema.detalle["fuente_kg"] = ks.detalle.get("fuente")
        sobre_sistema.advertencias = list(ks.advertencias)
    else:
        sobre_sistema = ks

    kr = kg_reportado_total(manifiesto)
    sobre_reportado = costo_importacion(kr.valor, tarifario) if kr.ok else Resultado.no_disponible(kr.motivo)

    return {"sobre_sistema": sobre_sistema, "sobre_reportado": sobre_reportado,
            "kg_sistema": ks, "kg_reportado": kr}


# --------------------------------------------------------------------------- #
# Distribución CO (por envío)
# --------------------------------------------------------------------------- #

def costo_distribucion(peso_lb: Optional[float], tarifario: Optional[Tarifario] = None) -> Resultado:
    """Distribución = dist_base_usd hasta dist_base_lb lb; desde ahí dist_usd_lb_extra
    por lb, con la lb redondeada hacia ARRIBA (ceil)."""
    tarifario = tarifario or Tarifario()
    if peso_lb is None:
        return Resultado.no_disponible("envío sin peso_lb")
    lb = math.ceil(peso_lb)
    if lb <= tarifario.dist_base_lb:
        total = tarifario.dist_base_usd
    else:
        total = tarifario.dist_base_usd + (lb - tarifario.dist_base_lb) * tarifario.dist_usd_lb_extra
    return Resultado.disponible(round(float(total), 2),
                                detalle={"lb_facturable": lb, "peso_lb": peso_lb})


# --------------------------------------------------------------------------- #
# Novedades de peso por tula
# --------------------------------------------------------------------------- #

def novedad_peso_tula(tula: dict, tarifario: Optional[Tarifario] = None) -> Resultado:
    """Alerta si |kg_reportado − kg_sistema| > alerta_peso_kg O |dif%| > alerta_peso_pct.
    Impacto USD = dif_kg × imp_tarifa_kg. Sin peso reportado → no_disponible."""
    tarifario = tarifario or Tarifario()
    ks = tula.get("kg_sistema")
    kr = tula.get("kg_reportado")
    if ks is None or kr is None:
        return Resultado.no_disponible("sin peso reportado de tula — PENDIENTE_API")

    dif_kg = round(kr - ks, 3)
    dif_pct = round(dif_kg / ks * 100, 2) if ks else None
    es_alerta = abs(dif_kg) > tarifario.alerta_peso_kg or (
        dif_pct is not None and abs(dif_pct) > tarifario.alerta_peso_pct)
    impacto = round(dif_kg * tarifario.imp_tarifa_kg, 2)

    return Resultado.disponible(impacto, detalle={
        "codigo": tula.get("codigo"),
        "numero": tula.get("numero"),
        "kg_sistema": ks,
        "kg_reportado": kr,
        "dif_kg": dif_kg,
        "dif_pct": dif_pct,
        "es_alerta": es_alerta,
        "impacto_usd": impacto,
        "estado": "alerta" if es_alerta else "ok",
    })


def novedades_peso_manifiesto(manifiesto: dict, tarifario: Optional[Tarifario] = None) -> Resultado:
    """Todas las novedades de peso del manifiesto. Sin tulas con peso reportado
    (excel) → no_disponible."""
    tarifario = tarifario or Tarifario()
    tulas = manifiesto.get("tulas") or []
    con_rep = [t for t in tulas if t.get("kg_reportado") is not None]
    if not con_rep:
        return Resultado.no_disponible("sin pesos de tula en el export — PENDIENTE_API")

    novedades = [novedad_peso_tula(t, tarifario).detalle for t in con_rep]
    alertas = [n for n in novedades if n["es_alerta"]]
    impacto_total = round(sum(n["impacto_usd"] for n in alertas), 2)

    return Resultado.disponible(impacto_total, detalle={
        "novedades": novedades,
        "alertas": alertas,
        "n_alertas": len(alertas),
        "impacto_total_usd": impacto_total,
    })
