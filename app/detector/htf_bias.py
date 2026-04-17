"""HTF Bias — derived from D1 and H4 Break of Structure sequence (FR-C-10).

Bias = 'bullish' when D1 shows HH+HL sequence (higher highs + higher lows)
Bias = 'bearish' when D1 shows LH+LL sequence
Bias = 'neutral' when mixed or insufficient data

Cross-confirmation: if D1 and H4 disagree, we return 'neutral'.
"""

from __future__ import annotations

from typing import Literal

from app.detector.swings import detect_swings

HTFBias = Literal["bullish", "bearish", "neutral"]


def compute_htf_bias(
    daily_candles: list[dict],
    h4_candles: list[dict],
    lookback: int = 10,
) -> HTFBias:
    d1_bias = _candles_bias(daily_candles, lookback)
    h4_bias = _candles_bias(h4_candles, lookback)

    if d1_bias == "neutral" and h4_bias == "neutral":
        return "neutral"
    if d1_bias == h4_bias:
        return d1_bias
    # Disagreement — use the higher timeframe (D1) as tiebreaker
    return d1_bias if d1_bias != "neutral" else h4_bias


def _candles_bias(candles: list[dict], lookback: int) -> HTFBias:
    if len(candles) < lookback * 2:
        return "neutral"
    swings = detect_swings(candles, lookback)
    highs = [s["price"] for s in swings if s["kind"] == "high"]
    lows = [s["price"] for s in swings if s["kind"] == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return "neutral"

    hh = highs[-1] > highs[-2]
    hl = lows[-1] > lows[-2]
    lh = highs[-1] < highs[-2]
    ll = lows[-1] < lows[-2]

    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "neutral"
