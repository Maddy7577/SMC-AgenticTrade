"""Average True Range (ATR) — Wilder smoothing, configurable period."""

from __future__ import annotations


def true_range(candle: dict, prev_close: float | None = None) -> float:
    high, low, close_prev = candle["h"], candle["l"], prev_close or candle["o"]
    return max(high - low, abs(high - close_prev), abs(low - close_prev))


def atr(candles: list[dict], period: int = 14) -> float | None:
    """Return ATR(period) for the last candle in the list, or None if insufficient data."""
    if len(candles) < period + 1:
        return None
    trs = [
        true_range(candles[i], candles[i - 1]["c"])
        for i in range(1, len(candles))
    ]
    # Wilder smoothing: SMA seed then EMA
    window = trs[:period]
    smoothed = sum(window) / period
    for tr in trs[period:]:
        smoothed = (smoothed * (period - 1) + tr) / period
    return smoothed


def atr_series(candles: list[dict], period: int = 14) -> list[float | None]:
    """Return ATR value aligned to each candle index (None for first period candles)."""
    if len(candles) < 2:
        return [None] * len(candles)
    trs = [None] + [true_range(candles[i], candles[i - 1]["c"]) for i in range(1, len(candles))]
    result: list[float | None] = [None] * len(candles)
    valid = [t for t in trs if t is not None]
    if len(valid) < period:
        return result
    smoothed = sum(valid[:period]) / period
    result[period] = smoothed
    for i in range(period + 1, len(candles)):
        smoothed = (smoothed * (period - 1) + (trs[i] or 0)) / period  # type: ignore[operator]
        result[i] = smoothed
    return result
