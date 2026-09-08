"""Experiment business logic: categories, properties, calculations, and autofill."""

from helpers.openbis_utils import extract_tables_as_list


# Categories used across the experiment data
CATEGORIES = ["Ceramic", "Binder", "Photo initiator", "Equipment"]


def format_float_value(value, decimal_places=3):
    """Format a float value with comma as decimal separator and max 3 decimal places.

    Parameters:
    - value: numeric value to format
    - decimal_places: max decimal places (default 3)

    Returns formatted string with comma as decimal separator, or original value if not numeric.
    """
    if value is None or value == "":
        return value
    try:
        float_val = float(str(value).replace(",", "."))
        # Format with specified decimal places, then replace . with ,
        formatted = f"{float_val:.{decimal_places}f}".rstrip("0").rstrip(".")
        return formatted.replace(".", ",")
    except (ValueError, TypeError):
        return value


def validate_sum_to_one(items: list, property_name: str = "percentage") -> tuple:
    """Validate that a list of items' property values sum to 100.0 (100%).

    Returns (is_valid: bool, total: float)
    """
    total = sum(item.get(property_name) or 0.0 for item in items)
    valid = (
        abs(total - 100.0) < 1e-4
    )  # tolerance for floating point, now checking for 100
    return valid, total


def assign_category_and_label(
    df, type_col="type", category_col="category", label_col="category_label"
):
    """Add category and label columns to a DataFrame.

    Categories are mapped from the type column; labels are sequential within each category.
    """
    # Force category mapping from type → fixed categories
    df[category_col] = df[type_col].map(lambda x: x if x in CATEGORIES else "Other")

    # Create label index inside each category
    df[label_col] = 0
    for cat, group in df.groupby(category_col):
        idx = group.index
        df.loc[idx, label_col] = range(1, len(idx) + 1)

    return df


# A compact mapping of category → property names (kept for compatibility)
CATEGORY_PROPERTIES = {
    "Ceramic": [
        "weight fraction in feedstock (decision)",
        "mass soll ceramic (decision)",
        "mass ist (weighted)",
    ],
    "Binder": [
        "percentage (decision)",
        "mass soll binder (calculated)",
        "mass ist (weighted)",
        "solvent (decision)",
        "volume solvent (decision)",
    ],
    "Dispersing Agent": [
        "current weight fraction (autofill)",
        "target weight fraction (decision)",
        "mass DA (calculated)",
        "volume (calculated)",
    ],
    "Photo-Initiator": [
        "'%' relative to binder (decision)",
        "mass soll binder (autofill)",
        "mass PI (calculated)",
        "volume PI (calculated)",
    ],
    "Additive": [
        "'%' relative to binder (decision)",
        "mass soll binder (autofill)",
        "mass Additives (calculated)",
        "volume Additives (calculated)",
    ],
}


PROPERTY_SCHEMA = {
    "Ceramic": {
        "autofill": ["weight fraction charge", "weight fraction disp. Susp."],
        "decision": ["weight fraction in feedstock", "mass soll ceramic"],
        "weighted": ["mass ist"],
        "calculated": [],
    },
    "Binder": {
        "decision": ["percentage", "solvent", "volume solvent"],
        "weighted": ["mass ist"],
        "calculated": ["mass soll binder"],
    },
    "Dispersing Agent": {
        "autofill": [
            "concentration disp. Agent",
            "weight fraction disp. Susp.",
            "current weight fraction",
        ],
        "decision": ["target weight fraction"],
        "calculated": ["mass DA", "volume"],
    },
    "Photo-Initiator": {
        "decision": ["'%' relative to binder"],
        "autofill": ["mass soll binder"],
        "calculated": ["mass PI", "volume PI"],
    },
    "Additive": {
        "decision": ["'%' relative to binder"],
        "autofill": ["mass soll binder"],
        "calculated": ["mass Additives", "volume Additives"],
    },
}


def initialize_scan(sample_id, category, scans_list):
    """Initialize an empty scan record and append it to scans_list."""
    scan = {
        "sample_id": sample_id,
        "category": category,
        "found": False,
        "name": sample_id,
        "decision": {},
        "weighted": {},
        "autofill": {},
        "calculated": {},
    }
    scans_list.append(scan)
    return scan


OPENBIS_FIELD_MAPPING = {
    "weight fraction charge": "Weight fraction charge",
    "weight fraction disp. Susp.": "Weight fraction disp. Susp.",
    "concentration disp. Agent": "Concentration disp. Agent",
}


AUTOFILL_MAPPING = {
    "Ceramic": {
        "weight fraction charge (autofill)": "Weight fraction charge",
        "weight fraction disp. Susp.(autofill)": "Weight fraction disp. Susp.",
    },
    "Dispersing Agent": {
        "current weight fraction (autofill)": "Weight fraction disp. Susp.",
        "concentration disp. Agent (autofill)": "Weight fraction disp. Susp.",
    },
    "Photo-Initiator": {
        "mass soll binder (autofill)": "mass soll binder",
    },
    "Additive": {
        "mass soll binder (autofill)": "mass soll binder",
    },
}


def collect_autofill_properties(scan, o):
    """Fetch and populate autofill properties from openBIS for a scan record."""
    # scan can be a string sample_id or dict; normalize to dict
    if isinstance(scan, str):
        scan = {
            "sample_id": scan,
            "autofill": {},
            "decision": {},
            "weighted": {},
            "calculated": {},
            "found": False,
        }

    try:
        tables = extract_tables_as_list(
            scan["sample_id"], property_name="description", o=o
        )
        # fill autofill fields based on CATEGORY_PROPERTIES or AUTOFILL_MAPPING
        for cat, mapping in AUTOFILL_MAPPING.items():
            if scan.get("category") == cat:
                for prop, table_field in mapping.items():
                    for table in tables:
                        for row_key, row_val in table.items():
                            if table_field in row_val:
                                scan["autofill"][prop] = row_val[table_field]
        scan["found"] = True
    except Exception:
        scan["found"] = False

    return scan

    return scan
