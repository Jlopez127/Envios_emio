"""Interfaz (contrato abstracto) de la persistencia en Dropbox.

Es la ÚNICA persistencia del sistema: novedades resueltas, gastos reales confirmados
y cobros de distribución por guía. Todo append-only (ver docs/CLAUDE.md y
docs/CONTRATO_DATOS.md). Las implementaciones (`dropbox_mock`, `dropbox_api`) son
intercambiables.

Los objetos (Novedad, GastoReal, CobroDistribucion) se representan como dicts según
docs/CONTRATO_DATOS.md. El Tarifario es `core.calculos.Tarifario`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.calculos import Tarifario

# Alias de tipos (dicts anidados según docs/CONTRATO_DATOS.md)
Novedad = dict
GastoReal = dict
CobroDistribucion = dict
TulaReportada = dict


class FuenteDropbox(ABC):
    """Contrato de la persistencia. Toda escritura es append-only e idempotente."""

    # -- Novedades (hoja NOVEDADES) --------------------------------------- #
    @abstractmethod
    def leer_novedades(self) -> list:
        raise NotImplementedError

    @abstractmethod
    def agregar_novedad(self, novedad: Novedad) -> bool:
        """Agrega una novedad. Idempotente por (manifiesto_id, tula_codigo|guia, tipo).
        Devuelve True si se agregó, False si ya existía (no se duplica)."""
        raise NotImplementedError

    # -- Gastos reales (hoja GASTOS_REALES) ------------------------------- #
    @abstractmethod
    def leer_gastos_reales(self) -> list:
        raise NotImplementedError

    @abstractmethod
    def agregar_gasto_real(self, gasto: GastoReal) -> bool:
        """Agrega un gasto real. Idempotente por (manifiesto_id, concepto, referencia)."""
        raise NotImplementedError

    # -- Cobros de distribución (hoja COBROS_DISTRIBUCION) ---------------- #
    @abstractmethod
    def leer_cobros_distribucion(self) -> list:
        raise NotImplementedError

    @abstractmethod
    def agregar_cobro_distribucion(self, cobro: CobroDistribucion) -> bool:
        """Agrega un cobro de distribución. Idempotente por (manifiesto_id, guia).

        En el futuro los cobros entrarán por visión o carga manual (ver Fase 5).
        """
        raise NotImplementedError

    # -- Tulas reportadas (hoja TULAS_REPORTADAS) ------------------------- #
    # Flujo PROVISIONAL por visión mientras la API de ASTRID no traiga kg_reportado
    # por tula (ver docs/PENDIENTES_API.md).
    @abstractmethod
    def leer_tulas_reportadas(self) -> list:
        raise NotImplementedError

    @abstractmethod
    def agregar_tulas_reportadas(self, registro: TulaReportada) -> bool:
        """Agrega un peso reportado de tula. Idempotente por (manifiesto_id, numero_tula)."""
        raise NotImplementedError

    # -- Tarifario -------------------------------------------------------- #
    @abstractmethod
    def leer_tarifario(self) -> Tarifario:
        raise NotImplementedError
