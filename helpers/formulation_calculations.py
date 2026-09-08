"""Formulation calculations, independent of the Streamlit UI.

Operates on the Formulation object and its component collections. See CLAUDE.md Layer 3
(ceramic) and Layer 4 (dispersing agent) for the full derivations.
"""

from helpers.formulation_model import Formulation
from helpers.material_helpers import build_dataframe_from_rows

FRACTION_SUM_TOLERANCE = 0.001


def _validate_ceramic_fractions(formulation: Formulation) -> None:
    """Validate ceramics exist, each Wc,i > 0, and sum(Wc,i) == 1 (+/- tolerance)."""
    if not formulation.ceramics:
        raise ValueError("At least one ceramic is required.")

    for i, ceramic in enumerate(formulation.ceramics):
        if ceramic.ceramic_fraction is None or ceramic.ceramic_fraction <= 0:
            raise ValueError(f"Ceramic {i + 1}: ceramic_fraction must be > 0.")

    total = sum(c.ceramic_fraction for c in formulation.ceramics)
    if abs(total - 1.0) > FRACTION_SUM_TOLERANCE:
        raise ValueError(
            f"Ceramic fractions must sum to 1 (+/- {FRACTION_SUM_TOLERANCE}); got {total}."
        )


def _validate_suspension_fractions(formulation: Formulation) -> None:
    """Validate 0 < Ws,i <= 1 for every ceramic."""
    for i, ceramic in enumerate(formulation.ceramics):
        wsi = ceramic.ceramic_fraction_in_suspension
        if wsi is None or not (0 < wsi <= 1):
            raise ValueError(
                f"Ceramic {i + 1}: ceramic_fraction_in_suspension must be in (0, 1]."
            )


def calculate_ceramic_suspension_masses(
    formulation: Formulation,
    reference_suspension_mass: float,
) -> None:
    """Calculate and store the suspension mass for every ceramic, using ceramic 1 as the
    reference (ms,1 = reference_suspension_mass, physically weighed by the user).

    ms,i = ms,1 * (Wc,i / Wc,1) * (Ws,1 / Ws,i)

    Stores the result in each ceramic's `suspension_mass`.
    """
    if reference_suspension_mass is None or reference_suspension_mass <= 0:
        raise ValueError("reference_suspension_mass must be > 0.")

    _validate_ceramic_fractions(formulation)
    _validate_suspension_fractions(formulation)

    reference = formulation.ceramics[0]
    wc1 = reference.ceramic_fraction
    ws1 = reference.ceramic_fraction_in_suspension

    for ceramic in formulation.ceramics:
        wci = ceramic.ceramic_fraction
        wsi = ceramic.ceramic_fraction_in_suspension
        ceramic.suspension_mass = reference_suspension_mass * (wci / wc1) * (ws1 / wsi)


def calculate_total_ceramic_mass(
    formulation: Formulation,
    reference_suspension_mass: float,
) -> float:
    """Derive the total ceramic mass from the reference suspension mass.

    mc,total = (ms,1 * Ws,1) / Wc,1
    """
    if reference_suspension_mass is None or reference_suspension_mass <= 0:
        raise ValueError("reference_suspension_mass must be > 0.")

    _validate_ceramic_fractions(formulation)
    _validate_suspension_fractions(formulation)

    reference = formulation.ceramics[0]
    return (reference_suspension_mass * reference.ceramic_fraction_in_suspension) / (
        reference.ceramic_fraction
    )


def calculate_individual_ceramic_masses(formulation: Formulation) -> None:
    """Calculate and store the ceramic mass contained in each ceramic's suspension.

    mc,i = ms,i * Ws,i

    Requires `suspension_mass` to already be populated (see
    calculate_ceramic_suspension_masses). Stores the result in each ceramic's `ceramic_mass`.
    """
    for i, ceramic in enumerate(formulation.ceramics):
        if ceramic.suspension_mass is None:
            raise ValueError(
                f"Ceramic {i + 1}: suspension_mass must be calculated first "
                "(see calculate_ceramic_suspension_masses)."
            )
        ceramic.ceramic_mass = ceramic.suspension_mass * ceramic.ceramic_fraction_in_suspension


def calculate_binder_masses(formulation: Formulation, mc_total: float) -> float:
    """Calculate and store each binder's target mass.

    total_binder_mass = mc_total * binder_to_ceramic_ratio
    Each binder then receives its share, proportional to its own percentage (each binder's
    `percentage` is relative to total binder mass, and should sum to 1 across all binders).

    Stores the result in each binder's `mass_target`. Returns the total binder mass.
    """
    if not formulation.binders:
        raise ValueError("At least one binder is required.")
    if not formulation.binder_to_ceramic_ratio:
        raise ValueError("binder_to_ceramic_ratio must be set (> 0).")

    total_binder_mass = mc_total * formulation.binder_to_ceramic_ratio
    for binder in formulation.binders:
        if binder.percentage is None:
            raise ValueError(f"Binder '{binder.name or binder.perm_id}': percentage must be set.")
        binder.mass_target = binder.percentage * total_binder_mass
    return total_binder_mass


def _mass_and_volume_relative_to_binder(
    percentage: float,
    total_binder_mass: float,
    concentration_mg_per_ml: float | None,
) -> tuple[float, float | None]:
    """mass [mg] = percentage * total_binder_mass [g] * 1000
    volume [uL] = mass [mg] / concentration_mg_per_ml * 1000, or None if concentration unknown.

    Shared by photo-initiator and additive sizing — both are small components dosed as a
    weight fraction relative to the total binder mass, converted to a pipettable volume via a
    concentration read from OpenBIS.
    """
    mass = percentage * total_binder_mass * 1000
    volume = mass / concentration_mg_per_ml * 1000 if concentration_mg_per_ml else None
    return mass, volume


def calculate_photo_initiator_masses(formulation: Formulation, total_binder_mass: float) -> None:
    """Calculate and store each photo-initiator's target mass and volume.

    Stores results in each photo-initiator's `mass_target` and `volume`. `volume` is left None
    for a photo-initiator whose `concentration_mg_per_ml` is not set (mass is still computed).
    """
    if not formulation.photo_initiators:
        raise ValueError("At least one photo-initiator is required.")
    if not total_binder_mass:
        raise ValueError("total_binder_mass must be > 0.")

    for pi in formulation.photo_initiators:
        if pi.percentage is None:
            raise ValueError(f"Photo-initiator '{pi.name or pi.perm_id}': percentage must be set.")
        pi.mass_target, pi.volume = _mass_and_volume_relative_to_binder(
            pi.percentage, total_binder_mass, pi.concentration_mg_per_ml
        )


def calculate_additive_mass(formulation: Formulation, total_binder_mass: float) -> None:
    """Calculate and store the additive's target mass and volume.

    Stores results in `formulation.additive.mass_target` and `.volume`. `volume` is left None
    if `concentration_mg_per_ml` is not set (mass is still computed).
    """
    if formulation.additive is None:
        raise ValueError("An additive is required.")
    if not total_binder_mass:
        raise ValueError("total_binder_mass must be > 0.")
    if formulation.additive.percentage is None:
        raise ValueError("Additive: percentage must be set.")

    formulation.additive.mass_target, formulation.additive.volume = (
        _mass_and_volume_relative_to_binder(
            formulation.additive.percentage,
            total_binder_mass,
            formulation.additive.concentration_mg_per_ml,
        )
    )


def calculate_dispersing_agent_addition(
    formulation: Formulation,
    reference_suspension_mass: float,
) -> float:
    """Calculate the additional dispersing-agent mass required to reach the target fraction.

    Wd,current = sum(Wc,i * Wd,i)
    md,add = mc,total * (Wd,t - Wd,current), only when Wd,t > Wd,current

    Stores Wd,current in `formulation.dispersing_agent.current_disp_fraction` and the result in
    `formulation.dispersing_agent.mass_to_add`. Also stores `.volume` (uL), computed from
    `mass_to_add` and `concentration_mg_per_ml`, or None if concentration is not set. Raises
    ValueError if Wd,t < Wd,current (target cannot be reached by adding dispersing agent alone).
    """
    if formulation.dispersing_agent is None:
        raise ValueError("formulation.dispersing_agent is required.")

    wdt = formulation.dispersing_agent.target_disp_fraction
    if wdt is None or not (0 <= wdt <= 1):
        raise ValueError("target_disp_fraction must be in [0, 1].")

    for i, ceramic in enumerate(formulation.ceramics):
        wdi = ceramic.disp_fraction_in_suspension
        if wdi is None or not (0 <= wdi <= 1):
            raise ValueError(f"Ceramic {i + 1}: disp_fraction_in_suspension must be in [0, 1].")

    mc_total = calculate_total_ceramic_mass(formulation, reference_suspension_mass)
    wd_current = sum(c.ceramic_fraction * c.disp_fraction_in_suspension for c in formulation.ceramics)
    formulation.dispersing_agent.current_disp_fraction = wd_current

    if wdt < wd_current - FRACTION_SUM_TOLERANCE:
        raise ValueError(
            f"Target dispersing-agent fraction ({wdt}) is below the current fraction "
            f"({wd_current}); it cannot be reached by adding dispersing agent alone."
        )

    # Clamp to 0: wdt can be fractionally below wd_current within tolerance (float rounding, or
    # a target essentially equal to the current fraction), which must not yield a negative mass.
    mass_to_add = max(0.0, mc_total * (wdt - wd_current))
    formulation.dispersing_agent.mass_to_add = mass_to_add

    concentration = formulation.dispersing_agent.concentration_mg_per_ml
    formulation.dispersing_agent.volume = (
        mass_to_add * 1000 / concentration * 1000 if concentration else None
    )

    return mass_to_add


def sync_formulation_to_materials_dict(formulation: Formulation, materials_dict: dict) -> None:
    """Synchronize the formulation model with the legacy `materials` dictionary.

    All components are synced (Phase 3a-3f complete): ceramic, binder, photo-initiator,
    solvent, additive, and dispersing agent.

    The legacy `materials["Ceramic"]` slot only ever represented a single ceramic, so it is
    populated from the reference ceramic (`formulation.ceramics[0]`) only for perm_id/name.
    Multi-ceramic export is deferred to a future Export Integration update.

    Binder mass sizing (Layer 5) reads `mc,total` and `formulation.binder_to_ceramic_ratio`
    directly from the Formulation object, not through this legacy dict, so the old
    `mass_soll_ceram` / `Weight fraction charge` / `weight_fraction_feedstock` fields (which
    only ever existed to feed the now-unused `calculate_binder_mass_g`) are intentionally not
    synced here — keeping fields no calculation reads would just be confusing dead weight.

    `materials["Binder"]["items"]` (perm_id/name only) still needs to exist because
    `helpers.openbis_client` reads it for export sample naming, and `materials["Binder"]
    ["total_mass"]` because the Photo-Initiator and Additive tabs size themselves relative to
    it — both are populated here from `formulation.binders`, whose `mass_target` values are
    expected to already be calculated (see `calculate_binder_masses`) before this is called.

    `materials["Photo-Initiator"]["items"]` (perm_id/name only) similarly still needs to exist
    because `helpers.material_helpers.collect_parent_materials` reads it to link OpenBIS parent
    samples on export.

    Every category also gets a `"df"` (property/value/unit rows, no "category" column — that is
    added by the caller) because `tab_summary` only includes a category in the Experiment Data
    export if `"df" in material`. Ceramic's `df` covers all N ceramics (not just the reference)
    since this is a plain display table, not an identity slot.

    `materials["Ceramic"]["items"]` (perm_id/name for every ceramic, not just the reference)
    exists so `helpers.material_helpers.collect_parent_materials` links *all* ceramics as
    OpenBIS parents on export, the same way it already does for binders/photo-initiators —
    `materials["Ceramic"]["perm_id"]`/`["name"]` remain reference-only, since sample naming
    (`helpers.openbis_client`) is intentionally still built from the reference ceramic alone.

    `materials["Binder"]["total_percentage"]` also needs to exist: `tab_export_openbis` blocks
    the export button unless it equals 100 — leaving it unsynced silently disables export
    entirely whenever a binder exists (it defaults to 0, which is never 100).
    """
    if not formulation.ceramics or not formulation.ceramics[0].perm_id:
        materials_dict["Ceramic"] = {}
    else:
        reference = formulation.ceramics[0]
        ceramic_rows = []
        for i, ceramic in enumerate(formulation.ceramics):
            if not ceramic.perm_id:
                continue
            ceramic_rows.extend(
                [
                    (f"Ceramic #{i + 1} Name", ceramic.name, ""),
                    (
                        f"Ceramic #{i + 1} Fraction (Wc,i)",
                        (ceramic.ceramic_fraction or 0) * 100,
                        "[%]",
                    ),
                    (
                        f"Ceramic #{i + 1} Fraction in suspension (Ws,i)",
                        (ceramic.ceramic_fraction_in_suspension or 0) * 100,
                        "[%]",
                    ),
                    (f"Ceramic #{i + 1} Suspension mass", ceramic.suspension_mass, "[g]"),
                    (f"Ceramic #{i + 1} Ceramic mass", ceramic.ceramic_mass, "[g]"),
                ]
            )
        materials_dict["Ceramic"] = {
            "perm_id": reference.perm_id,
            "name": reference.name,
            "values": {},
            "df": build_dataframe_from_rows(ceramic_rows),
            "items": [
                {"perm_id": ceramic.perm_id, "name": ceramic.name}
                for ceramic in formulation.ceramics
                if ceramic.perm_id
            ],
        }

    binder_section = materials_dict.setdefault(
        "Binder", {"items": [], "total_mass": 0, "total_percentage": 0}
    )
    binder_section["items"] = [
        {
            "perm_id": binder.perm_id,
            "name": binder.name,
            "percentage": (binder.percentage or 0) * 100,
            "mass_soll_binder": binder.mass_target,
            "mass_ist": binder.mass_measured,
        }
        for binder in formulation.binders
        if binder.perm_id
    ]
    binder_section["total_mass"] = sum(
        binder.mass_target or 0 for binder in formulation.binders
    )
    binder_section["total_percentage"] = sum(
        (binder.percentage or 0) * 100 for binder in formulation.binders
    )
    binder_rows = []
    for i, binder in enumerate(formulation.binders):
        if not binder.perm_id:
            continue
        binder_rows.extend(
            [
                (f"Binder #{i + 1} Name", binder.name, ""),
                (f"Binder #{i + 1} Percentage", (binder.percentage or 0) * 100, "[%]"),
                (f"Binder #{i + 1} Target mass", binder.mass_target, "[g]"),
                (f"Binder #{i + 1} Measured mass", binder.mass_measured, "[g]"),
            ]
        )
    binder_section["df"] = build_dataframe_from_rows(binder_rows)

    pi_section = materials_dict.setdefault("Photo-Initiator", {"items": []})
    pi_section["items"] = [
        {"perm_id": pi.perm_id, "name": pi.name}
        for pi in formulation.photo_initiators
        if pi.perm_id
    ]
    pi_rows = []
    for i, pi in enumerate(formulation.photo_initiators):
        if not pi.perm_id:
            continue
        pi_rows.extend(
            [
                (f"PI #{i + 1} Name", pi.name, ""),
                (f"PI #{i + 1} Percentage (of binder mass)", (pi.percentage or 0) * 100, "[%]"),
                (f"PI #{i + 1} Target mass", pi.mass_target, "[mg]"),
                (f"PI #{i + 1} Target volume", pi.volume, "[µL]"),
            ]
        )
    pi_section["df"] = build_dataframe_from_rows(pi_rows)

    if formulation.solvent and formulation.solvent.perm_id:
        materials_dict["Solvent"] = {
            "perm_id": formulation.solvent.perm_id,
            "name": formulation.solvent.name,
            "df": build_dataframe_from_rows(
                [
                    ("Name", formulation.solvent.name, ""),
                    ("Volume", formulation.solvent.volume_ml, "[mL]"),
                ]
            ),
        }
    else:
        materials_dict["Solvent"] = {}

    if formulation.additive and formulation.additive.perm_id:
        additive = formulation.additive
        materials_dict["Additive"] = {
            "perm_id": additive.perm_id,
            "name": additive.name,
            "df": build_dataframe_from_rows(
                [
                    ("Name", additive.name, ""),
                    ("Percentage (of binder mass)", (additive.percentage or 0) * 100, "[%]"),
                    ("Target mass", additive.mass_target, "[mg]"),
                    ("Target volume", additive.volume, "[µL]"),
                ]
            ),
        }
    else:
        materials_dict["Additive"] = {}

    if formulation.dispersing_agent and formulation.dispersing_agent.perm_id:
        da = formulation.dispersing_agent
        materials_dict["Dispersing Agent"] = {
            "perm_id": da.perm_id,
            "name": da.name,
            "df": build_dataframe_from_rows(
                [
                    ("Name", da.name, ""),
                    ("Target fraction", (da.target_disp_fraction or 0) * 100, "[%]"),
                    ("Current fraction", (da.current_disp_fraction or 0) * 100, "[%]"),
                    ("Mass to add", da.mass_to_add, "[g]"),
                    ("Volume to add", da.volume, "[µL]"),
                ]
            ),
        }
    else:
        materials_dict["Dispersing Agent"] = {}
