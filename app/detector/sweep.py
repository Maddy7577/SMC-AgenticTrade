"""Liquidity Sweep detector (FR-C-06).

Monitors:
  - Previous Day High (PDH) / Previous Day Low (PDL)
  - Equal Highs / Equal Lows within 5-pip tolerance
  - Asian session H/L (05:30–12:30 IST = 00:00–07:00 UTC)
  - Recent swing H/L

A sweep occurs when price wicks through the level but candle CLOSES back
on the other side (i.e., the wick hunts liquidity then reverses).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.detector.swings import detect_swings
from config.instruments import pips_to_price
from config.settings import EQH_EQL_TOLERANCE_PIPS

SweepDirection = Literal["bullish", "bearish"]
# bullish sweep: price wicks below a low level then closes above → bullish reversal
# bearish sweep: price wicks above a high level then closes below → bearish reversal


@dataclass
class SweepEvent:
    index: int
    t: str
    direction: SweepDirection
    swept_level: float
    level_type: str   # 'pdh' | 'pdl' | 'eqh' | 'eql' | 'asian_h' | 'asian_l' | 'swing_h' | 'swing_l'
    wick_extreme: float


def detect_sweeps(
    candles: list[dict],
    instrument: str = "EUR_USD",
    daily_candles: list[dict] | None = None,
    asian_high: float | None = None,
    asian_low: float | None = None,
    lookback: int = 10,
) -> list[SweepEvent]:
    results: list[SweepEvent] = []
    tolerance = pips_to_price(EQH_EQL_TOLERANCE_PIPS, instrument)

    # Build candidate levels
    levels: list[tuple[float, str]] = []

    # PDH / PDL from daily candles
    if daily_candles and len(daily_candles) >= 2:
        prev_day = daily_candles[-2]
        levels.append((prev_day["h"], "pdh"))
        levels.append((prev_day["l"], "pdl"))

    # Asian range
    if asian_high is not None:
        levels.append((asian_high, "asian_h"))
    if asian_low is not None:
        levels.append((asian_low, "asian_l"))

    # Equal Highs / Lows (within tolerance in recent candles)
    for i in range(len(candles)):
        hi = candles[i]["h"]
        lo = candles[i]["l"]
        count_h = sum(1 for c in candles[max(0, i - 20):i] if abs(c["h"] - hi) <= tolerance)
        count_l = sum(1 for c in candles[max(0, i - 20):i] if abs(c["l"] - lo) <= tolerance)
        if count_h >= 2:
            levels.append((hi, "eqh"))
        if count_l >= 2:
            levels.append((lo, "eql"))

    # Swing H/L from recent candles
    swings = detect_swings(candles, lookback)
    for s in swings:
        if s["kind"] == "high":
            levels.append((s["price"], "swing_h"))
        else:
            levels.append((s["price"], "swing_l"))

    # Check each candle for sweep
    for i in range(1, len(candles)):
        c = candles[i]
        for level, ltype in levels:
            # Bearish sweep: wick above high level, close below
            if c["h"] > level and c["c"] < level and ltype in ("pdh", "asian_h", "eqh", "swing_h"):
                results.append(SweepEvent(
                    index=i,
                    t=str(c["t"]),
                    direction="bearish",
                    swept_level=level,
                    level_type=ltype,
                    wick_extreme=c["h"],
                ))
            # Bullish sweep: wick below low level, close above
            elif c["l"] < level and c["c"] > level and ltype in ("pdl", "asian_l", "eql", "swing_l"):
                results.append(SweepEvent(
                    index=i,
                    t=str(c["t"]),
                    direction="bullish",
                    swept_level=level,
                    level_type=ltype,
                    wick_extreme=c["l"],
                ))

    return results


def latest_sweep(
    candles: list[dict],
    instrument: str = "EUR_USD",
    daily_candles: list[dict] | None = None,
    asian_high: float | None = None,
    asian_low: float | None = None,
) -> SweepEvent | None:
    events = detect_sweeps(candles, instrument, daily_candles, asian_high, asian_low)
    return events[-1] if events else None
