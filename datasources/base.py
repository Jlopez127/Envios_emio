"""Interfaces (contratos abstractos) de las fuentes de datos operativos de ASTRID.

Toda la logica del portal se construye contra estas interfaces, nunca contra una
implementacion concreta. La API real de ASTRID aun no existe: el desarrollo se hace
contra `datasources.astrid_mock` (ver docs/CLAUDE.md).

El Manifiesto completo se representa como dicts anidados segun docs/CONTRATO_DATOS.md
(en esta fase no se usa `core/modelos.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

# Manifiesto completo: estructura anidada segun docs/CONTRATO_DATOS.md
#   {id, fecha, awb_master, pallets, tulas: [Tula], envios: [Envio]}
Manifiesto = dict[str, Any]


@dataclass(frozen=True)
class ManifiestoResumen:
    """Vista de listado de un manifiesto (para grillas/selectores del portal)."""

    id: str
    fecha: date
    awb_master: str
    n_envios: int
    # n_tulas es Optional: un datasource puede reportar None cuando no puede
    # determinar el conteo con confianza (ej. el export Excel trae la asignacion de
    # tulas incompleta). Ver datasources.astrid_excel.
    n_tulas: Optional[int]
    kg_sistema_total: float


class FuenteASTRID(ABC):
    """Contrato de la fuente de datos operativos (manifiestos, tulas, envios).

    Las implementaciones concretas (`astrid_mock`, `astrid_api`) son intercambiables:
    la logica del portal depende solo de esta interfaz.
    """

    @abstractmethod
    def get_manifiestos(
        self,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
    ) -> list[ManifiestoResumen]:
        """Lista los manifiestos cuya fecha cae en [fecha_desde, fecha_hasta] (inclusive).

        `None` en cualquiera de los limites significa "sin cota" por ese lado.
        """
        raise NotImplementedError

    @abstractmethod
    def get_manifiesto(self, manifiesto_id: str) -> Manifiesto:
        """Devuelve el Manifiesto completo (dict anidado) segun docs/CONTRATO_DATOS.md.

        Lanza `KeyError` si el id no existe.
        """
        raise NotImplementedError
