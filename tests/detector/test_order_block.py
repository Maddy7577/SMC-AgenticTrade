"""Unit tests for Order Block and Breaker Block detection (J2)."""

from __future__ import annotations

import pytest

from app.detector.order_block import OrderBlock, detect_order_blocks, mark_breaker_blocks
from tests.fixtures.scenarios import order_block_bull_scenario


def test_bullish_ob_detected():
    candles = order_block_bull_scenario()
    obs = detect_order_blocks(candles)
    bull_obs = [ob for ob in obs if ob.direction == "bullish"]
    assert len(bull_obs) >= 1


def test_bullish_ob_is_bearish_candle_before_displacement():
    candles = order_block_bull_scenario()
    obs = detect_order_blocks(candles)
    bull_ob = next(ob for ob in obs if ob.direction == "bullish")
    # The OB is a bearish candle (close < open) at index 15
    ob_candle = candles[bull_ob.ob_index]
    assert ob_candle["c"] < ob_candle["o"]


def test_ob_initial_state_valid():
    candles = order_block_bull_scenario()
    obs = detect_order_blocks(candles)
    assert all(ob.valid for ob in obs)
    assert all(ob.kind == "order_block" for ob in obs)


def test_too_few_candles_returns_empty():
    from tests.fixtures.scenarios import _c
    candles = [_c(i, 1.1, 1.1 + 0.001, 1.1 - 0.001, 1.1) for i in range(10)]
    obs = detect_order_blocks(candles)
    assert obs == []


def test_ob_deduplication():
    candles = order_block_bull_scenario()
    obs = detect_order_blocks(candles)
    ob_indices = [ob.ob_index for ob in obs]
    assert len(ob_indices) == len(set(ob_indices))


def test_breaker_block_when_price_trades_through():
    candles = order_block_bull_scenario()
    obs = detect_order_blocks(candles)
    bull_ob = next(ob for ob in obs if ob.direction == "bullish")
    # Append a candle that trades through the OB low
    breach_candle = {
        "o": bull_ob.low - 0.0001,
        "h": bull_ob.low + 0.0005,
        "l": bull_ob.low - 0.0020,
        "c": bull_ob.low - 0.0015,
        "t": "2026-01-01",
    }
    all_candles = candles + [breach_candle]
    mark_breaker_blocks(obs, all_candles)
    assert bull_ob.kind == "breaker_block"
    assert bull_ob.valid is False


def test_ob_not_invalidated_without_breach():
    candles = order_block_bull_scenario()
    obs = detect_order_blocks(candles)
    mark_breaker_blocks(obs, candles)
    bull_obs = [ob for ob in obs if ob.direction == "bullish"]
    assert all(ob.valid for ob in bull_obs)
