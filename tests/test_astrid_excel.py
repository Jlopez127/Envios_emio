"""Tests de Fase 1.5: FuenteASTRIDExcel.

Todos corren contra fixtures SINTETICOS en tmp_path (ver tests/conftest.py), sin datos
reales. El manifiesto 900007 reproduce el escenario del export real de cobertura PARCIAL
(fuente envios, n_tulas None, campos faltantes) con datos ficticios.
"""

from datetime import date
from pathlib import Path

import pytest

from datasources.astrid_excel import FuenteASTRIDExcel
from datasources.base import FuenteASTRID, ManifiestoResumen

DIR_FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# Manifiesto SINTETICO de cobertura PARCIAL (900007): reproduce el escenario del
# export real (fuente envios, n_tulas None, campos faltantes) sin datos reales.
# --------------------------------------------------------------------------- #

@pytest.fixture
def fuente_parcial(directorio_sintetico):
    directorio, _ = directorio_sintetico
    return FuenteASTRIDExcel(directorio)


def test_parcial_cumple_la_interfaz(fuente_parcial):
    assert isinstance(fuente_parcial, FuenteASTRID)


def test_parcial_900007_n_envios(fuente_parcial, directorio_sintetico):
    _, meta = directorio_sintetico
    m = fuente_parcial.get_manifiesto("900007")
    assert len(m["envios"]) == meta["parcial_n_envios"]


def test_parcial_900007_kg_sistema_total_por_envios(fuente_parcial, directorio_sintetico):
    _, meta = directorio_sintetico
    resumenes = {r.id: r for r in fuente_parcial.get_manifiestos()}
    assert resumenes["900007"].kg_sistema_total == pytest.approx(meta["parcial_kg_sistema"], abs=0.01)


def test_parcial_900007_guia_990001_con_500_lb(fuente_parcial):
    m = fuente_parcial.get_manifiesto("900007")
    envio = next(e for e in m["envios"] if e["guia"] == "990001")
    assert envio["peso_lb"] == pytest.approx(500, abs=0.01)   # error de digitacion (100x)
    assert "." not in envio["guia"]  # guia como string, sin ".0"


def test_parcial_900007_campos_faltantes_en_none(fuente_parcial):
    m = fuente_parcial.get_manifiesto("900007")
    # Campos que el export no trae (PENDIENTE_API): None sin romper.
    assert m["pallets"] is None
    for envio in m["envios"]:
        assert envio["tipo"] is None
        assert envio["valor_cobrado_cliente_usd"] is None
    for tula in m["tulas"]:
        assert tula["kg_reportado"] is None


def test_parcial_900007_n_tulas_none_por_asignacion_incompleta(fuente_parcial):
    # Solo 4/20 envios traen tula (<80%) -> n_tulas None honesto + advertencia.
    resumenes = {r.id: r for r in fuente_parcial.get_manifiestos()}
    assert resumenes["900007"].n_tulas is None
    assert any("asignacion de tulas incompleta" in a for a in fuente_parcial.advertencias)


# --------------------------------------------------------------------------- #
# Fixtures SINTETICOS
# --------------------------------------------------------------------------- #

def test_archivo_no_manifiesto_ignorado_y_logueado(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)

    nombres_omitidos = [o.nombre for o in fuente.archivos_omitidos]
    assert any("DUPLICADOS" in n for n in nombres_omitidos)
    assert any("CAJAS-CEL" in n for n in nombres_omitidos)
    assert any("DEFINITIVO" in n for n in nombres_omitidos)
    # Ninguno se indexo como manifiesto.
    assert "0000000" not in fuente.ids_disponibles()
    assert "900005" not in fuente.ids_disponibles()


def test_sufijo_dropbox_se_parsea(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    assert "900009" in fuente.ids_disponibles()  # viene de "...-ASTRID (1).xlsx"
    m = fuente.get_manifiesto("900009")
    assert len(m["envios"]) == 4  # 4 envios + 1 fila de totales descartada


def test_filas_de_totales_descartadas(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    m = fuente.get_manifiesto("900009")
    # La fila 'W.Lb' (GUIA nula) no debe aparecer como envio.
    assert all(e["destinatario"] != "W.Lb" for e in m["envios"])


def test_hojas_extra_ignoradas(directorio_sintetico):
    # El archivo 900009 trae una hoja 'DUPLICADOS' ademas de INFO MANIFIESTO/CLIENTES;
    # que exista y no rompa el parseo prueba que solo se leen las dos hojas esperadas.
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    m = fuente.get_manifiesto("900009")
    assert len(m["envios"]) == 4


def test_dedupe_usa_mtime_mas_reciente(directorio_sintetico):
    directorio, meta = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    m = fuente.get_manifiesto("900010")
    # Gana el archivo con mtime mas reciente (el " (1)", con 5 envios).
    assert len(m["envios"]) == meta["dedupe_envios_nuevo"]
    assert any(a.startswith("900010:") for a in fuente.advertencias)


def test_sin_hoja_clientes_cliente_none(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    m = fuente.get_manifiesto("900008")  # archivo sin hoja CLIENTES
    assert m["envios"]  # hay envios
    assert all(e["cliente"] is None for e in m["envios"])


def test_guia_sin_punto_cero_y_pesos_coerce(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    m = fuente.get_manifiesto("900006")
    guias = [e["guia"] for e in m["envios"]]
    assert set(guias) == {"95001", "95002", "95003"}  # sin ".0"
    # El peso no numerico ("N/A") se coacciona a None sin romper.
    assert any(e["peso_lb"] is None for e in m["envios"])


def test_faltantes_none_en_sinteticos(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    m = fuente.get_manifiesto("900006")
    for e in m["envios"]:
        assert e["tipo"] is None
        assert e["valor_cobrado_cliente_usd"] is None
        assert e["tula_codigo"] is None  # los sinteticos no traen tula


def test_get_manifiestos_filtra_por_fechas(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    resumenes = fuente.get_manifiestos(date(2026, 7, 16), date(2026, 7, 18))
    ids = {r.id for r in resumenes}
    assert ids == {"900008", "900009"}  # 07-16 y 07-17; fuera: 900006, 900010
    assert all(isinstance(r, ManifiestoResumen) for r in resumenes)


def test_get_manifiesto_desconocido_lanza_keyerror(directorio_sintetico):
    directorio, _ = directorio_sintetico
    fuente = FuenteASTRIDExcel(directorio)
    with pytest.raises(KeyError):
        fuente.get_manifiesto("9999999")


# --------------------------------------------------------------------------- #
# ProveedorDropbox (Fase 5): listado ignora /portal/ y no-manifiestos
# --------------------------------------------------------------------------- #

def test_proveedor_dropbox_lista_e_ignora(FakeDropbox, construir_bytes_manifiesto, fila_info):
    from datetime import datetime
    from datasources.astrid_excel import ProveedorDropbox

    carpeta = "/portal_envios"
    manifiesto = construir_bytes_manifiesto(
        [fila_info(f"770{i}", f"CAS{i}", "900009", 2.0 + i) for i in range(3)])

    dbx = FakeDropbox()
    dbx.poblar_carpeta(
        carpeta,
        archivos=[
            ("2026-07-17-900009-ASTRID.xlsx", manifiesto, datetime(2026, 7, 17, 8, 0)),
            # no-manifiesto: mismo nivel, debe omitirse (no /portal/, no recursivo)
            ("MANIFIESTO DUPLICADOS 900007.xlsx", manifiesto, datetime(2026, 7, 10, 8, 0)),
        ],
        subcarpetas=["portal"],   # subcarpeta -> ignorada (no tiene server_modified)
    )

    fuente = FuenteASTRIDExcel(proveedor=ProveedorDropbox(dbx, carpeta))

    assert fuente.ids_disponibles() == ["900009"]
    nombres_omitidos = [o.nombre for o in fuente.archivos_omitidos]
    assert any("DUPLICADOS" in n for n in nombres_omitidos)
    assert "portal" not in nombres_omitidos            # la subcarpeta ni se considera

    m = fuente.get_manifiesto("900009")               # descarga + parsea por Dropbox
    assert len(m["envios"]) == 3


# --------------------------------------------------------------------------- #
# Excepciones legacy (cerradas) + regla dura DIAN
# --------------------------------------------------------------------------- #

def test_legacy_incluye_con_id_fecha_y_dian_omite(tmp_path, construir_bytes_manifiesto, fila_info):
    from datetime import date

    contenido = construir_bytes_manifiesto(
        [fila_info(f"L{i}", f"CAS{i}", "900001", 2.0 + i) for i in range(4)])
    d = tmp_path / "carpeta"
    d.mkdir()
    (d / "2026-07-02-900001-CAJAS-CEL.xlsx").write_bytes(contenido)          # legacy
    (d / "2026-07-06-900002-DIAN-CAJAS-CEL.xlsx").write_bytes(contenido)     # DIAN -> omitir
    (d / "2026-07-15-900007-ASTRID.xlsx").write_bytes(contenido)             # patrón normal

    legacy = {"2026-07-02-900001-CAJAS-CEL.xlsx": ("900001", "2026-07-02")}
    fuente = FuenteASTRIDExcel(d, legacy=legacy)

    # Legacy incluido, normal incluido, DIAN excluido.
    assert set(fuente.ids_disponibles()) == {"900001", "900007"}

    # El legacy toma el id y la fecha de la lista (no del patrón).
    resumenes = {r.id: r for r in fuente.get_manifiestos()}
    assert resumenes["900001"].fecha == date(2026, 7, 2)
    assert len(fuente.get_manifiesto("900001")["envios"]) == 4

    # DIAN omitido con motivo explícito.
    omitidos = {o.nombre: o.motivo for o in fuente.archivos_omitidos}
    assert "2026-07-06-900002-DIAN-CAJAS-CEL.xlsx" in omitidos
    assert "DIAN" in omitidos["2026-07-06-900002-DIAN-CAJAS-CEL.xlsx"].upper()


def test_sin_legacy_los_no_patron_se_omiten(tmp_path, construir_bytes_manifiesto, fila_info):
    """Sin lista legacy, un nombre no-patrón NO se incluye (comportamiento por defecto)."""
    contenido = construir_bytes_manifiesto([fila_info("X1", "C1", "900001", 3.0)])
    d = tmp_path / "c"
    d.mkdir()
    (d / "2026-07-02-900001-CAJAS-CEL.xlsx").write_bytes(contenido)
    fuente = FuenteASTRIDExcel(d)                       # sin legacy
    assert fuente.ids_disponibles() == []
    assert any("900001-CAJAS-CEL" in o.nombre for o in fuente.archivos_omitidos)
