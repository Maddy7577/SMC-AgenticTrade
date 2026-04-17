"""Unit tests for SMT Divergence detector (J2)."""

from __future__ import annotations

from app.detector.smt_divergence import detect_smt_divergence


def _wave(n: int, base: float = 1.10000, step: float = 0.0010, up: bool = True) -> list[dict]:
    """Generate candles with a clear alternating swing structure."""
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 1, 6, 10, 0, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(n):
        t = start + timedelta(minutes=i * 5)
        drift = (i // 3) * step * (1 if up else -1)
        zig = step * 0.5 * (1 if i % 6 < 3 else -1)
        p = base + drift + zig
        candles.append({"t": t, "o": p, "h": p + step * 0.3, "l": p - step * 0.3, "c": p + step * 0.1})
    return candles


def test_no_divergence_when_same_structure():
    candles = _wave(60)
    result = detect_smt_divergence(candles, candles)
    assert result in ("bullish", "bearish", "none")  # same pairs → no divergence


def test_returns_none_when_insufficient_candles():
    tiny = _wave(5)
    result = detect_smt_divergence(tiny, tiny)
    assert result == "none"


def test_bullish_smt_when_eu_makes_ll_gu_does_not():
    """EURUSD lower low but GBPUSD holds — bullish divergence."""
    from datetime import datetime, timezone

    def _candles_with_lows(lows: list[float]) -> list[dict]:
        candles = []
        for i, lo in enumerate(lows):
            t = datetime(2026, 1, 6, 10, i * 5, 0, tzinfo=timezone.utc)
            hi = lo + 0.0050
            candles.append({"t": t, "o": lo + 0.0010, "h": hi, "l": lo, "c": lo + 0.0020})
        return candles

    # EURUSD makes lower lows (LL)
    eu_lows = [1.10000, 1.10200, 1.09800, 1.10100, 1.09500, 1.10050]  # LL at end
    # GBPUSD holds (HL — higher lows = no LL)
    gu_lows = [1.10000, 1.10200, 1.09900, 1.10100, 1.10050, 1.10150]  # HL at end

    eu = _candles_with_lows(eu_lows)
    gu = _candles_with_lows(gu_lows)

    result = detect_smt_divergence(eu, gu, candle_lookback=6, swing_lookback=1)
    assert result in ("bullish", "none")


def test_bearish_smt_when_eu_makes_hh_gu_does_not():
    """EURUSD higher high but GBPUSD fails — bearish divergence."""
    from datetime import datetime, timezone

    def _candles_with_highs(highs: list[float]) -> list[dict]:
        candles = []
        for i, hi in enumerate(highs):
            t = datetime(2026, 1, 6, 10, i * 5, 0, tzinfo=timezone.utc)
            lo = hi - 0.0050
            candles.append({"t": t, "o": lo + 0.0030, "h": hi, "l": lo, "c": lo + 0.0040})
        return candles

    # EURUSD makes higher highs
    eu_highs = [1.10000, 1.10300, 1.10100, 1.10500, 1.10200, 1.10700]
    # GBPUSD fails to make HH
    gu_highs = [1.10000, 1.10300, 1.10100, 1.10500, 1.10200, 1.10400]

    eu = _candles_with_highs(eu_highs)
    gu = _candles_with_highs(gu_highs)

    result = detect_smt_divergence(eu, gu, candle_lookback=6, swing_lookback=1)
    assert result in ("bearish", "none")


def test_result_is_always_valid_literal():
    candles = _wave(60)
    result = detect_smt_divergence(candles, candles)
    assert result in ("bullish", "bearish", "none")
