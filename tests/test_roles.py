"""Roles (base del nuevo alcance): parseo por-usuario, casing, y AISLAMIENTO del rol
proveedor en el RENDER (AppTest, mock y excel) — nunca ve P&L/aerolínea/clientes."""

import importlib
import os

import streamlit_authenticator as stauth
from streamlit.testing.v1 import AppTest

import auth

# --- Parseo de roles y helpers (unitario) --------------------------------- #


def test_parsear_roles_string_y_dict():
    assert auth._parsear_roles("prov1:proveedor, Admin9:admin") == {"prov1": "proveedor", "admin9": "admin"}
    assert auth._parsear_roles({"Prov1": "PROVEEDOR"}) == {"prov1": "proveedor"}
    assert auth._parsear_roles("x:otro,y:") == {}          # roles inválidos se ignoran
    assert auth._parsear_roles(None) == {}


def test_rol_de_precedencia():
    roles = {"prov1": "proveedor"}
    assert auth.rol_de("Prov1", roles) == "proveedor"      # explícito, case-insensitive
    assert auth.rol_de("admin1", roles) == "admin"         # en ADMIN_USERS -> admin
    assert auth.rol_de("desconocido", roles) is None       # sin rol -> None (no autorizado)


def test_es_admin_es_proveedor_es_autorizado():
    roles = {"prov1": "proveedor"}
    assert auth.es_proveedor("prov1", roles) and not auth.es_admin("prov1", roles)
    assert auth.es_admin("admin1", roles) and not auth.es_proveedor("admin1", roles)
    assert auth.es_autorizado("prov1", roles) and auth.es_autorizado("admin1", roles)
    assert not auth.es_autorizado("intruso", roles)


def test_roles_desde_credenciales():
    cred = {"usernames": {"admin1": {"name": "A"}, "prov1": {"name": "P", "role": "Proveedor"}}}
    assert auth._roles_desde_credenciales(cred) == {"prov1": "proveedor"}


# --- AppTest: aislamiento del proveedor ----------------------------------- #

_HASH = stauth.Hasher.hash("Clave_123")
_AUTH_SECRET = {
    "credentials": {"usernames": {
        "admin1": {"name": "Admin Uno", "password": _HASH, "role": "admin"},
        "prov1": {"name": "Proveedor Uno", "password": _HASH, "role": "proveedor"}}},
    "cookie": {"name": "portal_test", "key": "clave-cookie-de-test-larga", "expiry_days": 7},
}

# Términos que el proveedor (acceso EXTERNO) JAMÁS debe ver.
_PROHIBIDO = ["valor cobrado al cliente", "utilidad", "margen", "novedades de peso",
              "clientes principales", "vista general", "entrada a colombia",
              "pactado vs cobrado", "conciliación"]


def _run(username, *, astrid="mock", excel_dir=""):
    os.environ.update({"DATASOURCE_ASTRID": astrid, "DATASOURCE_DROPBOX": "mock",
                       "EXCEL_DIRECTORIO_LOCAL": excel_dir})
    os.environ.pop("AUTH_USERS", None)
    os.environ.pop("AUTH_ROLES", None)
    import config
    importlib.reload(config)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["auth"] = _AUTH_SECRET
    at.session_state["authentication_status"] = True
    at.session_state["username"] = username
    at.session_state["name"] = username
    at.run()
    return at


def _textos(at):
    piezas = ([m.value for m in at.markdown] + [c.value for c in at.caption]
              + [g.value for g in at.get("header")] + [s.value for s in at.subheader]
              + [i.value for i in at.info])
    return " \n ".join(str(p) for p in piezas).lower()


def test_proveedor_solo_su_vista_sin_tabs_admin():
    at = _run("prov1")
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 0                               # el proveedor NO tiene las tabs admin
    texto = _textos(at)
    assert "mis facturas de despacho" in texto             # su vista propia
    for termino in _PROHIBIDO:
        assert termino not in texto, f"fuga de dato admin al proveedor: {termino!r}"


def test_proveedor_aislado_tambien_en_excel():
    at = _run("prov1", astrid="excel", excel_dir="tests/fixtures")
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 0
    texto = _textos(at)
    for termino in _PROHIBIDO:
        assert termino not in texto


def test_admin_ve_las_6_tabs():
    at = _run("admin1")
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 6                               # admin: acceso total


def test_admin_en_excel_ve_tabs():
    at = _run("admin1", astrid="excel", excel_dir="tests/fixtures")
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 6
