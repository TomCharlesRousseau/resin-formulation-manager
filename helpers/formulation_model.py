"""Formulation data model: dataclasses for a dynamic number of formulation components.

Weight fractions (ceramic_fraction, ceramic_fraction_in_suspension, disp_fraction_in_suspension,
percentage/target fields below) are stored as dimensionless fractions in [0, 1], matching the
math in CLAUDE.md. The rest of the existing codebase (OpenBIS tables, the legacy `materials`
dict) uses percent (0-100) — that conversion happens at the OpenBIS-fetch and
sync_formulation_to_materials_dict boundaries, not inside this model.
"""

from dataclasses import dataclass, field


@dataclass
class Ceramic:
    """One ceramic material and its associated suspension information.

    ceramic_fraction (Wc,i): fraction of this ceramic relative to the total ceramic content.
    ceramic_fraction_in_suspension (Ws,i): ceramic fraction in this ceramic's suspension.
    disp_fraction_in_suspension (Wd,i): dispersing-agent fraction relative to this ceramic's
        mass (not the suspension mass, despite the name — see CLAUDE.md).
    suspension_mass: mass of suspension to be physically weighed (user input for the reference
        ceramic, calculated for all others).
    ceramic_mass: calculated mass of ceramic contained in that suspension.
    """

    perm_id: str | None = None
    name: str | None = None
    ceramic_fraction: float | None = None
    ceramic_fraction_in_suspension: float | None = None
    disp_fraction_in_suspension: float | None = None
    suspension_mass: float | None = None
    ceramic_mass: float | None = None


@dataclass
class Binder:
    """One binder material."""

    perm_id: str | None = None
    name: str | None = None
    percentage: float | None = None  # fraction of total binder mass
    mass_target: float | None = None
    mass_measured: float | None = None
    solvent: str | None = None
    solvent_volume: float | None = None


@dataclass
class PhotoInitiator:
    """One photo-initiator material."""

    perm_id: str | None = None
    name: str | None = None
    percentage: float | None = None  # fraction relative to total binder mass
    mass_target: float | None = None
    mass_measured: float | None = None
    concentration_mg_per_ml: float | None = None
    volume: float | None = None


@dataclass
class Solvent:
    """Single solvent instance."""

    perm_id: str | None = None
    name: str | None = None
    volume_ml: float | None = None


@dataclass
class Additive:
    """Single additive instance."""

    perm_id: str | None = None
    name: str | None = None
    percentage: float | None = None  # fraction relative to total binder mass
    mass_target: float | None = None
    mass_measured: float | None = None
    concentration_mg_per_ml: float | None = None
    volume: float | None = None


@dataclass
class DispersingAgent:
    """Single dispersing-agent instance.

    target_disp_fraction (Wd,t): target dispersing-agent weight fraction relative to the total
        ceramic content in the final resin.
    """

    perm_id: str | None = None
    name: str | None = None
    target_disp_fraction: float | None = None
    current_disp_fraction: float | None = None  # Wd,current, derived from the ceramics
    mass_to_add: float | None = None
    concentration_mg_per_ml: float | None = None
    volume: float | None = None


@dataclass
class Formulation:
    """Source of truth for formulation data. Supports a dynamic number of ceramics, binders,
    and photo-initiators; solvent, additive, and dispersing agent are limited to one instance.

    binder_to_ceramic_ratio: a single, formulation-wide target — the ratio of total binder mass
        to total ceramic mass (mc,total). E.g. 0.2 means 0.2 g of binder per 1 g of ceramic
        (total, before splitting across individual binders by their own percentage). NOT the
        same as any ceramic.ceramic_fraction / Wc,i (which only splits the ceramic blend among
        multiple ceramics). PI/additive/dispersing agent are sized relative to binder mass
        separately, not part of this ratio. This is a real user input (entered on the Binder
        tab), needed to size total binder mass from mc,total:
        total_binder_mass = mc,total * binder_to_ceramic_ratio.
    """

    ceramics: list[Ceramic] = field(default_factory=list)
    binders: list[Binder] = field(default_factory=list)
    photo_initiators: list[PhotoInitiator] = field(default_factory=list)
    solvent: Solvent | None = None
    additive: Additive | None = None
    dispersing_agent: DispersingAgent | None = None
    binder_to_ceramic_ratio: float | None = None
