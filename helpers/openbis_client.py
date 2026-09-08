"""OpenBIS client helpers: sample naming and dataset attachment."""

import pandas as pd
import os
from pathlib import Path
from datetime import datetime


def get_purpose_suffix(purpose):
    """Map purpose string to suffix.

    Parameters:
    - purpose: Purpose string from General Information tab

    Returns the suffix string for the name.
    """
    purpose_map = {
        "2PP Feedstocks": "2PP",
        "Xolography Feedstocks": "Xolo",
        "UV Feedstocks": "UV",
        "2PP-UV-Kombi Feedstocks": "2PP-UV",
        "Other": "*",
    }
    return purpose_map.get(purpose, "*")


def _resolve_alias(o, perm_id, fallback_name):
    """Fetch a sample's alias from OpenBIS, falling back to a provided name."""
    if perm_id and o is not None:
        try:
            sample = o.get_sample(perm_id)
            alias = getattr(sample.props, "alias", None)
            if alias:
                return alias
        except Exception:
            pass
    return fallback_name or "Unknown"


def _build_name_parts(experiment, o=None):
    """Compute the shared pieces (ceramic label, binder list, date, purpose suffix) used by
    both build_experimental_step_name and build_resin_name.

    The ceramic label is prefixed with "<N>_Ceramics_" when the formulation has more than one
    ceramic (reads formulation.ceramics directly — the legacy materials dict only ever tracks
    the reference ceramic's identity, not the count), e.g. "3_Ceramics_3YSZ" instead of "3YSZ".
    """
    materials = experiment.get("materials", {})

    ceramic_perm_id = materials.get("Ceramic", {}).get("perm_id")
    ceramic_fallback = materials.get("Ceramic", {}).get("name", "Unknown")
    ceramic_name = _resolve_alias(o, ceramic_perm_id, ceramic_fallback)

    formulation = experiment.get("formulation")
    n_ceramics = len(formulation.ceramics) if formulation else 0
    ceramic_label = f"{n_ceramics}_Ceramics_{ceramic_name}" if n_ceramics > 1 else ceramic_name

    binder_names = []
    for binder in materials.get("Binder", {}).get("items", []):
        binder_alias = _resolve_alias(o, binder.get("perm_id"), binder.get("name"))
        if binder_alias:
            binder_names.append(binder_alias)
    binders_str = "/".join(binder_names) if binder_names else "NoBinders"

    weight_fraction_feedstock = materials.get("Ceramic", {}).get("values", {}).get(
        "weight_fraction_feedstock"
    )

    date_str = pd.Timestamp.today().strftime("%Y%m%d")
    purpose = experiment.get("general_info", {}).get("purpose", "Other")
    suffix = get_purpose_suffix(purpose)

    return ceramic_label, weight_fraction_feedstock, binders_str, date_str, suffix


def build_experimental_step_name(experiment, o=None):
    """Build an experimental step name from the experiment dict.

    Parameters:
    - experiment: dict with `materials` (Ceramic, Binders, etc.) and `formulation`
    - o: optional openBIS client object for fetching alias properties

    Returns a formatted string like "20250203_Mixing_Ceramic_in_Binder_for_2PP", or
    "20250203_Mixing_3_Ceramics_Ceramic_in_Binder_for_2PP" for a multi-ceramic formulation.
    """
    ceramic_label, wf_feedstock, binders_str, date_str, suffix = _build_name_parts(experiment, o)

    if wf_feedstock is not None:
        return f"{date_str}_Mixing_{ceramic_label}_{wf_feedstock}wt%_in_{binders_str}_for_{suffix}"
    return f"{date_str}_Mixing_{ceramic_label}_in_{binders_str}_for_{suffix}"


def build_resin_name(experiment, o=None):
    """Build a resin sample name from the experiment dict (without 'Mixing').

    Parameters:
    - experiment: dict with `materials` (Ceramic, Binders, etc.) and `formulation`
    - o: optional openBIS client object for fetching alias properties

    Returns a formatted string like "20250203_Ceramic_in_Binder_for_2PP", or
    "20250203_3_Ceramics_Ceramic_in_Binder_for_2PP" for a multi-ceramic formulation.
    """
    ceramic_label, wf_feedstock, binders_str, date_str, suffix = _build_name_parts(experiment, o)

    if wf_feedstock is not None:
        return f"{date_str}_{ceramic_label}_{wf_feedstock}wt%_in_{binders_str}_for_{suffix}"
    return f"{date_str}_{ceramic_label}_in_{binders_str}_for_{suffix}"


def build_resin_sample_name(experiment, o=None):
    """Deprecated: Use build_experimental_step_name instead."""
    return build_experimental_step_name(experiment, o)


def add_dataset(o, sample, experiment, excel_bytes):
    """Attach an Excel summary to a sample in openBIS and save locally.

    Parameters:
    - o: openBIS client object
    - sample: openBIS sample object
    - experiment: experiment dict (for getting the path)
    - excel_bytes: bytes of the Excel file

    Returns tuple (dataset, export_path) on success; raises on error.
    """
    # Create exports folder if it doesn't exist
    exports_dir = Path("exports")
    exports_dir.mkdir(exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_experiment_summary.xlsx"
    export_path = exports_dir / filename
    
    # Save Excel locally
    try:
        export_path.write_bytes(excel_bytes)
    except OSError as e:
        raise ValueError(f"Failed to save Excel export to {export_path}: {e}")
    
    try:
        # Get the experiment path
        exp_path = experiment.get("general_info", {}).get("openbis_path", {}).get("full_path")

        if not exp_path:
            raise ValueError(
                "Experiment path is None - could not get openbis_path.full_path"
            )

        ds = o.new_dataset(
            type="ATTACHMENT",
            experiment=exp_path,
            sample=sample,
            files=[str(export_path)],
            props={
                "$name": "experiment_summary",
                "notes": "Experiment summary with all chemicals and properties automatically generated",
            },
        )

        if ds is None:
            raise ValueError("o.new_dataset() returned None - dataset creation failed")

        ds.save()
        return ds, str(export_path)
    
    except Exception as e:
        raise ValueError(f"Failed to attach dataset to openBIS: {e}")
