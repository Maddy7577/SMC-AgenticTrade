"""Swing high / low detection.

A swing high at index i requires: candle[i].h > candle[j].h for all j in
[i-lookback, i+lookback] (excluding i itself). Equivalent for swing lows.
Returns the index within the supplied candle list.
"""

from __future__ import annotations

from typing import TypedDict

from config.settings import SWING_LOOKBACK


class SwingPoint(TypedDict):
    index: int
    t: str
    price: float
    kind: str  # 'high' or 'low'


def detect_swings(
    candles: list[dict],
    lookback: int = SWING_LOOKBACK,
) -> list[SwingPoint]:
    n = len(candles)
    results: list[SwingPoint] = []
    for i in range(lookback, n - lookback):
        h = candles[i]["h"]
        l = candles[i]["l"]

        is_sh = all(candles[j]["h"] < h for j in range(i - lookback, i + lookback + 1) if j != i)
        is_sl = all(candles[j]["l"] > l for j in range(i - lookback, i + lookback + 1) if j != i)

        if is_sh:
            results.append(SwingPoint(index=i, t=str(candles[i]["t"]), price=h, kind="high"))
        if is_sl:
            results.append(SwingPoint(index=i, t=str(candles[i]["t"]), price=l, kind="low"))

    return sorted(results, key=lambda x: x["index"])


def last_swing_high(candles: list[dict], lookback: int = SWING_LOOKBACK) -> SwingPoint | None:
    swings = detect_swings(candles, lookback)
    highs = [s for s in swings if s["kind"] == "high"]
    return highs[-1] if highs else None


def last_swing_low(candles: list[dict], lookback: int = SWING_LOOKBACK) -> SwingPoint | None:
    swings = detect_swings(candles, lookback)
    lows = [s for s in swings if s["kind"] == "low"]
    return lows[-1] if lows else None
