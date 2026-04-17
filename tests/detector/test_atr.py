"""Unit tests for ATR calculation (J2)."""

from __future__ import annotations

import pytest

from app.detector.atr import atr, atr_series, true_range


def _candle(o=1.1, h=1.105, l=1.095, c=1.102, prev_c=None):
    return {"o": o, "h": h, "l": l, "c": c}


def _uniform_candles(n: int, body: float = 0.001) -> list[dict]:
    candles = []
    for i in range(n):
        base = 1.10000 + i * 0.00001
        candles.append({"o": base, "h": base + body, "l": base - body, "c": base + body * 0.5})
    return candles


# ---------------------------------------------------------------------------
# true_range
# ---------------------------------------------------------------------------

def test_true_range_simple():
    c = {"o": 1.10000, "h": 1.10100, "l": 1.09900, "c": 1.10050}
    tr = true_range(c, prev_close=1.10000)
    assert tr == pytest.approx(0.00200, abs=1e-6)  # h - l = 0.002


def test_true_range_uses_prev_close_gap():
    c = {"o": 1.10100, "h": 1.10200, "l": 1.10090, "c": 1.10150}
    # prev_close well below l — gap dominates
    tr = true_range(c, prev_close=1.09500)
    assert tr == pytest.approx(1.10200 - 1.09500, abs=1e-6)


def test_true_range_no_prev_close_uses_open():
    c = {"o": 1.10000, "h": 1.10100, "l": 1.09900, "c": 1.10050}
    tr = true_range(c)
    assert tr > 0


# ---------------------------------------------------------------------------
# atr
# ---------------------------------------------------------------------------

def test_atr_insufficient_data():
    candles = _uniform_candles(5)
    result = atr(candles, period=14)
    assert result is None


def test_atr_returns_float_with_enough_data():
    candles = _uniform_candles(30)
    result = atr(candles, period=14)
    assert result is not None
    assert result > 0


def test_atr_stable_candles_roughly_matches_body():
    """With uniform candles of constant size, ATR should approximate 2× body."""
    body = 0.0010
    candles = _uniform_candles(30, body=body)
    result = atr(candles, period=14)
    assert result is not None
    # total range = 2*body; ATR should be near that
    assert result == pytest.approx(2 * body, rel=0.1)


# ---------------------------------------------------------------------------
# atr_series
# ---------------------------------------------------------------------------

def test_atr_series_length_matches_candles():
    candles = _uniform_candles(20)
    series = atr_series(candles, period=14)
    assert len(series) == len(candles)


def test_atr_series_first_period_candles_are_none():
    candles = _uniform_candles(20)
    series = atr_series(candles, period=14)
    # Indices 0 through period-1 should be None
    assert all(v is None for v in series[:14])


def test_atr_series_post_period_not_none():
    candles = _uniform_candles(20)
    series = atr_series(candles, period=14)
    assert series[14] is not None


def test_atr_series_too_few_candles():
    candles = _uniform_candles(5)
    series = atr_series(candles, period=14)
    assert all(v is None for v in series)
