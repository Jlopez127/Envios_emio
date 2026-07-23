"""Reajustes (nuevo alcance, solo recepción/archivo): extracción genérica tolerante
(todo null si no reconoce), archivo en Dropbox, registro append-only y edición manual."""

import json

from core import modelos
from datasources.dropbox_mock import FuenteDropboxMock
from vision import extractor


def _invocar(payload):
    return lambda prompt, imagenes: json.dumps(payload)


# --- Extracción genérica: puede devolver todo null ------------------------- #

def test_extraer_reajuste_reconocido():
    payload = {"manifiesto_id": "900007", "guia": "100005", "valor_usd": 12.5,
               "motivo": "sobrepeso", "fecha": "2026-07-18", "texto_resumen": "Reajuste por peso"}
    datos = extractor.extraer([], "reajuste", invocar=_invocar(payload))
    assert datos["manifiesto_id"] == "900007" and datos["valor_usd"] == 12.5


def test_extraer_reajuste_todo_null_no_inventa():
    payload = {"manifiesto_id": None, "guia": None, "valor_usd": None, "motivo": None,
               "fecha": None, "texto_resumen": None}
    datos = extractor.extraer([], "reajuste", invocar=_invocar(payload))
    assert all(datos[k] is None for k in
               ("manifiesto_id", "guia", "valor_usd", "motivo", "texto_resumen"))


# --- Archivo + registro append-only ---------------------------------------- #

def test_archivar_reajuste_persiste_documento_y_fila():
    dbx = FuenteDropboxMock()
    ruta = dbx.guardar_archivo("reajustes", "reaj-01.pdf", b"pdf-bytes")
    assert dbx.leer_archivo(ruta) == b"pdf-bytes"

    reg = modelos.construir_reajuste(
        usuario="proveedor1", archivo_ref=ruta, manifiesto_id="900007",
        guia=None, valor_usd=None, motivo=None, texto_resumen="ilegible")
    assert dbx.agregar_reajuste(reg) is True
    assert dbx.agregar_reajuste(dict(reg)) is False       # idempotente por archivo_ref

    leidos = dbx.leer_reajustes()
    assert len(leidos) == 1
    assert leidos[0]["archivo_ref"] == ruta
    assert leidos[0]["usuario"] == "proveedor1"


def test_reajuste_edicion_manual_de_campos():
    # La extracción dejó valor_usd null; el admin lo corrige a mano antes de archivar.
    reg = modelos.construir_reajuste(usuario="admin1", archivo_ref="/x/r.pdf",
                                     manifiesto_id="900007", valor_usd=None)
    reg_corregido = modelos.construir_reajuste(
        usuario="admin1", archivo_ref="/x/r.pdf", manifiesto_id="900007",
        guia="100005", valor_usd=30.0, motivo="corregido a mano")
    assert reg["valor_usd"] is None
    assert reg_corregido["valor_usd"] == 30.0 and reg_corregido["guia"] == "100005"
