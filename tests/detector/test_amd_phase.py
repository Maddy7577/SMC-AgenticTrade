"""Tests for amd_phase.py (FR-C2-06)."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.detector.amd_phase import detect_manipulation_event, get_amd_phase

IST = ZoneInfo("Asia/Kolkata")


def _ist(h, m):
    """Create UTC datetime corresponding to IST h:m."""
    import datetime as dt
    t_ist = dt.datetime(2026, 3, 19, h, m, 0, tzinfo=IST)
    return t_ist.astimezone(timezone.utc)


def _c(o, h, l, c, offset=0):
    t = datetime(2026, 3, 19, 10, offset, 0, tzinfo=timezone.utc)
    return {"o": o, "h": h, "l": l, "c": c, "t": t, "v": 100}


def test_accumulation_phase():
    t = _ist(8, 0)  # 08:00 IST = accumulation
    phase = get_amd_phase(t, 1.10100, 1.09900, [], "neutral")
    assert phase == "Accumulation"


def test_distribution_phase():
    t = _ist(17, 0)  # 17:00 IST = distribution
    phase = get_amd_phase(t, 1.10100, 1.09900, [], "neutral")
    assert phase == "Distribution"


def test_unknown_phase_late_night():
    t = _ist(23, 0)  # 23:00 IST = outside all windows
    phase = get_amd_phase(t, 1.10100, 1.09900, [], "neutral")
    assert phase == "Unknown"


def test_manipulation_detected_bullish_bias():
    # Bullish bias: expect bearish sweep of asian high
    candles = [
        _c(1.10050, 1.10200, 1.10000, 1.10060),  # sweeps above asian high 1.10100, closes below
    ]
    event = detect_manipulation_event(candles, asian_high=1.10100, asian_low=1.09900, htf_bias="bullish")
    assert event is not None
    assert event["direction"] == "bearish_sweep"
    assert event["manipulation_extreme"] > 1.10100


def test_no_manipulation_when_no_sweep():
    candles = [_c(1.10050, 1.10080, 1.10020, 1.10060)]
    event = detect_manipulation_event(candles, asian_high=1.10100, asian_low=1.09900, htf_bias="bullish")
    assert event is None


def test_manipulation_phase_upgrade():
    t = _ist(13, 0)
    candles = [_c(1.10050, 1.10200, 1.10000, 1.10060)]
    phase = get_amd_phase(t, 1.10100, 1.09900, candles, "bullish")
    assert phase == "Manipulation"
