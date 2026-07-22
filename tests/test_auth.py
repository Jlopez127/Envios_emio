"""Tests de auth: normalización a minúsculas (workaround del bug de casing),
decisión de modo (abierto / login obligatorio) y registro del usuario en novedades."""

import auth
from core import modelos


def test_admin_users_todos_en_minuscula():
    assert auth.ADMIN_USERS == {"admin1", "admin2", "admin3"}
    assert all(u == u.lower() for u in auth.ADMIN_USERS)


def test_normalizar():
    assert auth.normalizar("  ADMIN1 ") == "admin1"
    assert auth.normalizar("Admin2") == "admin2"
    assert auth.normalizar(None) == ""
    assert auth.normalizar(" AdMiN3\t") == "admin3"


def test_es_admin_case_insensitive():
    assert auth.es_admin("Admin1") and auth.es_admin(" ADMIN3 ") and auth.es_admin("admin2")
    assert not auth.es_admin("otro")
    assert not auth.es_admin("")
    assert not auth.es_admin(None)


def test_config_desde_secrets_lowercasea_usernames(monkeypatch):
    fake_auth = {
        "credentials": {"usernames": {"Admin1": {"name": "A1", "password": "$2b$x"},
                                       "ADMIN2": {"name": "A2", "password": "$2b$y"}}},
        "cookie": {"name": "c", "key": "k", "expiry_days": 7},
    }

    class _Seccion:
        def to_dict(self):
            return fake_auth

    class _Secrets:
        def __getitem__(self, clave):
            if clave == "auth":
                return _Seccion()
            raise KeyError(clave)

    monkeypatch.setattr(auth.st, "secrets", _Secrets())
    cred, cookie = auth._config_desde_secrets()
    assert set(cred["usernames"]) == {"admin1", "admin2"}   # claves en minúsculas
    assert "Admin1" not in cred["usernames"]
    assert cookie["name"] == "c"


def test_config_desde_secrets_none_si_falta(monkeypatch):
    class _Secrets:
        def __getitem__(self, clave):
            raise KeyError(clave)

    monkeypatch.setattr(auth.st, "secrets", _Secrets())
    assert auth._config_desde_secrets() is None


# --- Decisión de modo: abierto (local) vs login obligatorio (host) -------- #

def test_modo_auth_login_si_hay_config():
    # Con [auth] presente -> login obligatorio (independiente de AUTH_USERS).
    assert auth._modo_auth(True, False) == "login"
    assert auth._modo_auth(True, True) == "login"


def test_modo_auth_sin_config_es_obligatorio_no_abierto():
    # AUTH_USERS presente pero falta [auth] -> obligatorio (NUNCA modo abierto en host).
    assert auth._modo_auth(False, True) == "sin_config"


def test_modo_auth_abierto_solo_sin_ninguna_senal():
    # Ni [auth] ni AUTH_USERS -> modo abierto (solo local).
    assert auth._modo_auth(False, False) == "abierto"


def test_auth_users_raw_desde_env(monkeypatch):
    monkeypatch.setenv("AUTH_USERS", "admin1, Admin2 ,ADMIN3")
    assert auth._auth_users_raw() == "admin1, Admin2 ,ADMIN3"
    # y el set de admins queda en minúsculas, sin espacios.
    assert auth._cargar_admins() == {"admin1", "admin2", "admin3"}


def test_auth_users_raw_none_si_no_configurado(monkeypatch):
    monkeypatch.delenv("AUTH_USERS", raising=False)
    # sin runtime de streamlit, get_secret devuelve None -> raw None.
    assert auth._auth_users_raw() is None


# --- El usuario logueado queda registrado en la novedad que justifica ----- #

def test_construir_novedad_registra_usuario():
    n = modelos.construir_novedad(
        usuario="admin1", manifiesto_id="900007", tipo="peso_tula",
        discriminador="260714-900007-3", campo_disc="tula_codigo",
        valor_esperado=250.0, valor_real=20.0, delta=-230.0,
        justificacion="repesaje verificado", accion="Aceptar cargo")
    assert n["usuario"] == "admin1"          # queda registrado quién justificó
    assert n["tula_codigo"] == "260714-900007-3" and n["guia"] is None
    assert n["estado"] == "resuelta"


def test_construir_novedad_discrimina_guia():
    n = modelos.construir_novedad(
        usuario="admin2", manifiesto_id="900007", tipo="cobro_distribucion",
        discriminador="100005", campo_disc="guia",
        valor_esperado=5.0, valor_real=12.5, delta=7.5,
        justificacion="x", accion="Reclamar a proveedor")
    assert n["usuario"] == "admin2"
    assert n["guia"] == "100005" and n["tula_codigo"] is None
