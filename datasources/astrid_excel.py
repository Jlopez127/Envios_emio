"""Fuente ASTRID provisional (Fase 1.5): lee manifiestos desde los Excel que ASTRID
exporta a la carpeta de Dropbox de exports (ruta configurable, ver config.py).

Etapa puente mientras la API de ASTRID no esta disponible. Implementa la MISMA
interfaz que datasources.base.FuenteASTRID, asi que es intercambiable con el mock y
(en el futuro) con la API real.

ORIGEN DE ARCHIVOS (Fase 5):
    El origen se abstrae en un proveedor con `listar()` + `descargar()`:
      - `ProveedorLocal(directorio)`  -> archivos .xlsx de un directorio (tests/dev).
      - `ProveedorDropbox(dbx, carpeta)` -> lista la carpeta de Dropbox (no recursivo,
        ignora subcarpetas como /portal/) y descarga bajo demanda.
    `FuenteASTRIDExcel(directorio=...)` sigue funcionando (crea ProveedorLocal); en
    Dropbox se pasa `proveedor=ProveedorDropbox(...)`. Ver config.get_fuente_astrid.

REGLAS DE ARCHIVOS (la carpeta real es heterogenea):
    - Solo son manifiestos los que matchean  YYYY-MM-DD-<id>-ASTRID*.xlsx
      (se toleran sufijos de Dropbox como " (1)" antes de la extension).
    - Cualquier otro .xlsx (DEFINITIVO, DUPLICADOS, CAJAS-CEL, etc.) se IGNORA y queda
      registrado en `archivos_omitidos` (diagnostico).
    - Si hay varios archivos del mismo id, se usa el de fecha de modificacion mas
      reciente y se registra una advertencia en `advertencias`.
    - fecha e id se indexan desde el NOMBRE, sin abrir el archivo.

CAMPOS QUE EL EXPORT NO TRAE (ver docs/PENDIENTES_API.md; se marcan PENDIENTE_API):
    - tula_codigo por envio: mayormente vacio -> None.
    - kg_reportado por tula: no existe en el export.
    - valor_cobrado_cliente_usd y tipo (estandar/comercial): no existen -> None.
    - pallets por manifiesto: no existe -> None.
"""

from __future__ import annotations

import copy
import io
import logging
import math
import re
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union

from datasources.base import FuenteASTRID, Manifiesto, ManifiestoResumen

_log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Nombres de hojas y columnas reales del export ASTRID
# --------------------------------------------------------------------------- #

HOJA_INFO = "INFO MANIFIESTO"
HOJA_CLIENTES = "CLIENTES"

COL_MASTER = "MASTER"
COL_FECHA_GUIA = "FECHA GUIA"
COL_GUIA = "GUIA / consignment"
COL_NOMBRE_DESTINO = "NOMBRE DESTINO"
COL_CIUDAD = "DESTINO CIUDAD"
COL_ESTADO = "DESTINO ESTADO"
COL_CONTENIDO = "CONTENIDO"
COL_PESO_LB = "PESO LIBRAS"
COL_PESO_KG = "PESO KILOS"
COL_PIEZAS = "PIEZAS"
COL_MANIFIESTO = "MANIFIESTO"
COL_CASILLERO = "CASILLERO"
COL_TULA = "Tula"

# Umbral de cobertura de tulas por debajo del cual n_tulas se reporta como None.
UMBRAL_COBERTURA_TULAS = 0.80

# Nombre de manifiesto:  YYYY-MM-DD-<id>-ASTRID[ (n)].xlsx   (case-insensitive)
_PATRON = re.compile(
    r"^(?P<fecha>\d{4}-\d{2}-\d{2})-(?P<id>.+?)-ASTRID(?:\s*\(\d+\))*\.xlsx$",
    re.IGNORECASE,
)

ArchivoOmitido = namedtuple("ArchivoOmitido", ["nombre", "motivo"])


# --------------------------------------------------------------------------- #
# Helpers de limpieza de celdas
# --------------------------------------------------------------------------- #

def _es_nan(v) -> bool:
    return isinstance(v, float) and math.isnan(v)


def _num(v) -> Optional[float]:
    """Peso a float redondeado (2 dec) o None. Complementa pd.to_numeric(coerce)."""
    if v is None or _es_nan(v):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 2)


def _guia_a_str(v) -> Optional[str]:
    """Guia como string, sin el ".0" que introduce la lectura numerica de Excel."""
    if v is None or _es_nan(v):
        return None
    try:
        f = float(v)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    if not s:
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _str_limpio(v) -> Optional[str]:
    """Texto limpio o None (vacio, NaN o 'nan' -> None)."""
    if v is None or _es_nan(v):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _primer_no_nulo(serie) -> Optional[object]:
    if serie is None:
        return None
    for v in serie:
        if v is not None and not _es_nan(v):
            return v
    return None


# --------------------------------------------------------------------------- #
# Proveedores de archivos: abstraen el ORIGEN de los .xlsx (local o Dropbox).
# Solo exponen listar() -> [(nombre, mtime)] y descargar(nombre) -> bytes.
# --------------------------------------------------------------------------- #

class ProveedorLocal:
    """Archivos .xlsx desde un directorio local (usado en tests/dev)."""

    def __init__(self, directorio: Union[str, Path]) -> None:
        self._directorio = Path(directorio)

    def etiqueta(self) -> str:
        return str(self._directorio)

    def listar(self) -> list:
        if not self._directorio.exists():
            return []
        return [(p.name, p.stat().st_mtime)
                for p in sorted(self._directorio.iterdir())
                if p.is_file() and p.suffix.lower() == ".xlsx"]

    def descargar(self, nombre: str) -> bytes:
        return (self._directorio / nombre).read_bytes()


class ProveedorDropbox:
    """Archivos .xlsx desde una carpeta de Dropbox (Fase 5).

    Lista SOLO el nivel de la carpeta (no recursivo): las subcarpetas como /portal/
    (que no tienen `server_modified`) se ignoran, igual que los archivos que no
    matchean el patron de manifiesto (esos quedan en `archivos_omitidos`).
    """

    def __init__(self, dbx, carpeta: str) -> None:
        self._dbx = dbx
        self._carpeta = carpeta.rstrip("/")

    def etiqueta(self) -> str:
        return f"dropbox:{self._carpeta}"

    def _entries(self) -> list:
        resultado = self._dbx.files_list_folder(self._carpeta)
        entries = list(resultado.entries)
        while getattr(resultado, "has_more", False):
            resultado = self._dbx.files_list_folder_continue(resultado.cursor)
            entries.extend(resultado.entries)
        return entries

    def listar(self) -> list:
        salida = []
        for e in self._entries():
            # Solo archivos: las carpetas (FolderMetadata) no tienen server_modified.
            if not hasattr(e, "server_modified"):
                continue
            if not e.name.lower().endswith(".xlsx"):
                continue
            salida.append((e.name, e.server_modified.timestamp()))
        return salida

    def descargar(self, nombre: str) -> bytes:
        _, respuesta = self._dbx.files_download(f"{self._carpeta}/{nombre}")
        return respuesta.content


# --------------------------------------------------------------------------- #
# Fuente
# --------------------------------------------------------------------------- #

class FuenteASTRIDExcel(FuenteASTRID):
    """Lee manifiestos ASTRID desde un proveedor de archivos (local o Dropbox)."""

    def __init__(self, directorio: Union[str, Path, None] = None, *,
                 proveedor=None, legacy=None, logger: Optional[logging.Logger] = None) -> None:
        if proveedor is None:
            if directorio is None:
                raise ValueError("FuenteASTRIDExcel requiere `directorio` o `proveedor`.")
            proveedor = ProveedorLocal(directorio)
        self._proveedor = proveedor
        # Excepciones legacy CERRADAS: nombre exacto -> (id, fecha). Ver config.MANIFIESTOS_LEGACY.
        self._legacy: dict = dict(legacy or {})
        self._log = logger or _log

        self.archivos_omitidos: list[ArchivoOmitido] = []
        self.advertencias: list[str] = []

        self._indice: dict[str, str] = {}            # id -> nombre de archivo elegido
        self._fecha_por_id: dict[str, date] = {}     # id -> fecha (desde el nombre)
        self._cache: dict[str, Manifiesto] = {}
        self._resumenes: dict[str, ManifiestoResumen] = {}

        self._indexar()

    # -- indexado por nombre (sin descargar archivos) ----------------------- #

    def _indexar(self) -> None:
        try:
            archivos = self._proveedor.listar()  # [(nombre, mtime)]
        except Exception as exc:
            self._advertir(f"no se pudo listar el origen ({self._proveedor.etiqueta()}): {exc}")
            return

        candidatos: dict[str, list[tuple[str, float, date]]] = {}
        for nombre, mtime in sorted(archivos):
            # Regla dura: NUNCA ingerir archivos "DIAN" (defensa, aunque estuvieran en legacy).
            if "DIAN" in nombre.upper():
                self._omitir(nombre, "contiene 'DIAN' (excluido por regla)")
                continue
            m = _PATRON.match(nombre)
            if m:
                try:
                    fecha = datetime.strptime(m.group("fecha"), "%Y-%m-%d").date()
                except ValueError:
                    self._omitir(nombre, "fecha invalida en el nombre")
                    continue
                mid = m.group("id")
            elif nombre in self._legacy:                     # excepción legacy cerrada
                mid, fecha_str = self._legacy[nombre]
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            else:
                self._omitir(nombre, "no coincide con el patron de manifiesto ASTRID")
                continue
            candidatos.setdefault(mid, []).append((nombre, mtime, fecha))

        for mid, lista in candidatos.items():
            lista.sort(key=lambda t: t[1], reverse=True)  # mtime descendente
            elegido, _, fecha = lista[0]
            self._indice[mid] = elegido
            self._fecha_por_id[mid] = fecha
            if len(lista) > 1:
                descartados = ", ".join(n for n, _, _ in lista[1:])
                adv = (f"{mid}: {len(lista)} archivos para el mismo manifiesto; se usa "
                       f"el mas reciente '{elegido}' y se descartan: {descartados}")
                self._advertir(adv)

    def _omitir(self, nombre: str, motivo: str) -> None:
        self.archivos_omitidos.append(ArchivoOmitido(nombre, motivo))
        self._log.info("Archivo omitido (%s): %s", motivo, nombre)

    def _advertir(self, mensaje: str) -> None:
        if mensaje not in self.advertencias:
            self.advertencias.append(mensaje)
            self._log.warning(mensaje)

    # -- diagnostico -------------------------------------------------------- #

    def ids_disponibles(self) -> list[str]:
        return sorted(self._indice)

    def diagnostico(self) -> dict:
        """Estado del indexado para inspeccion en la UI (archivos omitidos/advertencias)."""
        return {
            "archivos_omitidos": list(self.archivos_omitidos),
            "advertencias": list(self.advertencias),
        }

    # -- interfaz FuenteASTRID --------------------------------------------- #

    def get_manifiestos(
        self,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
    ) -> list[ManifiestoResumen]:
        resumenes = []
        for mid, fecha in self._fecha_por_id.items():
            if fecha_desde is not None and fecha < fecha_desde:
                continue
            if fecha_hasta is not None and fecha > fecha_hasta:
                continue
            try:
                _, resumen = self._asegurar_parseado(mid)
            except Exception as exc:  # carpeta heterogenea: un archivo roto no tumba el listado
                self._advertir(f"{mid}: no se pudo parsear '{self._indice[mid]}': {exc}")
                continue
            resumenes.append(resumen)
        resumenes.sort(key=lambda r: (r.fecha, r.id))
        return resumenes

    def get_manifiesto(self, manifiesto_id: str) -> Manifiesto:
        if manifiesto_id not in self._indice:
            raise KeyError(f"Manifiesto desconocido: {manifiesto_id}")
        manifiesto, _ = self._asegurar_parseado(manifiesto_id)
        return copy.deepcopy(manifiesto)

    # -- parseo ------------------------------------------------------------- #

    def _asegurar_parseado(self, manifiesto_id: str) -> tuple[Manifiesto, ManifiestoResumen]:
        if manifiesto_id not in self._cache:
            manifiesto, resumen = self._parsear(manifiesto_id)
            self._cache[manifiesto_id] = manifiesto
            self._resumenes[manifiesto_id] = resumen
        return self._cache[manifiesto_id], self._resumenes[manifiesto_id]

    def _parsear(self, manifiesto_id: str) -> tuple[Manifiesto, ManifiestoResumen]:
        import pandas as pd  # import perezoso: el mock no necesita pandas

        nombre = self._indice[manifiesto_id]
        fecha = self._fecha_por_id[manifiesto_id]
        datos = self._proveedor.descargar(nombre)  # bytes (local o Dropbox)

        # Leer SOLO "INFO MANIFIESTO" y "CLIENTES"; ignorar cualquier hoja extra.
        with pd.ExcelFile(io.BytesIO(datos), engine="openpyxl") as xls:
            hojas = set(xls.sheet_names)
            if HOJA_INFO not in hojas:
                raise ValueError(f"{nombre}: falta la hoja '{HOJA_INFO}'")
            df = xls.parse(HOJA_INFO)
            clientes = _mapa_clientes(xls.parse(HOJA_CLIENTES)) if HOJA_CLIENTES in hojas else {}

        df.columns = [str(c).strip() for c in df.columns]

        # Limpieza obligatoria: descartar filas con GUIA nula (totales/"W.Lb" al final).
        if COL_GUIA not in df.columns:
            raise ValueError(f"{nombre}: falta la columna '{COL_GUIA}'")
        df = df[df[COL_GUIA].notna()].copy()

        for col in (COL_PESO_LB, COL_PESO_KG):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        envios = [_fila_a_envio(row, clientes) for _, row in df.iterrows()]
        envios = [e for e in envios if e["guia"]]  # por si alguna guia quedo vacia tras limpiar

        awb = _str_limpio(_primer_no_nulo(df[COL_MASTER] if COL_MASTER in df.columns else None))
        tulas, n_tulas = self._derivar_tulas(manifiesto_id, envios)

        manifiesto: Manifiesto = {
            "id": manifiesto_id,
            "fecha": fecha,
            "awb_master": awb,
            "pallets": None,          # PENDIENTE_API: pallets — llega con la API de ASTRID (HU 21/07/2026)
            "tulas": tulas,
            "envios": envios,
        }
        resumen = ManifiestoResumen(
            id=manifiesto_id,
            fecha=fecha,
            awb_master=awb,
            n_envios=len(envios),
            n_tulas=n_tulas,
            kg_sistema_total=round(sum(e["peso_kg"] for e in envios if e["peso_kg"] is not None), 2),
        )
        return manifiesto, resumen

    def _derivar_tulas(self, manifiesto_id: str, envios: list) -> tuple[list, Optional[int]]:
        """Deriva tulas de los codigos presentes en los envios.

        El export trae la asignacion de tulas incompleta: si menos del 80% de los
        envios trae tula, n_tulas se reporta como None (mejor None honesto que un
        conteo falso) con una advertencia.
        """
        total = len(envios)
        con_tula = [e for e in envios if e["tula_codigo"]]

        grupos: dict[str, list] = {}
        for e in con_tula:
            grupos.setdefault(e["tula_codigo"], []).append(e)

        tulas = []
        for codigo, es in grupos.items():
            kg = round(sum(e["peso_kg"] for e in es if e["peso_kg"] is not None), 2)
            tulas.append({
                "codigo": codigo,
                "numero": None,          # el export no trae numero de tula fiable
                "kg_sistema": kg,        # suma de peso_kg de los envios de la tula
                "kg_reportado": None,    # PENDIENTE_API: kg_reportado — API de ASTRID (HU 21/07/2026)
            })

        if total > 0 and len(con_tula) / total >= UMBRAL_COBERTURA_TULAS:
            return tulas, len(grupos)

        self._advertir(f"{manifiesto_id}: asignacion de tulas incompleta en el export")
        return tulas, None


# --------------------------------------------------------------------------- #
# Mapeo de filas
# --------------------------------------------------------------------------- #

def _fila_a_envio(row, clientes: dict) -> dict:
    casillero = _str_limpio(row.get(COL_CASILLERO))
    return {
        "guia": _guia_a_str(row.get(COL_GUIA)),
        "casillero": casillero,
        # CLIENTES (CASILLERO -> CLIENTE); None si no hay hoja o no matchea.
        "cliente": clientes.get(casillero),
        "destinatario": _str_limpio(row.get(COL_NOMBRE_DESTINO)),
        "ciudad": _str_limpio(row.get(COL_CIUDAD)),
        "departamento": _str_limpio(row.get(COL_ESTADO)),
        "contenido": _str_limpio(row.get(COL_CONTENIDO)),
        "peso_lb": _num(row.get(COL_PESO_LB)),
        "peso_kg": _num(row.get(COL_PESO_KG)),
        # PENDIENTE_API: tula_codigo — mayormente vacio en el export (HU 21/07/2026)
        "tula_codigo": _str_limpio(row.get(COL_TULA)),
        # PENDIENTE_API: tipo — no existe en el export (HU 21/07/2026)
        "tipo": None,
        # PENDIENTE_API: valor_cobrado_cliente_usd — no existe en el export (HU 21/07/2026)
        "valor_cobrado_cliente_usd": None,
    }


def _mapa_clientes(df) -> dict:
    df.columns = [str(c).strip() for c in df.columns]
    if COL_CASILLERO not in df.columns or "CLIENTE" not in df.columns:
        return {}
    mapa = {}
    for _, row in df.iterrows():
        cas = _str_limpio(row.get(COL_CASILLERO))
        if cas:
            mapa[cas] = _str_limpio(row.get("CLIENTE"))
    return mapa
