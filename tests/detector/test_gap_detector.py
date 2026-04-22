"""Tests for gap_detector.py (FR-C2-05)."""

from datetime import datetime, timedelta, timezone

from app.detector.gap_detector import detect_gaps, update_gap_fill_status


def _c(offset_h, o, h, l, c):
    t = datetime(2026, 3, 21, 8, 0, 0, tzinfo=timezone.utc) + timedelta(hours=offset_h)
    return {"o": o, "h": h, "l": l, "c": c, "t": t, "v": 100}


def test_gap_up_detected():
    candles = [
        _c(0, 1.10000, 1.10100, 1.09900, 1.10050),
        _c(1, 1.10200, 1.10300, 1.10200, 1.10250),  # gap up: curr.l > prev.h
    ]
    gaps = detect_gaps(candles)
    assert len(gaps) == 1
    assert gaps[0]["direction"] == "up"
    assert gaps[0]["bottom"] == 1.10100
    assert gaps[0]["top"] == 1.10200


def test_gap_down_detected():
    candles = [
        _c(0, 1.10200, 1.10300, 1.10100, 1.10200),
        _c(1, 1.09800, 1.10000, 1.09700, 1.09800),  # gap down: curr.h < prev.l
    ]
    gaps = detect_gaps(candles)
    assert len(gaps) == 1
    assert gaps[0]["direction"] == "down"


def test_no_gap_when_candles_overlap():
    candles = [
        _c(0, 1.10000, 1.10100, 1.09900, 1.10050),
        _c(1, 1.10050, 1.10150, 1.10000, 1.10100),
    ]
    gaps = detect_gaps(candles)
    assert len(gaps) == 0


def test_session_gap_classification():
    # 30-min delta → session_gap
    t1 = datetime(2026, 3, 21, 8, 0, 0, tzinfo=timezone.utc)
    t2 = t1 + timedelta(minutes=30)
    candles = [
        {"o": 1.10000, "h": 1.10100, "l": 1.09900, "c": 1.10050, "t": t1, "v": 100},
        {"o": 1.10200, "h": 1.10300, "l": 1.10200, "c": 1.10250, "t": t2, "v": 100},
    ]
    gaps = detect_gaps(candles)
    assert gaps[0]["gap_type"] == "session_gap"


def test_weekend_gap_classification():
    # 48-hour delta → weekend_gap
    t1 = datetime(2026, 3, 21, 22, 0, 0, tzinfo=timezone.utc)
    t2 = t1 + timedelta(hours=48)
    candles = [
        {"o": 1.10000, "h": 1.10100, "l": 1.09900, "c": 1.10050, "t": t1, "v": 100},
        {"o": 1.10200, "h": 1.10300, "l": 1.10200, "c": 1.10250, "t": t2, "v": 100},
    ]
    gaps = detect_gaps(candles)
    assert gaps[0]["gap_type"] == "weekend_gap"


def test_news_gap_classification():
    # 4-hour delta → news_gap
    t1 = datetime(2026, 3, 21, 8, 0, 0, tzinfo=timezone.utc)
    t2 = t1 + timedelta(hours=4)
    candles = [
        {"o": 1.10000, "h": 1.10100, "l": 1.09900, "c": 1.10050, "t": t1, "v": 100},
        {"o": 1.10200, "h": 1.10300, "l": 1.10200, "c": 1.10250, "t": t2, "v": 100},
    ]
    gaps = detect_gaps(candles)
    assert gaps[0]["gap_type"] == "news_gap"


def test_gap_full_fill_by_body():
    candles = [
        _c(0, 1.10000, 1.10100, 1.09900, 1.10050),
        _c(1, 1.10200, 1.10300, 1.10200, 1.10250),
    ]
    gaps = detect_gaps(candles)
    assert len(gaps) == 1
    # Fill candle body goes through gap bottom (1.10100)
    fill_candle = {"o": 1.10150, "h": 1.10200, "l": 1.10080, "c": 1.10090, "t": _c(2, 0, 0, 0, 0)["t"], "v": 100}
    updated = update_gap_fill_status(gaps, fill_candle)
    assert updated[0]["fully_filled"]


def test_wick_only_gap_entry_not_filled():
    # Wick enters gap but body stays above gap top
    candles = [
        _c(0, 1.10000, 1.10100, 1.09900, 1.10050),
        _c(1, 1.10200, 1.10300, 1.10200, 1.10250),
    ]
    gaps = detect_gaps(candles)
    # Body entirely above gap, wick barely enters
    wick_only = {"o": 1.10250, "h": 1.10300, "l": 1.10150, "c": 1.10230, "t": _c(2, 0, 0, 0, 0)["t"], "v": 100}
    updated = update_gap_fill_status(gaps, wick_only)
    assert not updated[0]["fully_filled"]
