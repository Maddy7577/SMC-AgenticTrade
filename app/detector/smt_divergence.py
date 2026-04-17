"""SMT Divergence — EURUSD vs GBPUSD swing comparison (FR-C-11).

Checks the last N M5 candles (default 50) for correlated pairs.
Divergence when one pair makes HH while the other makes LH (bullish SMT)
or one makes LL while the other makes HL (bearish SMT).
"""

from __future__ import annotations

from typing import Literal

from app.detector.swings import detect_swings
from config.settings import SMT_LOOKBACK_CANDLES_M5, SWING_LOOKBACK

SMTResult = Literal["bullish", "bearish", "none"]


def detect_smt_divergence(
    eurusd_m5: list[dict],
    gbpusd_m5: list[dict],
    candle_lookback: int = SMT_LOOKBACK_CANDLES_M5,
    swing_lookback: int = SWING_LOOKBACK,
) -> SMTResult:
    """Compare swing structure of the two pairs. Return divergence direction or 'none'."""
    eu = eurusd_m5[-candle_lookback:] if len(eurusd_m5) >= candle_lookback else eurusd_m5
    gu = gbpusd_m5[-candle_lookback:] if len(gbpusd_m5) >= candle_lookback else gbpusd_m5

    eu_swings = detect_swings(eu, swing_lookback)
    gu_swings = detect_swings(gu, swing_lookback)

    eu_highs = [s["price"] for s in eu_swings if s["kind"] == "high"]
    eu_lows = [s["price"] for s in eu_swings if s["kind"] == "low"]
    gu_highs = [s["price"] for s in gu_swings if s["kind"] == "high"]
    gu_lows = [s["price"] for s in gu_swings if s["kind"] == "low"]

    if len(eu_highs) < 2 or len(gu_highs) < 2 or len(eu_lows) < 2 or len(gu_lows) < 2:
        return "none"

    eu_hh = eu_highs[-1] > eu_highs[-2]
    gu_hh = gu_highs[-1] > gu_highs[-2]
    eu_ll = eu_lows[-1] < eu_lows[-2]
    gu_ll = gu_lows[-1] < gu_lows[-2]

    # Bullish SMT: EURUSD makes LL while GBPUSD makes HL (or vice versa) at lows
    if eu_ll and not gu_ll:
        return "bullish"
    if gu_ll and not eu_ll:
        return "bullish"

    # Bearish SMT: EURUSD makes HH while GBPUSD makes LH (or vice versa) at highs
    if eu_hh and not gu_hh:
        return "bearish"
    if gu_hh and not eu_hh:
        return "bearish"

    return "none"
