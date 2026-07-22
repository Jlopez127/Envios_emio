"""Fixtures de la suite. Incluye un generador de directorios de manifiestos
SINTETICOS (en tmp_path) para los casos que el fixture real del 900007 no cubre:
archivo ignorado, sufijo Dropbox, dedupe por mtime y hoja CLIENTES ausente.
"""

import os
from pathlib import Path

import pandas as pd
import pytest

LB_A_KG = 0.45359237

# Columnas reales de la hoja "INFO MANIFIESTO" del export ASTRID.
COLUMNAS_INFO = [
    "MASTER", "FECHA GUIA", "GUIA / consignment", "NOMBRE DESTINO", "DESTINO CIUDAD",
    "DESTINO ESTADO", "CONTENIDO", "PESO LIBRAS", "PESO KILOS", "PIEZAS",
    "MANIFIESTO", "CASILLERO", "Tula",
]


def _fila_info(guia, casillero, manifiesto_id, peso_lb, *, master="999-99999999", tula=None):
    peso_kg = round(peso_lb * LB_A_KG, 2) if isinstance(peso_lb, (int, float)) else None
    return {
        "MASTER": master,
        "FECHA GUIA": "2026-07-15",
        "GUIA / consignment": guia,
        "NOMBRE DESTINO": "Destinatario Demo",
        "DESTINO CIUDAD": "Bogota",
        "DESTINO ESTADO": "Bogota D.C.",
        "CONTENIDO": "Ropa",
        "PESO LIBRAS": peso_lb,
        "PESO KILOS": peso_kg,
        "PIEZAS": 1,
        "MANIFIESTO": manifiesto_id,
        "CASILLERO": casillero,
        "Tula": tula,
    }


def _fila_total():
    """Fila de totales al final del export: GUIA nula, etiqueta 'W.Lb'. Debe descartarse."""
    fila = {c: None for c in COLUMNAS_INFO}
    fila["NOMBRE DESTINO"] = "W.Lb"
    fila["PESO LIBRAS"] = 123.4
    return fila


def _escribir_xlsx(path, filas_info, *, clientes=None, hojas_extra=None):
    df = pd.DataFrame(filas_info, columns=COLUMNAS_INFO)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="INFO MANIFIESTO", index=False)
        if clientes is not None:
            pd.DataFrame(clientes, columns=["CASILLERO", "CLIENTE"]).to_excel(
                writer, sheet_name="CLIENTES", index=False)
        for nombre, dframe in (hojas_extra or {}).items():
            dframe.to_excel(writer, sheet_name=nombre, index=False)


@pytest.fixture
def directorio_sintetico(tmp_path):
    """Directorio de exports sinteticos + metadatos para las aserciones."""
    d = tmp_path / "portal_envios"
    d.mkdir()

    # 900007: cobertura de tulas PARCIAL (4/20 < 80%) -> fuente envios, n_tulas None +
    # advertencia. Incluye la guia 990001 con error de digitacion (peso 500). Reproduce el
    # escenario del export real (parcial) con datos SINTETICOS (sin PII).
    tulas7 = ["260714-900007-1", "260714-900007-2", "260714-900007-3"]
    filas7 = [_fila_info(f"70{i:03d}", f"CAS{i}", "900007", 3.0 + (i % 5),
                         tula=(tulas7[i] if i < 3 else None)) for i in range(19)]
    filas7.append(_fila_info("990001", "CAS99", "900007", 500.0, tula=tulas7[0]))  # digitacion
    _escribir_xlsx(d / "2026-07-15-900007-ASTRID.xlsx", filas7, clientes=None)
    _parcial_kg = round(sum(f["PESO KILOS"] for f in filas7
                            if isinstance(f["PESO KILOS"], (int, float))), 2)

    # 900009: unico archivo, con sufijo Dropbox " (1)". 4 envios + fila de totales +
    # una hoja extra (DUPLICADOS) que el parser debe ignorar.
    filas9 = [_fila_info(f"7770{i}", "CAS0" if i == 0 else f"CAS{i}", "900009", 2.0 + i)
              for i in range(4)]
    filas9.append(_fila_total())
    _escribir_xlsx(
        d / "2026-07-17-900009-ASTRID (1).xlsx", filas9,
        clientes=[["CAS0", "Cliente Cero"]],
        hojas_extra={"DUPLICADOS": pd.DataFrame({"basura": [1, 2, 3]})},
    )

    # 900008: SIN hoja CLIENTES -> cliente None sin romper.
    filas8 = [_fila_info(f"8880{i}", f"CAS{i}", "900008", 3.0 + i) for i in range(3)]
    _escribir_xlsx(d / "2026-07-16-900008-ASTRID.xlsx", filas8, clientes=None)

    # 900006: guias como float (95001.0) y un peso no numerico (coerce -> None).
    filas6 = [
        _fila_info(95001.0, "CAS1", "900006", 5.0),
        _fila_info(95002.0, "CAS2", "900006", "N/A"),
        _fila_info("95003.0", "CAS3", "900006", 7.0),
    ]
    _escribir_xlsx(d / "2026-07-08-900006-ASTRID.xlsx", filas6, clientes=[["CAS1", "Uno"]])

    # 900010: dedupe. Base (3 envios, mtime viejo) + " (1)" (5 envios, mtime nuevo).
    base = d / "2026-07-20-900010-ASTRID.xlsx"
    nuevo = d / "2026-07-20-900010-ASTRID (1).xlsx"
    _escribir_xlsx(base, [_fila_info(f"1000{i}", "CASA", "900010", 4.0) for i in range(3)])
    _escribir_xlsx(nuevo, [_fila_info(f"2000{i}", "CASA", "900010", 4.0) for i in range(5)])
    os.utime(base, (1_700_000_000, 1_700_000_000))   # mas viejo
    os.utime(nuevo, (1_700_100_000, 1_700_100_000))  # mas reciente -> gana

    # Archivos que NO son manifiestos: deben ignorarse y registrarse en omitidos.
    for nombre in (
        "MANIFIESTO DUPLICADOS 900007.xlsx",
        "CAJAS-CEL julio.xlsx",
        "2026-07-10-900005-DEFINITIVO.xlsx",  # matchea fecha pero no '-ASTRID'
    ):
        _escribir_xlsx(d / nombre, [_fila_info("1", "X", "0000000", 1.0)])

    meta = {"dedupe_envios_base": 3, "dedupe_envios_nuevo": 5,
            "parcial_n_envios": len(filas7), "parcial_kg_sistema": _parcial_kg}
    return d, meta


# --------------------------------------------------------------------------- #
# SDK de Dropbox FALSO (para tests de dropbox_api y del ProveedorDropbox)
# --------------------------------------------------------------------------- #

class _Resp:
    def __init__(self, content):
        self.content = content


class _FileEntry:
    def __init__(self, name, server_modified):
        self.name = name
        self.server_modified = server_modified


class _FolderEntry:            # las carpetas NO tienen server_modified (se ignoran)
    def __init__(self, name):
        self.name = name


class _ListResult:
    def __init__(self, entries):
        self.entries = entries
        self.has_more = False
        self.cursor = ""


class _FakeDropbox:
    """Cuenta Dropbox en memoria: store {path: bytes} + listado por carpeta."""

    def __init__(self):
        self.store = {}
        self.folders = set()
        self.uploads = 0
        self._entries_por_carpeta = {}

    def files_download(self, path):
        if path not in self.store:
            from dropbox.exceptions import ApiError
            from dropbox.files import DownloadError, LookupError as DbxLookupError
            raise ApiError("req", DownloadError.path(DbxLookupError.not_found), "", "")
        return (None, _Resp(self.store[path]))

    def files_upload(self, data, path, mode=None):
        self.store[path] = data
        self.uploads += 1
        return None

    def files_create_folder_v2(self, path):
        self.folders.add(path)
        return None

    def files_list_folder(self, path):
        return _ListResult(list(self._entries_por_carpeta.get(path.rstrip("/"), [])))

    def files_list_folder_continue(self, cursor):
        return _ListResult([])

    def poblar_carpeta(self, carpeta, archivos=(), subcarpetas=()):
        """archivos: [(nombre, bytes, mtime_datetime)]; subcarpetas: [nombre]."""
        carpeta = carpeta.rstrip("/")
        entries = self._entries_por_carpeta.setdefault(carpeta, [])
        for nombre, contenido, mtime in archivos:
            self.store[f"{carpeta}/{nombre}"] = contenido
            entries.append(_FileEntry(nombre, mtime))
        for sub in subcarpetas:
            entries.append(_FolderEntry(sub))


def _bytes_xlsx_manifiesto(filas, clientes=None):
    """Bytes de un .xlsx de manifiesto (hoja INFO MANIFIESTO [+ CLIENTES])."""
    import io
    buf = io.BytesIO()
    df = pd.DataFrame(filas, columns=COLUMNAS_INFO)
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="INFO MANIFIESTO", index=False)
        if clientes is not None:
            pd.DataFrame(clientes, columns=["CASILLERO", "CLIENTE"]).to_excel(
                writer, sheet_name="CLIENTES", index=False)
    return buf.getvalue()


@pytest.fixture
def FakeDropbox():
    return _FakeDropbox


@pytest.fixture
def construir_bytes_manifiesto():
    return _bytes_xlsx_manifiesto


@pytest.fixture
def fila_info():
    return _fila_info
