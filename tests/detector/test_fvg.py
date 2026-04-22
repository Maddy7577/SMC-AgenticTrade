"""Unit tests for FVG detector (J2), including CE-test history (FR-C2-03)."""

from __future__ import annotations

import pytest

from app.detector.fvg import FVG, detect_fvgs, update_fvg_ce_tests, update_fvg_state
from tests.fixtures.scenarios import (
    bearish_fvg_scenario,
    bullish_fvg_scenario,
    fvg_too_small_scenario,
)

# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------

def test_bullish_fvg_detected():
    candles = bullish_fvg_scenario()
    fvgs = detect_fvgs(candles)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.direction == "bullish"
    assert fvg.size_pips >= 5.0


def test_bullish_fvg_geometry():
    candles = bullish_fvg_scenario()
    fvg = detect_fvgs(candles)[0]
    c1, c3 = candles[0], candles[2]
    assert fvg.bottom == pytest.approx(c1["h"])
    assert fvg.top == pytest.approx(c3["l"])
    assert fvg.midpoint == pytest.approx((c1["h"] + c3["l"]) / 2, abs=1e-6)


def test_bearish_fvg_detected():
    candles = bearish_fvg_scenario()
    fvgs = detect_fvgs(candles)
    assert len(fvgs) == 1
    assert fvgs[0].direction == "bearish"
    assert fvgs[0].size_pips >= 5.0


def test_bearish_fvg_geometry():
    candles = bearish_fvg_scenario()
    fvg = detect_fvgs(candles)[0]
    c1, c3 = candles[0], candles[2]
    assert fvg.top == pytest.approx(c1["l"])
    assert fvg.bottom == pytest.approx(c3["h"])


def test_fvg_below_min_pips_not_detected():
    candles = fvg_too_small_scenario()
    # Ensure the scenario actually has a gap smaller than 5 pips
    c1, c3 = candles[0], candles[2]
    from config.instruments import price_to_pips
    gap_pips = price_to_pips(c3["l"] - c1["h"]) if c3["l"] > c1["h"] else price_to_pips(c1["l"] - c3["h"])
    assert gap_pips < 5.0, f"Scenario gap should be < 5 pips, got {gap_pips:.1f}"
    fvgs = detect_fvgs(candles)
    assert fvgs == []


def test_no_fvg_in_flat_candles(flat_candles_20):
    fvgs = detect_fvgs(flat_candles_20)
    assert fvgs == []


def test_fewer_than_3_candles_returns_empty():
    from tests.fixtures.scenarios import bullish_fvg_scenario
    fvgs = detect_fvgs(bullish_fvg_scenario()[:2])
    assert fvgs == []


# ---------------------------------------------------------------------------
# State machine tests
# ---------------------------------------------------------------------------

def _make_fvg(bottom: float = 1.10050, top: float = 1.10100, direction: str = "bullish") -> FVG:
    return FVG(
        id="test_fvg",
        instrument="EUR_USD",
        timeframe="M1",
        c1_index=0,
        c1_t="2026-01-01T10:00:00",
        c3_t="2026-01-01T10:02:00",
        top=top,
        bottom=bottom,
        midpoint=(bottom + top) / 2,
        direction=direction,  # type: ignore[arg-type]
    )


def test_bullish_fvg_retested():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    # Candle low enters the gap (between bottom and top)
    candle = {"o": 1.10120, "h": 1.10130, "l": 1.10060, "c": 1.10110}
    updated = update_fvg_state(fvg, candle)
    assert updated.state == "retested"


def test_bullish_fvg_fully_filled():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    # Candle low goes through or below bottom
    candle = {"o": 1.10120, "h": 1.10130, "l": 1.10040, "c": 1.10080}
    updated = update_fvg_state(fvg, candle)
    assert updated.state == "fully_filled"


def test_bullish_fvg_inverted():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    # Body opens above top, closes below bottom = inverted
    candle = {"o": 1.10120, "h": 1.10130, "l": 1.10030, "c": 1.10030}
    updated = update_fvg_state(fvg, candle)
    assert updated.state == "inverted"


def test_bearish_fvg_retested():
    fvg = _make_fvg(1.10050, 1.10100, "bearish")
    # Candle high enters the gap
    candle = {"o": 1.10030, "h": 1.10060, "l": 1.10010, "c": 1.10035}
    updated = update_fvg_state(fvg, candle)
    assert updated.state == "retested"


def test_bearish_fvg_fully_filled():
    fvg = _make_fvg(1.10050, 1.10100, "bearish")
    candle = {"o": 1.10030, "h": 1.10110, "l": 1.10010, "c": 1.10080}
    updated = update_fvg_state(fvg, candle)
    assert updated.state == "fully_filled"


def test_terminal_states_are_final():
    """Once fully_filled or inverted, further candles don't change state."""
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    fvg.state = "fully_filled"
    candle = {"o": 1.10000, "h": 1.10200, "l": 1.09900, "c": 1.10000}
    updated = update_fvg_state(fvg, candle)
    assert updated.state == "fully_filled"


def test_fvg_id_format():
    candles = bullish_fvg_scenario()
    fvg = detect_fvgs(candles, instrument="EUR_USD", timeframe="M5")[0]
    assert fvg.id.startswith("EUR_USD_M5_")


# ---------------------------------------------------------------------------
# CE-test history tests (FR-C2-03)
# ---------------------------------------------------------------------------

def test_ce_test_respected_bullish():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    # Candle enters gap but closes above CE (respected)
    candle = {"o": 1.10120, "h": 1.10130, "l": 1.10060, "c": 1.10090, "t": "2026-01-01T10:03:00"}
    result = update_fvg_ce_tests([fvg], candle)
    assert len(result[0].tests) == 1
    assert result[0].tests[0]["respected"] is True


def test_ce_test_failed_bullish():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    # Close below CE (midpoint = 1.10075) = failed
    candle = {"o": 1.10090, "h": 1.10100, "l": 1.10050, "c": 1.10060, "t": "2026-01-01T10:03:00"}
    result = update_fvg_ce_tests([fvg], candle)
    assert len(result[0].tests) == 1
    assert result[0].tests[0]["respected"] is False


def test_ce_test_not_recorded_outside_zone():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    # Candle doesn't touch the FVG zone at all
    candle = {"o": 1.11000, "h": 1.11100, "l": 1.10900, "c": 1.11000, "t": "2026-01-01T10:03:00"}
    result = update_fvg_ce_tests([fvg], candle)
    assert len(result[0].tests) == 0


def test_ce_test_not_recorded_for_fully_filled():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    fvg.state = "fully_filled"
    candle = {"o": 1.10070, "h": 1.10090, "l": 1.10060, "c": 1.10075, "t": "2026-01-01T10:03:00"}
    result = update_fvg_ce_tests([fvg], candle)
    assert len(result[0].tests) == 0


def test_multiple_ce_tests_accumulate():
    fvg = _make_fvg(1.10050, 1.10100, "bullish")
    for i in range(3):
        candle = {"o": 1.10120, "h": 1.10130, "l": 1.10060, "c": 1.10085, "t": f"2026-01-01T10:0{i}:00"}
        update_fvg_ce_tests([fvg], candle)
    assert len(fvg.tests) == 3
