"""Predict agent: the sourced v1.3 domino model (SPEC.md Segment 1, Phase 3).

Mirrors tests/test_recommend.py's pure-function style: run_predict is a pure,
DB-free function, so every case here is a plain input -> output assertion.
"""

from backend.agents.predict import assumptions_from_severity, run_predict
from backend.schemas import Assumptions, AssumptionEntry, PredictAgentOutput


def _entry(value, type_="fact", lo=0.0, hi=100.0, src="test fixture"):
    return AssumptionEntry(value=value, type=type_, range=(lo, hi), src=src)


def _assumptions(
    supply_lost_pct=40.0,
    buffer_days=9.0,
    price_elasticity=3.0,
    power_oil_dependence=0.015,
    gdp_oil_sensitivity=0.03,
    power_stress_multiplier=7.5,
):
    return Assumptions(
        supply_lost_pct=_entry(supply_lost_pct),
        buffer_days=_entry(buffer_days),
        price_elasticity=_entry(price_elasticity, "estimate"),
        power_oil_dependence=_entry(power_oil_dependence),
        gdp_oil_sensitivity=_entry(gdp_oil_sensitivity, "estimate"),
        power_stress_multiplier=_entry(power_stress_multiplier, "internal"),
    )


# --------------------------------------------------------------------------- #
# assumptions_from_severity: shape + sourcing tiers (unchanged from Phase 1).
# --------------------------------------------------------------------------- #


def test_assumptions_from_severity_has_all_six_typed_keys():
    a = assumptions_from_severity(0.4)
    assert isinstance(a, Assumptions)
    tiers = {
        "supply_lost_pct": "fact",
        "buffer_days": "fact",
        "price_elasticity": "estimate",
        "power_oil_dependence": "fact",
        "gdp_oil_sensitivity": "estimate",
        "power_stress_multiplier": "internal",
    }
    for field, expected_type in tiers.items():
        entry = getattr(a, field)
        assert entry.type == expected_type, field


def test_assumptions_from_severity_derives_supply_lost_from_severity():
    a = assumptions_from_severity(0.4)
    assert a.supply_lost_pct.value == 40.0
    assert a.buffer_days.value == 9.0
    assert a.price_elasticity.value == 3.0


def test_assumptions_from_severity_clamps_out_of_range_severity():
    a = assumptions_from_severity(1.5)  # shouldn't happen, but never crash/overflow
    assert a.supply_lost_pct.value == 100.0


# --------------------------------------------------------------------------- #
# run_predict: the corrected, real domino chain (F3/F15/F20).
# --------------------------------------------------------------------------- #


def test_run_predict_at_default_severity_0_4():
    """SPEC.md Phase 3's worked example: gap=40, price_rise=12, gdp_delta=-0.36,
    power_stress=4.5, run_rate=70 -- replaces the old stub's -0.792/0.0."""

    out = run_predict(assumptions_from_severity(0.4))
    assert isinstance(out, PredictAgentOutput)
    assert out.impact.supply_gap_pct == 40.0
    assert out.impact.price_rise_pct == 12.0
    assert out.impact.gdp_delta_pct == -0.36
    assert out.impact.power_stress_pct == 4.5
    assert out.impact.refinery_runrate_pct == 70.0


def test_gdp_delta_uses_sourced_coefficient_not_hardcoded_0066():
    base = run_predict(_assumptions(gdp_oil_sensitivity=0.03)).impact.gdp_delta_pct
    changed = run_predict(_assumptions(gdp_oil_sensitivity=0.05)).impact.gdp_delta_pct
    assert base == -0.36
    assert changed == -0.6
    assert changed != base
    # never the old v1.0 magic number's result (12 * 0.066 = 0.792)
    assert round(abs(base), 3) != 0.792


def test_power_stress_scales_with_all_three_inputs():
    baseline = run_predict(_assumptions()).impact.power_stress_pct
    assert baseline == 4.5

    higher_gap = run_predict(_assumptions(supply_lost_pct=80.0)).impact.power_stress_pct
    assert higher_gap == 9.0
    assert higher_gap > baseline

    higher_dependence = run_predict(
        _assumptions(power_oil_dependence=0.02)
    ).impact.power_stress_pct
    assert higher_dependence == 6.0
    assert higher_dependence > baseline

    higher_multiplier = run_predict(
        _assumptions(power_stress_multiplier=10.0)
    ).impact.power_stress_pct
    assert higher_multiplier == 6.0
    assert higher_multiplier > baseline


def test_power_stress_no_longer_a_zero_placeholder():
    out = run_predict(assumptions_from_severity(0.4))
    assert out.impact.power_stress_pct != 0.0


# --------------------------------------------------------------------------- #
# Clamping: schema won't bound these, so run_predict must (SPEC.md decision #11).
# --------------------------------------------------------------------------- #


def test_price_rise_pct_clamped_to_100():
    out = run_predict(_assumptions(supply_lost_pct=100.0, price_elasticity=50.0))
    assert out.impact.price_rise_pct == 100.0


def test_gdp_delta_pct_clamped_to_minus_50():
    out = run_predict(
        _assumptions(supply_lost_pct=100.0, price_elasticity=50.0, gdp_oil_sensitivity=5.0)
    )
    assert out.impact.gdp_delta_pct == -50.0


def test_power_stress_pct_clamped_to_100():
    out = run_predict(
        _assumptions(
            supply_lost_pct=100.0, power_oil_dependence=0.02, power_stress_multiplier=1000.0
        )
    )
    assert out.impact.power_stress_pct == 100.0


def test_supply_gap_and_runrate_stay_clamped_0_100():
    out = run_predict(_assumptions(supply_lost_pct=150.0))
    assert out.impact.supply_gap_pct == 100.0
    assert 0.0 <= out.impact.refinery_runrate_pct <= 100.0


# --------------------------------------------------------------------------- #
# Purity: no DB, no mutation, deterministic.
# --------------------------------------------------------------------------- #


def test_run_predict_is_pure_and_deterministic():
    a = assumptions_from_severity(0.4)
    first = run_predict(a).model_dump(mode="json")
    second = run_predict(a).model_dump(mode="json")
    assert first == second
    # the input object itself is untouched
    assert a.supply_lost_pct.value == 40.0


def test_run_predict_echoes_input_assumptions_unchanged():
    a = _assumptions(price_elasticity=6.0)
    out = run_predict(a)
    assert out.assumptions == a
