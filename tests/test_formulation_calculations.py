"""Unit tests for helpers/formulation_calculations.py.

Run from the resin-formulation-manager directory: `python -m pytest tests/`
"""

import pytest

from helpers.formulation_calculations import (
    calculate_ceramic_suspension_masses,
    calculate_dispersing_agent_addition,
    calculate_individual_ceramic_masses,
    calculate_total_ceramic_mass,
)
from helpers.formulation_model import Ceramic, DispersingAgent, Formulation


def make_ceramic(fraction, fraction_in_suspension, disp_fraction=None):
    return Ceramic(
        ceramic_fraction=fraction,
        ceramic_fraction_in_suspension=fraction_in_suspension,
        disp_fraction_in_suspension=disp_fraction,
    )


def worked_example_formulation():
    """The 3-ceramic worked example from CLAUDE.md Phase 2."""
    return Formulation(
        ceramics=[
            make_ceramic(0.50, 0.402),
            make_ceramic(0.30, 0.35),
            make_ceramic(0.20, 0.45),
        ]
    )


# --- Suspension mass calculation ---


def test_worked_example_suspension_masses():
    formulation = worked_example_formulation()
    calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.000)

    assert formulation.ceramics[0].suspension_mass == pytest.approx(1.000, abs=1e-4)
    assert formulation.ceramics[1].suspension_mass == pytest.approx(0.6891, abs=1e-4)
    assert formulation.ceramics[2].suspension_mass == pytest.approx(0.3573, abs=1e-4)


def test_worked_example_total_ceramic_mass():
    formulation = worked_example_formulation()
    mc_total = calculate_total_ceramic_mass(formulation, reference_suspension_mass=1.000)
    assert mc_total == pytest.approx(0.804, abs=1e-4)


def test_individual_ceramic_masses():
    formulation = worked_example_formulation()
    calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.000)
    calculate_individual_ceramic_masses(formulation)

    mc_total = calculate_total_ceramic_mass(formulation, reference_suspension_mass=1.000)
    assert sum(c.ceramic_mass for c in formulation.ceramics) == pytest.approx(mc_total, abs=1e-4)


def test_individual_ceramic_masses_requires_suspension_mass_first():
    formulation = worked_example_formulation()
    with pytest.raises(ValueError):
        calculate_individual_ceramic_masses(formulation)


def test_one_ceramic():
    formulation = Formulation(ceramics=[make_ceramic(1.0, 0.4)])
    calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=2.0)
    assert formulation.ceramics[0].suspension_mass == pytest.approx(2.0)

    mc_total = calculate_total_ceramic_mass(formulation, reference_suspension_mass=2.0)
    assert mc_total == pytest.approx(0.8)


def test_two_ceramics():
    formulation = Formulation(ceramics=[make_ceramic(0.6, 0.4), make_ceramic(0.4, 0.3)])
    calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.0)

    assert formulation.ceramics[0].suspension_mass == pytest.approx(1.0)
    # ms,2 = 1.0 * (0.4/0.6) * (0.4/0.3)
    assert formulation.ceramics[1].suspension_mass == pytest.approx(0.888889, abs=1e-4)


def test_arbitrary_number_of_ceramics():
    n = 5
    fraction = 1.0 / n
    formulation = Formulation(ceramics=[make_ceramic(fraction, 0.3 + 0.02 * i) for i in range(n)])
    calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.0)
    calculate_individual_ceramic_masses(formulation)

    mc_total = calculate_total_ceramic_mass(formulation, reference_suspension_mass=1.0)
    assert sum(c.ceramic_mass for c in formulation.ceramics) == pytest.approx(mc_total, abs=1e-4)
    # Reference ceramic's own suspension mass must equal the input mass exactly.
    assert formulation.ceramics[0].suspension_mass == pytest.approx(1.0)


# --- Validation ---


def test_invalid_ceramic_fraction_sum():
    formulation = Formulation(ceramics=[make_ceramic(0.5, 0.4), make_ceramic(0.4, 0.3)])
    with pytest.raises(ValueError):
        calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.0)


def test_individual_ceramic_fraction_non_positive_even_if_sum_is_one():
    # -0.2 + 0.7 + 0.5 == 1.0, but the first fraction is not positive.
    formulation = Formulation(
        ceramics=[make_ceramic(-0.2, 0.4), make_ceramic(0.7, 0.3), make_ceramic(0.5, 0.4)]
    )
    with pytest.raises(ValueError):
        calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.0)


def test_suspension_fraction_zero_or_negative():
    formulation = Formulation(ceramics=[make_ceramic(0.5, 0.0), make_ceramic(0.5, 0.3)])
    with pytest.raises(ValueError):
        calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.0)


def test_suspension_fraction_greater_than_one():
    formulation = Formulation(ceramics=[make_ceramic(0.5, 1.2), make_ceramic(0.5, 0.3)])
    with pytest.raises(ValueError):
        calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.0)


def test_invalid_reference_mass():
    formulation = worked_example_formulation()
    with pytest.raises(ValueError):
        calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=0)
    with pytest.raises(ValueError):
        calculate_total_ceramic_mass(formulation, reference_suspension_mass=-1.0)


def test_no_ceramics():
    formulation = Formulation(ceramics=[])
    with pytest.raises(ValueError):
        calculate_ceramic_suspension_masses(formulation, reference_suspension_mass=1.0)


# --- Dispersing agent ---


def dispersing_agent_formulation(target_fraction):
    formulation = worked_example_formulation()
    formulation.ceramics[0].disp_fraction_in_suspension = 0.05
    formulation.ceramics[1].disp_fraction_in_suspension = 0.04
    formulation.ceramics[2].disp_fraction_in_suspension = 0.03
    formulation.dispersing_agent = DispersingAgent(target_disp_fraction=target_fraction)
    return formulation


def test_dispersing_agent_target_above_current():
    # Wd,current = 0.5*0.05 + 0.3*0.04 + 0.2*0.03 = 0.043
    formulation = dispersing_agent_formulation(target_fraction=0.06)
    mass_to_add = calculate_dispersing_agent_addition(formulation, reference_suspension_mass=1.0)

    assert formulation.dispersing_agent.current_disp_fraction == pytest.approx(0.043)
    assert mass_to_add > 0
    assert formulation.dispersing_agent.mass_to_add == pytest.approx(mass_to_add)


def test_dispersing_agent_target_equal_current():
    formulation = dispersing_agent_formulation(target_fraction=0.043)
    mass_to_add = calculate_dispersing_agent_addition(formulation, reference_suspension_mass=1.0)
    assert mass_to_add == pytest.approx(0.0, abs=1e-9)


def test_dispersing_agent_target_below_current():
    formulation = dispersing_agent_formulation(target_fraction=0.01)
    with pytest.raises(ValueError):
        calculate_dispersing_agent_addition(formulation, reference_suspension_mass=1.0)


def test_dispersing_agent_fraction_out_of_bounds():
    formulation = dispersing_agent_formulation(target_fraction=1.5)
    with pytest.raises(ValueError):
        calculate_dispersing_agent_addition(formulation, reference_suspension_mass=1.0)

    formulation = dispersing_agent_formulation(target_fraction=0.06)
    formulation.ceramics[0].disp_fraction_in_suspension = -0.1
    with pytest.raises(ValueError):
        calculate_dispersing_agent_addition(formulation, reference_suspension_mass=1.0)


def test_dispersing_agent_missing():
    formulation = worked_example_formulation()
    with pytest.raises(ValueError):
        calculate_dispersing_agent_addition(formulation, reference_suspension_mass=1.0)
