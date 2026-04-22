"""Fair Value Gap (FVG) detector with full state machine.

Detection rule (FR-C-02): C1 wick does not overlap C3 wick AND gap ≥ 5 pips.
Bullish FVG: C1.high < C3.low  (gap above C1, below C3)
Bearish FVG: C1.low > C3.high  (gap below C1, above C3)

State machine (FR-C-03):
  formed → retested (price enters gap) → partially_filled / fully_filled / inverted
  inverted = candle BODY closes through the entire FVG (used by Strategy #6)

CE-test history (FR-C2-03): each time price enters the zone, record whether the candle
  closed beyond the CE (failed) or respected it (held).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from config.instruments import pips_to_price
from config.settings import FVG_MIN_PIPS

FVGState = Literal["formed", "retested", "partially_filled", "fully_filled", "inverted"]
FVGDirection = Literal["bullish", "bearish"]


@dataclass
class FVG:
    id: str           # f"{instrument}_{timeframe}_{c1_index}"
    instrument: str
    timeframe: str
    c1_index: int     # index of C1 in the original candle list
    c1_t: str
    c3_t: str
    top: float        # upper bound of the gap
    bottom: float     # lower bound of the gap
    midpoint: float
    direction: FVGDirection
    state: FVGState = "formed"
    size_pips: float = 0.0
    tests: list[dict] = field(default_factory=list)  # CE-test history (FR-C2-03)

    @property
    def ce(self) -> float:
        return self.midpoint


def detect_fvgs(
    candles: list[dict],
    instrument: str = "EUR_USD",
    timeframe: str = "M1",
) -> list[FVG]:
    """Return all FVGs formed within the supplied candle list."""
    min_size = pips_to_price(FVG_MIN_PIPS, instrument)
    results: list[FVG] = []
    n = len(candles)
    for i in range(n - 2):
        c1, c3 = candles[i], candles[i + 2]

        # Bullish: gap between c1.high and c3.low
        if c3["l"] > c1["h"]:
            gap = c3["l"] - c1["h"]
            if gap >= min_size:
                size_pips = gap / pips_to_price(1, instrument)
                results.append(
                    FVG(
                        id=f"{instrument}_{timeframe}_{i}",
                        instrument=instrument,
                        timeframe=timeframe,
                        c1_index=i,
                        c1_t=str(c1["t"]),
                        c3_t=str(c3["t"]),
                        top=c3["l"],
                        bottom=c1["h"],
                        midpoint=round((c1["h"] + c3["l"]) / 2, 5),
                        direction="bullish",
                        size_pips=round(size_pips, 1),
                    )
                )

        # Bearish: gap between c3.high and c1.low
        elif c1["l"] > c3["h"]:
            gap = c1["l"] - c3["h"]
            if gap >= min_size:
                size_pips = gap / pips_to_price(1, instrument)
                results.append(
                    FVG(
                        id=f"{instrument}_{timeframe}_{i}",
                        instrument=instrument,
                        timeframe=timeframe,
                        c1_index=i,
                        c1_t=str(c1["t"]),
                        c3_t=str(c3["t"]),
                        top=c1["l"],
                        bottom=c3["h"],
                        midpoint=round((c3["h"] + c1["l"]) / 2, 5),
                        direction="bearish",
                        size_pips=round(size_pips, 1),
                    )
                )
    return results


def update_fvg_state(fvg: FVG, candle: dict) -> FVG:
    """Advance the FVG state machine given a new candle. Returns updated FVG."""
    if fvg.state in ("fully_filled", "inverted"):
        return fvg

    c_high, c_low = candle["h"], candle["l"]
    c_open, c_close = candle["o"], candle["c"]

    if fvg.direction == "bullish":
        # Inverted: candle BODY closes entirely through the gap (FR-SP-06-01)
        if c_close < fvg.bottom and c_open > fvg.top:
            fvg.state = "inverted"
        elif c_low <= fvg.bottom:
            fvg.state = "fully_filled"
        elif c_low <= fvg.top:
            if fvg.state == "formed":
                fvg.state = "retested"
            elif fvg.state == "retested":
                fvg.state = "partially_filled"
    else:  # bearish
        if c_close > fvg.top and c_open < fvg.bottom:
            fvg.state = "inverted"
        elif c_high >= fvg.top:
            fvg.state = "fully_filled"
        elif c_high >= fvg.bottom:
            if fvg.state == "formed":
                fvg.state = "retested"
            elif fvg.state == "retested":
                fvg.state = "partially_filled"
    return fvg


def update_fvg_ce_tests(fvgs: list[FVG], new_candle: dict) -> list[FVG]:
    """Record CE-test history for each active FVG (FR-C2-03).

    A test is recorded when price enters the gap zone.
    respected=True if candle closes back inside zone (did NOT close beyond CE).
    Bullish failure: close < CE (closed below midpoint — bearish escape).
    Bearish failure: close > CE (closed above midpoint — bullish escape).
    """
    for fvg in fvgs:
        if fvg.state in ("fully_filled", "inverted"):
            continue
        c_high, c_low = new_candle["h"], new_candle["l"]
        c_close = new_candle["c"]
        candle_t = str(new_candle["t"])
        # Candle entered the gap zone
        if fvg.direction == "bullish" and c_low <= fvg.top and c_high >= fvg.bottom:
            respected = c_close >= fvg.ce
            fvg.tests.append({
                "t": candle_t,
                "respected": respected,
                "close_price": c_close,
            })
        elif fvg.direction == "bearish" and c_high >= fvg.bottom and c_low <= fvg.top:
            respected = c_close <= fvg.ce
            fvg.tests.append({
                "t": candle_t,
                "respected": respected,
                "close_price": c_close,
            })
    return fvgs
