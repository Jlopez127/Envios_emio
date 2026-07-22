"""AppTest del gate de autenticación: modo abierto (sin auth) y login obligatorio
(con auth). Cubre no-logueado, login OK autorizado, y usuario no autorizado."""

import importlib
import os

import streamlit_authenticator as stauth
from streamlit.testing.v1 import AppTest

# Un hash real (bcrypt) para el usuario de prueba admin1 (está en el ADMIN_USERS default).
_HASH_ADMIN1 = stauth.Hasher.hash("Admin1_123")
_AUTH_SECRET = {
    "credentials": {"usernames": {
        "admin1": {"name": "Admin Uno", "password": _HASH_ADMIN1, "email": "a@x.co"}}},
    "cookie": {"name": "portal_test", "key": "clave-cookie-de-test-larga", "expiry_days": 7},
}


def _run(*, auth_secret=None, session=None, auth_users=None):
    os.environ.update({"DATASOURCE_ASTRID": "mock", "DATASOURCE_DROPBOX": "mock",
                       "EXCEL_DIRECTORIO_LOCAL": ""})
    import config
    importlib.reload(config)   # fija modo mock aunque otro test dejara config en excel
    if auth_users is None:
        os.environ.pop("AUTH_USERS", None)
    else:
        os.environ["AUTH_USERS"] = auth_users
    try:
        at = AppTest.from_file("app.py", default_timeout=60)
        if auth_secret is not None:
            at.secrets["auth"] = auth_secret
        for k, v in (session or {}).items():
            at.session_state[k] = v
        at.run()
        return at
    finally:
        os.environ.pop("AUTH_USERS", None)


def test_modo_abierto_sin_auth_renderiza():
    # Ni [auth] ni AUTH_USERS -> modo abierto (aviso) y dashboard visible.
    at = _run()
    assert not at.exception
    assert len(at.tabs) == 5
    assert any("modo abierto" in w.value for w in at.warning)


def test_sin_config_con_auth_users_es_obligatorio():
    # AUTH_USERS presente pero SIN [auth] -> login obligatorio (error, NO modo abierto).
    at = _run(auth_users="admin1,admin2")
    assert not at.exception
    assert len(at.tabs) == 0                                   # no abre el dashboard
    assert any("obligatorio" in e.value.lower() for e in at.error)
    assert not at.warning or not any("modo abierto" in w.value for w in at.warning)


def test_login_obligatorio_no_autenticado():
    # [auth] configurado, sin sesión -> pide credenciales y detiene (no hay tabs).
    at = _run(auth_secret=_AUTH_SECRET)
    assert not at.exception
    assert len(at.tabs) == 0
    assert any("credenciales" in i.value.lower() for i in at.info)


def test_login_ok_usuario_autorizado_renderiza():
    # Sesión autenticada como admin1 (autorizado) -> dashboard visible (login pasó y el
    # usuario está autorizado; si no, serían 0 tabs + error).
    at = _run(auth_secret=_AUTH_SECRET,
              session={"authentication_status": True, "username": "admin1", "name": "Admin Uno"})
    assert not at.exception
    assert len(at.tabs) == 5
    assert not any("no autorizado" in e.value.lower() for e in at.error)
    # proteger() rotula la sesión del usuario (en caption o markdown del sidebar).
    textos = [c.value for c in at.caption] + [m.value for m in at.markdown]
    assert any("Sesión" in t for t in textos)


def test_login_usuario_no_autorizado_se_bloquea():
    # Autenticado pero username fuera de ADMIN_USERS -> bloqueado (no abre).
    at = _run(auth_secret=_AUTH_SECRET,
              session={"authentication_status": True, "username": "intruso", "name": "X"})
    assert not at.exception
    assert len(at.tabs) == 0
    assert any("no autorizado" in e.value.lower() for e in at.error)
