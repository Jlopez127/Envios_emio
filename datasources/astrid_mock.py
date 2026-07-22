"""Implementacion mock de la fuente ASTRID, con datos generados EN MEMORIA.

La API real de ASTRID no existe todavia: el desarrollo se hace contra este mock.
Los datos son deterministicos (seed fija por manifiesto), sin numpy ni archivos
externos; todo vive embebido en codigo (ver docs/CLAUDE.md).

Contenido: 8 manifiestos DEMO de julio 2026 (ids 900005..900012), datos SINTETICOS.
Dos manifiestos reproducen escenarios de prueba especificos:
  - 900007: 316 envios, 27 tulas, kg_sistema total = 1000.00, kg_reportado total = 774.00.
    Reproduce: tula 3 con discrepancia enorme por error de digitacion (sistema inflado,
    250 vs bascula 20), tula 15 con alerta media (+4 kg), y la guia 990001 con error de
    digitacion (peso_lb=500 en vez de ~5 lb) en la tula 3.
  - 900009: 31 envios, 11 tulas, kg reportados totales = 300.0, sin alertas de peso
    (manifiesto "limpio").

NOTA para fases posteriores: el manifiesto 900012 debe quedar SIN factura de
aerolinea (caso de gasto de importacion faltante).

Asunciones de modelado:
  - Codigo de tula = "<(fecha-1dia) %y%m%d>-<id>-<numero>" -> ej "260714-900007-3".
  - `tula.kg_sistema` es la autoridad del total del manifiesto; los envios son
    realistas pero NO se fuerzan a sumar exactamente el peso de su tula.
"""

from __future__ import annotations

import copy
import random
from datetime import date, timedelta
from typing import Optional

import config
from datasources.base import FuenteASTRID, Manifiesto, ManifiestoResumen

# --------------------------------------------------------------------------- #
# Constantes de dominio
# --------------------------------------------------------------------------- #

LB_A_KG = 0.45359237
_SEED_BASE = 20260721

# Coeficientes de cobro al cliente (USD/lb) usados por la GENERACION del mock. Se toman
# del Tarifario (precedencia hoja TARIFARIO > env/secret > default DEMO, via
# config.tarifario_base); en datos reales el valor_cobrado viene del datasource, no de
# esta formula. Se refrescan al construir la fuente (FuenteASTRIDMock.__init__).
_COEFS_COBRO = {"comercial": 5.0, "estandar": 4.0}  # DEMO; sobreescrito en __init__

# (ciudad, departamento). Los 4 primeros concentran la mayoria de los destinos.
DEPARTAMENTOS = [
    ("Bogota D.C.", "Bogota D.C."),
    ("Medellin", "Antioquia"),
    ("Bucaramanga", "Santander"),
    ("Cali", "Valle del Cauca"),
    ("Barranquilla", "Atlantico"),
    ("Cartagena", "Bolivar"),
    ("Pereira", "Risaralda"),
    ("Manizales", "Caldas"),
    ("Cucuta", "Norte de Santander"),
    ("Ibague", "Tolima"),
    ("Villavicencio", "Meta"),
    ("Pasto", "Narino"),
    ("Neiva", "Huila"),
    ("Monteria", "Cordoba"),
    ("Santa Marta", "Magdalena"),
    ("Armenia", "Quindio"),
    ("Popayan", "Cauca"),
    ("Sincelejo", "Sucre"),
    ("Valledupar", "Cesar"),
    ("Tunja", "Boyaca"),
    ("Riohacha", "La Guajira"),
    ("Florencia", "Caqueta"),
    ("Quibdo", "Choco"),
]

CONTENIDOS = [
    "Ropa y calzado", "Suplementos vitaminicos", "Repuestos electronicos",
    "Accesorios de celular", "Perfumeria", "Articulos de belleza", "Juguetes",
    "Herramientas manuales", "Libros", "Articulos para el hogar",
    "Zapatos deportivos", "Audifonos", "Relojes", "Utiles escolares",
]

NOMBRES = [
    "Maria", "Juan", "Andres", "Camila", "Diego", "Laura", "Carlos", "Valentina",
    "Mateo", "Daniela", "Felipe", "Paula", "Sergio", "Natalia", "Ricardo",
]
APELLIDOS = [
    "Gomez", "Rodriguez", "Martinez", "Lopez", "Garcia", "Hernandez", "Ramirez",
    "Torres", "Vargas", "Castro", "Rojas", "Moreno", "Jimenez", "Ospina", "Restrepo",
]

# --------------------------------------------------------------------------- #
# Especificacion de los 8 manifiestos (id, fecha, pallets). 900007 y 900009 son
# especiales (valores calcados de casos reales); el resto se generan genericos.
# --------------------------------------------------------------------------- #

_ESPECIFICACIONES = [
    ("900005", date(2026, 7, 3), 1),
    ("900006", date(2026, 7, 8), 3),
    ("900007", date(2026, 7, 15), 2),   # especial
    ("900008", date(2026, 7, 16), 2),
    ("900009", date(2026, 7, 17), 2),   # especial
    ("900010", date(2026, 7, 20), 2),
    ("900011", date(2026, 7, 24), 1),
    ("900012", date(2026, 7, 29), 3),   # SIN factura de aerolinea en fases posteriores
]

# 900007 (DEMO): 27 tulas, kg_sistema total EXACTO 1000.00, kg_reportado total 774.00.
#  - tula 3 : error de digitacion (sistema inflado) -> ks 250 / kr 20 (dif -230, alerta enorme)
#  - tula 15: alerta media                          -> ks  30 / kr 34 (dif  +4)
#  - resto (25 tulas)                               -> ks reparte 720.00 exacto; kr = ks (sin alerta)
_M7_TULA3_KS, _M7_TULA3_KR = 250.00, 20.00
_M7_TULA15_KS, _M7_TULA15_KR = 30.00, 34.00
_M7_KS_TOTAL_CENTS = 100000                       # 1000.00
_M7_KS_RESTO_CENTS = _M7_KS_TOTAL_CENTS - round(_M7_TULA3_KS * 100) - round(_M7_TULA15_KS * 100)  # 72000

# 900009 (DEMO): kg_reportado exactos por tula (suman 300.0), manifiesto limpio.
_M9_KG_REPORTADO = [28.0, 27.0, 29.0, 26.0, 25.0, 30.0, 24.0, 28.0, 31.0, 22.0, 30.0]


# --------------------------------------------------------------------------- #
# Helpers de generacion (deterministicos: reciben siempre el rng del manifiesto)
# --------------------------------------------------------------------------- #

def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _codigo_tula(fecha: date, manifiesto_id: str, numero: int) -> str:
    """Codigo de tula. Prefijo = (fecha - 1 dia) en formato %y%m%d.

    Para 900007 (fecha 2026-07-15) da "260714-900007-<numero>".
    """
    prefijo = (fecha - timedelta(days=1)).strftime("%y%m%d")
    return f"{prefijo}-{manifiesto_id}-{numero}"


def _repartir_cents(raws: list[float], total_cents: int) -> list[int]:
    """Reparte `total_cents` proporcionalmente a `raws`, garantizando suma exacta."""
    s = sum(raws)
    cents = [int(round(r / s * total_cents)) for r in raws]
    cents[-1] += total_cents - sum(cents)  # el residuo de redondeo va a la ultima
    return cents


def _pesos_destino(pool: list) -> list[float]:
    pesos = []
    for i in range(len(pool)):
        pesos.append([9, 7, 6, 5][i] if i < 4 else 1.5)
    return pesos


def _asignar_destinos(rng: random.Random, n: int, cobertura: int) -> list:
    """Lista de `n` destinos (ciudad, depto) garantizando `cobertura` distintos."""
    cobertura = min(cobertura, len(DEPARTAMENTOS), n)
    pool = DEPARTAMENTOS[:cobertura]
    destinos = list(pool)  # cada uno al menos una vez
    faltan = n - cobertura
    if faltan > 0:
        destinos += rng.choices(pool, weights=_pesos_destino(pool), k=faltan)
    rng.shuffle(destinos)
    return destinos


def _nombre(rng: random.Random) -> str:
    return f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"


def _valor_cobrado(rng: random.Random, tipo: str, peso_lb_cobro: float) -> float:
    """Valor cobrado al cliente en USD, con ruido +/-3%. Coeficientes desde el Tarifario."""
    if tipo == "comercial":
        base = max(22.0, _COEFS_COBRO["comercial"] * peso_lb_cobro)
    else:
        base = max(14.0, _COEFS_COBRO["estandar"] * peso_lb_cobro)
    return round(base * (1 + rng.uniform(-0.03, 0.03)), 2)


def _peso_lb_realista(rng: random.Random) -> float:
    """Mayoria entre 0.3 y 10 lb; una cola hasta 50 lb."""
    if rng.random() < 0.85:
        return round(rng.uniform(0.3, 10.0), 2)
    return round(rng.uniform(10.0, 50.0), 2)


def _crear_envio(
    rng: random.Random,
    guia: str,
    casillero: str,
    tula_codigo: str,
    tipo: str,
    destino: tuple,
    *,
    contenido: Optional[str] = None,
    peso_lb: Optional[float] = None,
    peso_lb_cobro: Optional[float] = None,
) -> dict:
    """Construye un Envio segun docs/CONTRATO_DATOS.md.

    `peso_lb_cobro` permite facturar con un peso distinto al registrado (caso 990001:
    peso_lb=500 por error de digitacion, pero se cobra con 5.00 lb).
    """
    if peso_lb is None:
        peso_lb = _peso_lb_realista(rng)
    if peso_lb_cobro is None:
        peso_lb_cobro = peso_lb
    if contenido is None:
        contenido = rng.choice(CONTENIDOS)
    ciudad, departamento = destino
    return {
        "guia": guia,
        "casillero": casillero,
        "cliente": _nombre(rng),
        "destinatario": _nombre(rng),
        "ciudad": ciudad,
        "departamento": departamento,
        "contenido": contenido,
        "peso_lb": peso_lb,
        "peso_kg": round(peso_lb * LB_A_KG, 2),
        "tula_codigo": tula_codigo,
        "tipo": tipo,
        "valor_cobrado_cliente_usd": _valor_cobrado(rng, tipo, peso_lb_cobro),
    }


# --------------------------------------------------------------------------- #
# Construccion de manifiestos
# --------------------------------------------------------------------------- #

def _construir_900007(manifiesto_id: str, fecha: date, pallets: int, rng: random.Random) -> Manifiesto:
    tulas: list = [None] * 27

    # Tula 3: error de digitacion (sistema inflado). Tula 15: alerta media.
    tulas[2] = {"codigo": _codigo_tula(fecha, manifiesto_id, 3), "numero": 3,
                "kg_sistema": _M7_TULA3_KS, "kg_reportado": _M7_TULA3_KR}
    tulas[14] = {"codigo": _codigo_tula(fecha, manifiesto_id, 15), "numero": 15,
                 "kg_sistema": _M7_TULA15_KS, "kg_reportado": _M7_TULA15_KR}

    # Resto (25 tulas): kg_sistema reparte 720.00 exacto; kr = ks (sin alerta).
    indices_resto = [i for i in range(27) if i not in (2, 14)]
    raws = [_clip(rng.gauss(28.8, 6.0), 8.0, 45.0) for _ in indices_resto]
    cents = _repartir_cents(raws, _M7_KS_RESTO_CENTS)
    for i, c in zip(indices_resto, cents):
        numero = i + 1
        ks = round(c / 100, 2)
        tulas[i] = {
            "codigo": _codigo_tula(fecha, manifiesto_id, numero),
            "numero": numero,
            "kg_sistema": ks,
            "kg_reportado": ks,
        }

    envios = _envios_900007(rng, tulas)
    return {
        "id": manifiesto_id,
        "fecha": fecha,
        "awb_master": "999-12345678",
        "pallets": pallets,
        "tulas": tulas,
        "envios": envios,
    }


def _envios_900007(rng: random.Random, tulas: list) -> list:
    """316 envios. ~45% comercial concentrado (casilleros 60/21/19 + medianos)."""
    tula_codigos = [t["codigo"] for t in tulas]
    pesos_tula = [max(0.1, t["kg_reportado"]) for t in tulas]  # peso "real", no el inflado
    tula3_codigo = tulas[2]["codigo"]

    destinos = _asignar_destinos(rng, 316, cobertura=21)
    idx_destino = 0

    def prox_destino():
        nonlocal idx_destino
        d = destinos[idx_destino]
        idx_destino += 1
        return d

    def tula_al_azar():
        return rng.choices(tula_codigos, weights=pesos_tula, k=1)[0]

    envios = []
    guia = 100000  # guias corrientes; la 990001 es un caso aparte

    # Comercial concentrado: 60 + 21 + 19 + (6 x 7) = 142 (~45% de 316)
    plan_comercial = [("MIA-0060", 60), ("MIA-0021", 21), ("MIA-0019", 19)]
    plan_comercial += [(f"MIA-M{i:02d}", 7) for i in range(6)]
    for casillero, cnt in plan_comercial:
        for _ in range(cnt):
            envios.append(_crear_envio(rng, str(guia), casillero, tula_al_azar(),
                                       "comercial", prox_destino()))
            guia += 1

    # Estandar: 173 envios en casilleros pequenos (1-3 c/u).
    restantes = 173
    cas = 0
    while restantes > 0:
        size = min(restantes, rng.choice([1, 1, 2, 2, 3]))
        casillero = f"EST-{cas:04d}"
        cas += 1
        for _ in range(size):
            envios.append(_crear_envio(rng, str(guia), casillero, tula_al_azar(),
                                       "estandar", prox_destino()))
            guia += 1
        restantes -= size

    # Escenario: guia 990001, error de digitacion (peso_lb=500, real ~5.00 lb, 100x), tula 3.
    envios.append(_crear_envio(
        rng, "990001", "MIA-0095", tula3_codigo, "estandar", prox_destino(),
        contenido="Cargador portatil de alta capacidad",
        peso_lb=500.0, peso_lb_cobro=5.00,
    ))
    return envios


def _construir_900009(manifiesto_id: str, fecha: date, pallets: int, rng: random.Random) -> Manifiesto:
    tulas = []
    for i, kr in enumerate(_M9_KG_REPORTADO):
        numero = i + 1
        # kg_sistema cercano al reportado, ruido leve acotado -> nunca dispara alerta.
        ruido = _clip(rng.gauss(0, 0.35), -0.7, 0.7)
        tulas.append({
            "codigo": _codigo_tula(fecha, manifiesto_id, numero),
            "numero": numero,
            "kg_sistema": round(kr + ruido, 2),
            "kg_reportado": kr,
        })

    envios = _envios_genericos(rng, manifiesto_id, tulas, n_envios=31)
    return {
        "id": manifiesto_id,
        "fecha": fecha,
        "awb_master": _awb_generico(rng),
        "pallets": pallets,
        "tulas": tulas,
        "envios": envios,
    }


def _construir_generico(manifiesto_id: str, fecha: date, pallets: int, rng: random.Random) -> Manifiesto:
    """Manifiesto realista: 80-350 envios, 10-30 tulas, 1-3 discrepancias menores."""
    n_tulas = rng.randint(10, 30)
    n_envios = rng.randint(80, 350)

    tulas = []
    for numero in range(1, n_tulas + 1):
        ks = round(_clip(rng.gauss(24.0, 7.0), 8.0, 45.0), 2)
        kr = round(ks + _clip(rng.gauss(0, 0.35), -0.7, 0.7), 2)  # base: casi sin diferencia
        tulas.append({
            "codigo": _codigo_tula(fecha, manifiesto_id, numero),
            "numero": numero,
            "kg_sistema": ks,
            "kg_reportado": kr,
        })

    # 1-3 discrepancias menores (delta 1.0-1.9 kg, signo aleatorio).
    for numero in rng.sample(range(1, n_tulas + 1), rng.randint(1, 3)):
        t = tulas[numero - 1]
        t["kg_reportado"] = round(t["kg_sistema"] + rng.uniform(1.0, 1.9) * rng.choice([-1, 1]), 2)

    envios = _envios_genericos(rng, manifiesto_id, tulas, n_envios)
    return {
        "id": manifiesto_id,
        "fecha": fecha,
        "awb_master": _awb_generico(rng),
        "pallets": pallets,
        "tulas": tulas,
        "envios": envios,
    }


def _awb_generico(rng: random.Random) -> str:
    return f"999-{rng.randint(10_000_000, 99_999_999)}"


def _envios_genericos(rng: random.Random, manifiesto_id: str, tulas: list, n_envios: int) -> list:
    """Envios realistas con concentracion suave por casillero y ~42% comercial."""
    tula_codigos = [t["codigo"] for t in tulas]
    pesos_tula = [max(0.1, t["kg_reportado"]) for t in tulas]
    destinos = _asignar_destinos(rng, n_envios, cobertura=min(21, n_envios))
    n_casilleros = max(1, n_envios // 3)

    envios = []
    for i in range(n_envios):
        # Sesgo hacia casilleros de indice bajo -> unos pocos concentran mas envios.
        casillero = f"CAS-{int(rng.random() ** 2 * n_casilleros):04d}"
        tipo = "comercial" if rng.random() < 0.42 else "estandar"
        tula_codigo = rng.choices(tula_codigos, weights=pesos_tula, k=1)[0]
        guia = f"{manifiesto_id[-3:]}{i:04d}"
        envios.append(_crear_envio(rng, guia, casillero, tula_codigo, tipo, destinos[i]))
    return envios


_CONSTRUCTORES_ESPECIALES = {
    "900007": _construir_900007,
    "900009": _construir_900009,
}


# --------------------------------------------------------------------------- #
# Fuente
# --------------------------------------------------------------------------- #

class FuenteASTRIDMock(FuenteASTRID):
    """Fuente ASTRID en memoria y deterministica (ver docstring del modulo)."""

    def __init__(self) -> None:
        # Coeficientes de cobro desde el Tarifario (env/secret > DEMO).
        _tarifario = config.tarifario_base()
        _COEFS_COBRO["comercial"] = _tarifario.cobro_comercial_usd_lb
        _COEFS_COBRO["estandar"] = _tarifario.cobro_estandar_usd_lb

        self._manifiestos: dict[str, Manifiesto] = {}
        for manifiesto_id, fecha, pallets in _ESPECIFICACIONES:
            rng = random.Random(_SEED_BASE + int(manifiesto_id))
            constructor = _CONSTRUCTORES_ESPECIALES.get(manifiesto_id, _construir_generico)
            self._manifiestos[manifiesto_id] = constructor(manifiesto_id, fecha, pallets, rng)

    def get_manifiestos(
        self,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
    ) -> list[ManifiestoResumen]:
        resumenes = []
        for m in self._manifiestos.values():
            f = m["fecha"]
            if fecha_desde is not None and f < fecha_desde:
                continue
            if fecha_hasta is not None and f > fecha_hasta:
                continue
            resumenes.append(self._resumen(m))
        resumenes.sort(key=lambda r: (r.fecha, r.id))
        return resumenes

    def get_manifiesto(self, manifiesto_id: str) -> Manifiesto:
        if manifiesto_id not in self._manifiestos:
            raise KeyError(f"Manifiesto desconocido: {manifiesto_id}")
        # Copia profunda: el consumidor no puede mutar el estado interno del mock.
        return copy.deepcopy(self._manifiestos[manifiesto_id])

    @staticmethod
    def _resumen(m: Manifiesto) -> ManifiestoResumen:
        return ManifiestoResumen(
            id=m["id"],
            fecha=m["fecha"],
            awb_master=m["awb_master"],
            n_envios=len(m["envios"]),
            n_tulas=len(m["tulas"]),
            kg_sistema_total=round(sum(t["kg_sistema"] for t in m["tulas"]), 2),
        )
