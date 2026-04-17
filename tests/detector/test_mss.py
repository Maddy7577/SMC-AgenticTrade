"""Unit tests for MSS / CHoCH detector (J2)."""

from __future__ import annotations

import pytest

from app.detector.mss import detect_mss, latest_mss
from tests.fixtures.scenarios import mss_bearish_scenario, mss_bullish_scenario


def test_bullish_mss_detected():
    candles = mss_bullish_scenario()
    events = detect_mss(candles, lookback=2)
    bullish = [e for e in events if e.direction == "bullish"]
    assert len(bullish) >= 1


def test_bullish_mss_last_event_is_break():
    candles = mss_bullish_scenario()
    mss = latest_mss(candles, lookback=2)
    assert mss is not None
    assert mss.direction == "bullish"
    assert mss.displacement > 0


def test_bearish_mss_detected():
    candles = mss_bearish_scenario()
    events = detect_mss(candles, lookback=2)
    bearish = [e for e in events if e.direction == "bearish"]
    assert len(bearish) >= 1


def test_bearish_mss_displacement_positive():
    candles = mss_bearish_scenario()
    events = [e for e in detect_mss(candles, lookback=2) if e.direction == "bearish"]
    assert all(e.displacement > 0 for e in events)


def test_flat_candles_no_mss(flat_candles_20):
    events = detect_mss(flat_candles_20, lookback=2)
    assert events == []


def test_latest_mss_none_when_no_events(flat_candles_20):
    assert latest_mss(flat_candles_20, lookback=2) is None


def test_mss_broken_level_is_swing_price():
    candles = mss_bullish_scenario()
    mss = latest_mss(candles, lookback=2)
    assert mss is not None
    # broken_level should be the swing high price from the scenario
    # swing high of scenario is 1.10050 + 0.0050 = 1.10050
    assert mss.broken_level > 1.10000
