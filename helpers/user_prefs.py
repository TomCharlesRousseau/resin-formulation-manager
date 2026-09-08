"""Local, per-machine user preferences.

Stored as a plain JSON file next to the app, not synced via git or OpenBIS — this is for
per-installation UI preferences (e.g. "don't show me this reminder again"), not experiment data.
"""

import json
from pathlib import Path

_PREFS_FILE = Path(__file__).resolve().parent.parent / ".user_prefs.json"


def _load_prefs() -> dict:
    if not _PREFS_FILE.exists():
        return {}
    try:
        return json.loads(_PREFS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        _PREFS_FILE.write_text(json.dumps(prefs))
    except OSError:
        pass


def should_show_first_time_popup() -> bool:
    """Whether the first-time "verify calculations" reminder should still be shown."""
    return not _load_prefs().get("dismissed_first_time_popup", False)


def dismiss_first_time_popup_permanently() -> None:
    """Record that the user checked "Don't remind me again" — persists across app restarts."""
    prefs = _load_prefs()
    prefs["dismissed_first_time_popup"] = True
    _save_prefs(prefs)
