"""Unit tests for swing high/low detection (J2)."""

from __future__ import annotations

import pytest

from app.detector.swings import detect_swings, last_swing_high, last_swing_low
from tests.fixtures.scenarios import swing_high_low_scenario


def test_swing_high_detected():
    candles = swing_high_low_scenario()
    swings = detect_swings(candles, lookback=2)
    highs = [s for s in swings if s["kind"] == "high"]
    assert len(highs) >= 1
    # The peak at index 12 has h = base + 0.0090 = 1.109 — highest in the series
    top_high = max(highs, key=lambda s: s["price"])
    assert top_high["price"] == pytest.approx(1.109, abs=1e-4)


def test_swing_low_detected():
    candles = swing_high_low_scenario()
    swings = detect_swings(candles, lookback=2)
    lows = [s for s in swings if s["kind"] == "low"]
    assert len(lows) >= 1
    # Swing low at index 18 has l=1.09980
    bottom_low = min(lows, key=lambda s: s["price"])
    assert bottom_low["price"] < 1.10000


def test_too_few_candles_for_lookback():
    candles = swing_high_low_scenario()[:3]
    swings = detect_swings(candles, lookback=5)
    assert swings == []


def test_last_swing_high_returns_latest():
    candles = swing_high_low_scenario()
    sh = last_swing_high(candles, lookback=2)
    assert sh is not None
    assert sh["kind"] == "high"


def test_last_swing_low_returns_latest():
    candles = swing_high_low_scenario()
    sl = last_swing_low(candles, lookback=2)
    assert sl is not None
    assert sl["kind"] == "low"


def test_flat_candles_no_swings(flat_candles_20):
    # All candles identical → no strict swing extremes
    swings = detect_swings(flat_candles_20, lookback=2)
    assert swings == []


def test_swing_points_sorted_by_index():
    candles = swing_high_low_scenario()
    swings = detect_swings(candles, lookback=2)
    indices = [s["index"] for s in swings]
    assert indices == sorted(indices)
