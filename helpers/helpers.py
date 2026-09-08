# helpers.py

# ---------- SAFE CONVERSIONS ----------
def safe_float(value, default=None):
    if value is None:
        return default
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return default
