"""Tests for fibonacci.py (FR-C2-01/02)."""

from app.detector.fibonacci import compute_fib_levels


def test_bullish_levels_direction():
    levels = compute_fib_levels(swing_high=1.11000, swing_low=1.10000, direction="bullish")
    assert levels[0.0] == 1.10000
    assert levels[1.0] == 1.11000
    assert levels[0.5] == 1.10500
    assert abs(levels[0.618] - 1.10618) < 0.00002


def test_bearish_levels_direction():
    levels = compute_fib_levels(swing_high=1.11000, swing_low=1.10000, direction="bearish")
    assert levels[0.0] == 1.11000
    assert levels[1.0] == 1.10000
    assert levels[0.5] == 1.10500


def test_all_expected_levels_present():
    levels = compute_fib_levels(1.11000, 1.10000, "bullish")
    for lvl in (0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0, -0.27, -0.62):
        assert lvl in levels


def test_extension_levels_bullish():
    levels = compute_fib_levels(swing_high=1.11000, swing_low=1.10000, direction="bullish")
    # -0.27 extension should be below swing_low
    assert levels[-0.27] < 1.10000


def test_zero_or_negative_span_returns_empty():
    levels = compute_fib_levels(swing_high=1.10000, swing_low=1.10000, direction="bullish")
    assert levels == {}
    levels = compute_fib_levels(swing_high=1.09000, swing_low=1.10000, direction="bullish")
    assert levels == {}


def test_body_to_body_matches_known_swing():
    # Simulate 100-pip impulse body-to-body
    swing_low_body = 1.10000
    swing_high_body = 1.11000
    levels = compute_fib_levels(swing_high_body, swing_low_body, "bullish")
    assert abs(levels[0.618] - 1.10618) < 0.0001
    assert abs(levels[0.705] - 1.10705) < 0.0001
