"""
Material tab helpers for code reusability.
Extracted common patterns to reduce duplication across tabs.
"""

from typing import Any
import pandas as pd
from helpers.openbis_utils import extract_tables_as_list
from helpers.helpers import safe_float


def get_openbis_table(perm_id: str, o: Any) -> dict[str, Any] | None:
    """
    Safely extract OpenBIS table from sample.

    Args:
        perm_id: Sample permutation ID from openBIS
        o: OpenBIS connection object

    Returns:
        dict: OpenBIS table with property data, or None if not available
    """
    try:
        tables = extract_tables_as_list(perm_id, "description", o)
        return tables[0] if tables else None
    except Exception:
        return None


def extract_property_value(
    table: dict[str, Any] | None, property_name: str
) -> float | None:
    """
    Safely extract property value from OpenBIS table and convert to float.

    Args:
        table: OpenBIS table dict
        property_name: Name of the property to extract

    Returns:
        float: Numeric value, or None if property not found/invalid

    Example:
        >>> conc = extract_property_value(table, "Concentration PI")
    """
    if not table:
        return None

    prop = table.get(property_name)
    if prop:
        return safe_float(prop.get("value"))
    return None


def build_dataframe_from_rows(
    rows: list[tuple[str, Any, str]], category: str | None = None
) -> pd.DataFrame:
    """
    Standardized dataframe creation from rows.

    Args:
        rows: List of tuples: (property_name, value, unit)
        category: Optional category to insert as first column

    Returns:
        pd.DataFrame: Properly formatted dataframe with string values

    Example:
        >>> rows = [("Name", "Sample A", ""), ("Mass", 1.5, "g")]
        >>> df = build_dataframe_from_rows(rows, category="Ceramic")
    """
    df = pd.DataFrame(rows, columns=["property", "value", "unit"])
    df["value"] = df["value"].astype(str)

    if category:
        df.insert(0, "category", category)

    return df


def extract_openbis_rows(table: dict[str, Any] | None) -> list[tuple[str, Any, str]]:
    """
    Extract all OpenBIS properties as rows for dataframe.

    Args:
        table: OpenBIS table dict with properties

    Returns:
        list: List of tuples (property_name, value, unit)

    Example:
        >>> rows = extract_openbis_rows(openbis_table)
        >>> rows.extend(user_input_rows)
    """
    rows = []
    if table:
        for prop, content in table.items():
            val = content.get("value")
            unit = content.get("unit", "")
            rows.append((prop, val, unit))
    return rows


def get_numeric_from_df(df: pd.DataFrame, prop_name: str) -> float | None:
    """
    Extract numeric value from a DataFrame by property name.
    Converts commas to dots and returns float if possible.

    Args:
        df: DataFrame with 'property' and 'value' columns
        prop_name: Property name to search for

    Returns:
        float: Numeric value, or None if not found/invalid

    Example:
        >>> mass = get_numeric_from_df(ceramic_df, "mass_soll_ceram")
    """
    row = df.loc[df["property"] == prop_name, "value"]
    if not row.empty:
        try:
            return float(row.values[0].replace(",", "."))
        except Exception:
            return None
    return None


def fetch_ceramic_suspension_properties(perm_id: str, o: Any) -> dict[str, Any]:
    """Fetch a ceramic's suspension weight fractions from its OpenBIS description table.

    "Weight fraction charge" (Ws,i, the ceramic's fraction in its own suspension) and
    "Weight fraction disp. Susp." (Wd,i, the dispersing-agent fraction already present,
    relative to the ceramic) are properties of the commercial suspension itself, already known
    from OpenBIS — the user should not have to re-enter them.

    Args:
        perm_id: Ceramic sample permID.
        o: OpenBIS connection object.

    Returns:
        dict with:
            - "table": the raw OpenBIS table (dict), or None if unavailable.
            - "ceramic_fraction_in_suspension": Ws,i as a fraction in [0, 1], or None if the
              "Weight fraction charge" property was not found.
            - "disp_fraction_in_suspension": Wd,i as a fraction in [0, 1], or None if the
              "Weight fraction disp. Susp." property was not found.
    """
    table = get_openbis_table(perm_id, o)
    wf_charge = extract_property_value(table, "Weight fraction charge")
    wf_disp_susp = extract_property_value(table, "Weight fraction disp. Susp.")
    return {
        "table": table,
        "ceramic_fraction_in_suspension": (
            wf_charge / 100.0 if wf_charge is not None else None
        ),
        "disp_fraction_in_suspension": (
            wf_disp_susp / 100.0 if wf_disp_susp is not None else None
        ),
    }


def calculate_ceramic_suspension_mass(
    mass_soll_ceram: float, weight_fraction_charge: float
) -> float:
    """
    Calculate ceramic mass in suspension from target mass and weight fraction.

    Args:
        mass_soll_ceram: Target mass of ceramic (g)
        weight_fraction_charge: Weight fraction of ceramic in charge (%)

    Returns:
        float: Mass of ceramic in suspension (g)

    Example:
        >>> mass_in_susp = calculate_ceramic_suspension_mass(100.0, 45.0)
    """
    return mass_soll_ceram * weight_fraction_charge / 100


def collect_parent_materials(
    experiment: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """
    Collect all parent material permIDs and names from experiment.

    Args:
        experiment: Session state experiment dict

    Returns:
        tuple: (parents list of permids, parents_with_names list of (permid, category, name))

    Example:
        >>> parents, parents_with_names = collect_parent_materials(experiment)
        >>> for permid, cat, name in parents_with_names:
        >>>     print(f"{cat} - {name}: {permid}")
    """
    parents = []
    parents_with_names = []

    gen_info = experiment.get("general_info", {})
    materials = experiment.get("materials", {})

    # Ceramics (all N, not just the reference)
    ceramics = materials.get("Ceramic", {}).get("items", [])
    for i, ceramic in enumerate(ceramics, 1):
        if ceramic.get("perm_id"):
            parents.append(ceramic.get("perm_id"))
            ceramic_name = ceramic.get("name", f"Ceramic #{i}")
            parents_with_names.append(
                (ceramic.get("perm_id"), f"Ceramic #{i}", ceramic_name)
            )

    # Binders
    binders = materials.get("Binder", {}).get("items", [])
    for i, binder in enumerate(binders, 1):
        if binder.get("perm_id"):
            parents.append(binder.get("perm_id"))
            binder_name = binder.get("name", f"Binder #{i}")
            parents_with_names.append(
                (binder.get("perm_id"), f"Binder #{i}", binder_name)
            )

    # Solvent
    solvent_data = materials.get("Solvent", {})
    if solvent_data.get("perm_id"):
        parents.append(solvent_data.get("perm_id"))
        solvent_name = solvent_data.get("name", "Solvent")
        parents_with_names.append(
            (solvent_data.get("perm_id"), "Solvent", solvent_name)
        )

    # Dispersing Agent
    disp_data = materials.get("Dispersing Agent", {})
    if disp_data.get("perm_id"):
        parents.append(disp_data.get("perm_id"))
        disp_name = disp_data.get("name", "Dispersing Agent")
        parents_with_names.append(
            (disp_data.get("perm_id"), "Dispersing Agent", disp_name)
        )

    # Photo-Initiators
    pis = materials.get("Photo-Initiator", {}).get("items", [])
    for i, pi in enumerate(pis, 1):
        if pi.get("perm_id"):
            parents.append(pi.get("perm_id"))
            pi_name = pi.get("name", f"PI #{i}")
            parents_with_names.append((pi.get("perm_id"), f"PI #{i}", pi_name))

    # Additive
    add_data = materials.get("Additive", {})
    if add_data.get("perm_id"):
        parents.append(add_data.get("perm_id"))
        add_name = add_data.get("name", "Additive")
        parents_with_names.append((add_data.get("perm_id"), "Additive", add_name))

    # Equipment (if scanned)
    if gen_info.get("equipment_perm_id"):
        parents.append(gen_info.get("equipment_perm_id"))
        equipment_name = gen_info.get("equipment_name", "Equipment")
        parents_with_names.append(
            (gen_info.get("equipment_perm_id"), "Equipment", equipment_name)
        )

    return parents, parents_with_names
