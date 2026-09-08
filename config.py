# =========================
# Application Configuration
# =========================

import os
import streamlit as st

# Application name
APP_NAME = "Resin Formulation Manager"
# Application version
VERSION = "2.0.0"
DESCRIPTION = "Resin Formulation Manager for n Ceramics"


def _secrets_file_exists() -> bool:
    """Whether any secrets.toml Streamlit would actually read exists on disk.

    Checked ourselves, ahead of touching st.secrets, because st.secrets.get(...) has a
    side effect when NO secrets.toml exists anywhere: internally it renders a visible
    st.error(...) in the app before raising FileNotFoundError — a try/except around that
    call prevents the crash, but not the error box. Skipping st.secrets entirely in that
    case avoids it.
    """
    try:
        paths = st.config.get_option("secrets.files")
    except Exception:
        return False
    return any(os.path.exists(p) for p in paths)


def _get_secret(key: str, default: str = "") -> str:
    """Read a Streamlit secret, defaulting to `default` if the key isn't set, or if no
    secrets.toml exists at all.
    """
    if not _secrets_file_exists():
        return default
    try:
        return st.secrets.get(key, default)
    except FileNotFoundError:
        return default


# Deployment-specific defaults. Set via .streamlit/secrets.toml locally, or via the
# "Secrets" panel in Streamlit Community Cloud's app settings when deploying — never
# committed to git. Blank by default so the app ships with no institution-specific
# values baked in; the user can still type a URL/space directly in the UI either way.
#
# These are functions, not module-level constants, deliberately: touching st.secrets when
# no secrets.toml exists at all has a side effect that trips Streamlit's "set_page_config
# must be the first command" check if it happens at import time (before main() gets a
# chance to call set_page_config). Calling these lazily, from inside the tabs that need
# them, keeps that access safely after set_page_config has already run.
def get_default_openbis_url() -> str:
    return _get_secret("openbis_url")


def get_default_openbis_space() -> str:
    return _get_secret("default_space")
