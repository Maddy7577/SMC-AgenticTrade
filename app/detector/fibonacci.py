"""Fibonacci retracement and extension levels using body-to-body measurement (FR-C2-01/02)."""

from __future__ import annotations

_LEVELS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0, -0.27, -0.62)


def compute_fib_levels(
    swing_high: float,
    swing_low: float,
    direction: str,
) -> dict[float, float]:
    """Return fib levels keyed by level float, valued at price.

    Uses body-to-body (open/close) swing points, not wick extremes.
    Bullish: 0.0 = swing_low, 1.0 = swing_high.
    Bearish: 0.0 = swing_high, 1.0 = swing_low.
    """
    diff = swing_high - swing_low
    if diff <= 0:
        return {}
    result: dict[float, float] = {}
    for lvl in _LEVELS:
        if direction == "bullish":
            result[lvl] = round(swing_low + lvl * diff, 5)
        else:
            result[lvl] = round(swing_high - lvl * diff, 5)
    return result
