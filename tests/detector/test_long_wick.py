"""Tests for long_wick_classifier.py (FR-C2-04)."""

from app.detector.long_wick_classifier import classify_wick


def _c(o, h, l, c):
    return {"o": o, "h": h, "l": l, "c": c, "t": "2026-01-01T10:00:00", "v": 100}


def test_bullish_rejection_qualifies():
    # Long lower wick: body 5 pips, lower wick 15 pips
    c = _c(1.10050, 1.10060, 1.09900, 1.10055)
    result = classify_wick(c)
    assert result is not None
    assert result["type"] == "bullish_rejection"
    assert result["ratio"] >= 2.0


def test_bearish_rejection_qualifies():
    # Long upper wick: body 5 pips, upper wick 20 pips
    c = _c(1.10050, 1.10250, 1.10040, 1.10060)
    result = classify_wick(c)
    assert result is not None
    assert result["type"] == "bearish_rejection"
    assert result["ratio"] >= 2.0


def test_balanced_candle_returns_none():
    # Nearly equal wicks — no dominant wick
    c = _c(1.10050, 1.10110, 1.09990, 1.10050)
    result = classify_wick(c)
    assert result is None


def test_doji_returns_none():
    # Body = 0 (doji)
    c = _c(1.10050, 1.10080, 1.10020, 1.10050)
    result = classify_wick(c)
    assert result is None


def test_large_body_no_wick_returns_none():
    # Big bull candle, tiny wicks
    c = _c(1.10000, 1.10201, 1.09999, 1.10200)
    result = classify_wick(c)
    assert result is None


def test_wick_pips_populated():
    c = _c(1.10050, 1.10060, 1.09900, 1.10055)
    result = classify_wick(c)
    assert result is not None
    assert result["wick_pips"] > 0
    assert result["body_pips"] > 0
