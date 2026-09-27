"""Advise agent: reserve depletion math and the survives flag."""

from backend.agents.advise import simulate_reserve
from backend.schemas import Reserve


def test_returns_contract_reserve():
    r = simulate_reserve(buffer_days=9, supply_gap_pct=40, refill_days=22)
    assert isinstance(r, Reserve)


def test_depletion_math():
    # 9 days of full cover, drawing 40% of a day per day -> lasts 22.5 days.
    r = simulate_reserve(buffer_days=9, supply_gap_pct=40, refill_days=22)
    assert r.drawdown_per_day == 0.4
    assert r.days_cover == 22.5
    assert r.survives_until_refill is True


def test_does_not_survive_when_refill_too_far():
    r = simulate_reserve(buffer_days=9, supply_gap_pct=65, refill_days=22)
    assert r.survives_until_refill is False


def test_zero_gap_no_drawdown():
    r = simulate_reserve(buffer_days=9, supply_gap_pct=0, refill_days=30)
    assert r.drawdown_per_day == 0.0
    assert r.days_cover == 9
    assert r.survives_until_refill is True


def test_gap_clamped_above_100():
    # a transient 120% gap must not crash — it clamps to 100%.
    r = simulate_reserve(buffer_days=9, supply_gap_pct=120, refill_days=1)
    assert r.drawdown_per_day == 1.0
    assert r.days_cover == 9
