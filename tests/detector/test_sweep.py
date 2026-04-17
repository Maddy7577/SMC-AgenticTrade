"""Unit tests for Liquidity Sweep detector (J2)."""

from __future__ import annotations

import pytest

from app.detector.sweep import SweepEvent, detect_sweeps
from tests.fixtures.scenarios import sweep_pdh_scenario


def test_bearish_pdh_sweep_detected():
    candles, daily = sweep_pdh_scenario()
    events = detect_sweeps(candles, daily_candles=daily)
    bearish = [e for e in events if e.direction == "bearish"]
    assert len(bearish) >= 1


def test_bearish_sweep_level_is_pdh():
    candles, daily = sweep_pdh_scenario()
    events = detect_sweeps(candles, daily_candles=daily)
    bearish = [e for e in events if e.direction == "bearish" and e.level_type == "pdh"]
    assert len(bearish) >= 1
    assert bearish[0].swept_level == pytest.approx(1.10200, abs=1e-5)


def test_bullish_pdl_sweep_detected():
    from tests.fixtures.scenarios import _c
    # Build scenario: price wicks below 1.09900 (PDL) then closes above
    candles = [
        _c(0,  1.09950, 1.09970, 1.09930, 1.09960),
        _c(1,  1.09960, 1.09980, 1.09870, 1.09950),  # wick below PDL, close above
    ]
    daily = [
        _c(0,  1.10000, 1.10100, 1.09900, 1.10050),  # prev day low = 1.09900
        _c(1440, 1.10050, 1.10150, 1.09950, 1.10080),
    ]
    events = detect_sweeps(candles, daily_candles=daily)
    bullish = [e for e in events if e.direction == "bullish" and e.level_type == "pdl"]
    assert len(bullish) >= 1


def test_no_sweep_when_no_wick_beyond_level():
    from tests.fixtures.scenarios import _c
    candles = [
        _c(0,  1.10100, 1.10180, 1.10080, 1.10160),  # never touches PDH
        _c(1,  1.10160, 1.10190, 1.10140, 1.10170),  # never touches PDH
    ]
    daily = [
        _c(0,  1.10000, 1.10200, 1.09900, 1.10100),
        _c(1440, 1.10100, 1.10220, 1.10050, 1.10180),
    ]
    events = detect_sweeps(candles, daily_candles=daily)
    pdh_sweeps = [e for e in events if e.level_type == "pdh"]
    assert pdh_sweeps == []


def test_eql_sweep_detected():
    """Equal lows within tolerance swept by a bullish wick."""
    from tests.fixtures.scenarios import _c
    lo = 1.10000
    candles = [
        _c(0,  1.10050, 1.10080, lo,        1.10060),
        _c(1,  1.10060, 1.10090, lo + 0.0001, 1.10070),  # EQL forms (2 lows near 1.10000)
        _c(2,  1.10070, 1.10100, lo + 0.0002, 1.10085),
        _c(3,  1.10050, 1.10080, lo,          1.10070),  # 3rd EQL candle
        _c(4,  1.10070, 1.10090, lo - 0.0010, 1.10080),  # wick below EQL, close above
    ]
    events = detect_sweeps(candles)
    eql_sweeps = [e for e in events if e.level_type == "eql"]
    assert len(eql_sweeps) >= 1


def test_sweep_wick_extreme_recorded():
    candles, daily = sweep_pdh_scenario()
    events = detect_sweeps(candles, daily_candles=daily)
    for e in events:
        assert e.wick_extreme > 0
