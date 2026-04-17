"""Unit tests for HTF bias detection (J2)."""

from __future__ import annotations

from app.detector.htf_bias import _candles_bias, compute_htf_bias


def _staircase_candles(n_waves: int = 4, base: float = 1.10000, step: float = 0.0020, up: bool = True) -> list[dict]:
    """Generate explicit HH+HL (up) or LH+LL (down) staircase swing structure.

    Each wave is 9 candles: 3 rising to peak, 1 peak, 3 falling to trough, 1 trough, 1 transition.
    Successive peaks/troughs are higher (up=True) or lower (up=False), ensuring
    HH+HL or LH+LL at lookback=3.
    """
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    t = start

    def _c(price, h_extra=0.0, l_extra=0.0):
        nonlocal t
        c = {"t": t, "o": price, "h": price + h_extra + step * 0.2,
             "l": price - l_extra - step * 0.2, "c": price + step * 0.1}
        t = t + timedelta(hours=1)
        return c

    for wave in range(n_waves):
        drift = wave * step * (1 if up else -1)
        peak = base + drift + step
        trough = base + drift

        # 3 approach candles (below peak)
        candles.append(_c(trough + step * 0.2))
        candles.append(_c(trough + step * 0.5))
        candles.append(_c(trough + step * 0.8))
        # Peak candle
        candles.append(_c(peak, h_extra=step * 0.3))
        # 3 descent candles
        candles.append(_c(trough + step * 0.8))
        candles.append(_c(trough + step * 0.5))
        candles.append(_c(trough + step * 0.2))
        # Trough candle
        candles.append(_c(trough, l_extra=step * 0.3))
        # Transition
        candles.append(_c(trough + step * 0.3))

    return candles


def _trending_candles(n: int, step: float = 0.0010, base: float = 1.10000, up: bool = True) -> list[dict]:
    return _staircase_candles(n_waves=max(n // 9, 4), base=base, step=step, up=up)


def _choppy_candles(n: int) -> list[dict]:
    """Alternating candles — no clear trend."""
    from datetime import datetime, timezone
    candles = []
    base = 1.10000
    for i in range(n):
        t = datetime(2026, 1, 2, 10, i, 0, tzinfo=timezone.utc)
        sign = 1 if i % 2 == 0 else -1
        p = base + sign * 0.0005
        candles.append({"t": t, "o": base, "h": p + 0.0002, "l": p - 0.0002, "c": p})
    return candles


def test_both_neutral_returns_neutral():
    choppy = _choppy_candles(10)
    result = compute_htf_bias(choppy, choppy)
    assert result == "neutral"


def test_insufficient_candles_returns_neutral():
    tiny = _trending_candles(5, up=True)
    result = compute_htf_bias(tiny, tiny)
    assert result == "neutral"


def test_agreeing_bias_returns_that_bias():
    up_candles = _staircase_candles(n_waves=5, step=0.0020, up=True)
    result = compute_htf_bias(up_candles, up_candles, lookback=3)
    assert result == "bullish"


def test_d1_tiebreaks_when_h4_neutral():
    up_candles = _staircase_candles(n_waves=5, step=0.0020, up=True)
    neutral_h4 = _choppy_candles(45)
    result = compute_htf_bias(up_candles, neutral_h4, lookback=3)
    assert result in ("bullish", "neutral")


def test_candles_bias_bullish():
    candles = _staircase_candles(n_waves=5, step=0.0020, up=True)
    result = _candles_bias(candles, lookback=3)
    assert result == "bullish"


def test_candles_bias_bearish():
    candles = _staircase_candles(n_waves=5, step=0.0020, up=False)
    result = _candles_bias(candles, lookback=3)
    assert result == "bearish"
