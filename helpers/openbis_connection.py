"""OpenBIS connection using Personal Access Tokens (PAT).

Tokens are entered by the user through the Streamlit UI and live only in
st.session_state for the duration of the browser session. They are never
written to disk, keyring, or any other persistent store, and are never
included in log output or error messages.
"""

from pybis import Openbis


def connect_with_pat(url: str, token: str) -> Openbis:
    """Connect to OpenBIS using a Personal Access Token.

    Raises ValueError with a user-safe message (never containing the token
    itself) if the URL/token are missing, the token is invalid or expired,
    or the connection otherwise fails.
    """
    if not url or not url.strip():
        raise ValueError("Please provide the OpenBIS URL.")
    if not token or not token.strip():
        raise ValueError("Please provide a Personal Access Token.")

    o = Openbis(url.strip())
    try:
        o.set_token(token.strip(), save_token=False)
    except ValueError:
        raise ValueError(
            "This Personal Access Token is invalid or has expired. "
            "Generate a new one in openBIS and try again."
        )
    except Exception as exc:
        raise ValueError(
            f"Could not connect to OpenBIS ({type(exc).__name__}). "
            "Check the URL and your network connection."
        )
    return o


def get_username_from_token(o: Openbis) -> str | None:
    """Best-effort extraction of the username embedded in an openBIS PAT.

    OpenBIS PATs are formatted as "<username>-<id>" (optionally prefixed
    with "$pat-"), so the username can be recovered without a separate
    login call. Returns None if it can't be determined.
    """
    try:
        username = o._get_username()
        return username or None
    except Exception:
        return None
