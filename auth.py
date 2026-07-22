"""Autenticación con streamlit-authenticator 0.4.x.

Usuarios admin autorizados. streamlit-authenticator tiene un BUG CONOCIDO de casing:
por eso TODO se maneja en minúsculas — las claves de username del secrets y TODA
comparación de permisos con `.strip().lower()`; el set de autorizados va en minúsculas.

Config vía secrets (`[auth]`, nunca en el repo). **Modo abierto** (sin login) SOLO en
local, cuando NO hay `[auth]` NI `AUTH_USERS`. En el host, con `AUTH_USERS` presente, el
login es OBLIGATORIO: si falta `[auth]`, error claro, nunca modo abierto.
"""

import os

import streamlit as st


def normalizar(u):
    """strip + lower (workaround del bug de casing de la librería)."""
    return (u or "").strip().lower()


def _auth_users_raw():
    """Valor crudo de `AUTH_USERS` (env o secret `[auth] usuarios`), o None si no está
    configurado. Sirve de señal de "auth esperada" (host)."""
    raw = os.environ.get("AUTH_USERS")
    if not raw:
        try:
            import config
            raw = config.get_secret("auth", "usuarios", "AUTH_USERS")
        except Exception:
            raw = None
    return raw or None


def _cargar_admins(raw=None):
    """Set de usuarios admin autorizados (en minúsculas). Los REALES se cargan por
    env/secret `AUTH_USERS` (coma-separados); default DEMO genérico admin1/2/3. Nunca hay
    nombres reales en el código."""
    raw = raw if raw is not None else _auth_users_raw()
    raw = raw or "admin1,admin2,admin3"
    return {u for u in (normalizar(x) for x in str(raw).split(",")) if u}


# Usuarios autorizados — SIEMPRE en minúsculas. Reales vía secret AUTH_USERS.
ADMIN_USERS = _cargar_admins()


def es_admin(username):
    return normalizar(username) in ADMIN_USERS


def _modo_auth(cfg_presente, auth_users_configurado):
    """Decide el modo de auth (pura, sin runtime; testeable):

    - ``"login"``      → hay `[auth]` con credenciales → login obligatorio.
    - ``"sin_config"`` → `AUTH_USERS` presente (host) pero falta `[auth]` → ERROR claro,
      NUNCA modo abierto.
    - ``"abierto"``    → ni `[auth]` ni `AUTH_USERS` → modo abierto (solo local).
    """
    if cfg_presente:
        return "login"
    if auth_users_configurado:
        return "sin_config"
    return "abierto"


def _config_desde_secrets():
    """(credenciales, cookie) desde st.secrets['auth'], o None si no está configurado.
    Las claves de username se pasan a minúsculas."""
    try:
        auth = st.secrets["auth"]
        data = auth.to_dict() if hasattr(auth, "to_dict") else dict(auth)
    except Exception:
        return None
    usernames = ((data.get("credentials") or {}).get("usernames")) or {}
    if not usernames:
        return None
    credenciales = {"usernames": {normalizar(k): dict(v) for k, v in usernames.items()}}
    cookie = data.get("cookie") or {}
    return credenciales, cookie


def proteger():
    """Protege el dashboard. Devuelve el username (minúsculas) autenticado y autorizado.

    - `modo abierto` (ni `[auth]` ni `AUTH_USERS`) → aviso y devuelve None (el caller usa
      un usuario de sesión). Solo local.
    - `sin_config` (`AUTH_USERS` presente pero falta `[auth]`) → error y detiene: en el
      host el login es obligatorio, nunca modo abierto.
    - `login` (`[auth]` configurado) → login; credenciales inválidas o usuario no
      autorizado → detiene con mensaje claro.
    """
    cfg = _config_desde_secrets()
    modo = _modo_auth(cfg is not None, _auth_users_raw() is not None)

    if modo == "abierto":
        st.warning("⚠️ Autenticación NO configurada — **modo abierto** (solo desarrollo "
                   "local). Para producción, configurá `[auth]` (y `AUTH_USERS`) en los "
                   "secrets del host (ver README).")
        return None

    if modo == "sin_config":
        st.error("🔒 Login obligatorio: `AUTH_USERS` está configurado pero falta la sección "
                 "`[auth]` con credenciales hasheadas. Configurala en los secrets del host "
                 "(ver README). El portal no abre sin login.")
        st.stop()

    try:
        import streamlit_authenticator as stauth
    except Exception:
        st.error("Falta el paquete `streamlit-authenticator` (ver requirements.txt).")
        st.stop()

    credenciales, cookie = cfg
    authenticator = stauth.Authenticate(
        credenciales,
        cookie.get("name", "encargomio_portal"),
        cookie.get("key", "clave-cookie-por-defecto"),
        float(cookie.get("expiry_days", 7)),
    )
    authenticator.login(location="main")

    estado = st.session_state.get("authentication_status")
    if estado is False:
        st.error("Usuario o contraseña incorrectos.")
        st.stop()
    if estado is None:
        st.info("Ingresá tus credenciales (usuario en **minúsculas**).")
        st.stop()

    username = normalizar(st.session_state.get("username"))
    if not es_admin(username):
        st.error(f"Usuario «{username}» no autorizado para este portal.")
        with st.sidebar:
            try:
                authenticator.logout("Cerrar sesión", "sidebar")
            except Exception:
                pass
        st.stop()

    with st.sidebar:
        st.caption(f"Sesión: **{st.session_state.get('name', username)}**")
        try:
            authenticator.logout("Cerrar sesión", "sidebar")
        except Exception:
            pass
    return username
