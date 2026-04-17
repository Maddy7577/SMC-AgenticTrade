"""Market Structure Shift (MSS) / Change of Character (CHoCH) detector.

Rule (FR-C-07): A break of the most recent swing point with displacement
(closing candle body clears the swing level, NOT just a wick).

MSS vs CHoCH:
  - CHoCH: first break of character (minor, within a pullback)
  - MSS: a more significant break that confirms the new trend
In Phase 1 we return a single 'mss' event type and include a subtype field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.detector.swings import SwingPoint, detect_swings
from config.settings import SWING_LOOKBACK

MSSDirection = Literal["bullish", "bearish"]  # direction of the NEW trend post-break


@dataclass
class MSSEvent:
    index: int       # candle index that caused the break
    t: str
    direction: MSSDirection
    broken_level: float
    broken_swing_t: str
    displacement: float  # size of the breaking candle body


def detect_mss(
    candles: list[dict],
    lookback: int = SWING_LOOKBACK,
) -> list[MSSEvent]:
    """Return all MSS events within the candle list."""
    swings = detect_swings(candles, lookback)
    highs = [s for s in swings if s["kind"] == "high"]
    lows = [s for s in swings if s["kind"] == "low"]

    results: list[MSSEvent] = []

    for i in range(1, len(candles)):
        c = candles[i]
        body_high = max(c["o"], c["c"])
        body_low = min(c["o"], c["c"])

        # Bullish MSS: body closes above most recent swing high
        recent_highs = [s for s in highs if s["index"] < i]
        if recent_highs:
            last_sh = recent_highs[-1]
            if body_high > last_sh["price"]:
                results.append(
                    MSSEvent(
                        index=i,
                        t=str(c["t"]),
                        direction="bullish",
                        broken_level=last_sh["price"],
                        broken_swing_t=last_sh["t"],
                        displacement=body_high - last_sh["price"],
                    )
                )

        # Bearish MSS: body closes below most recent swing low
        recent_lows = [s for s in lows if s["index"] < i]
        if recent_lows:
            last_sl = recent_lows[-1]
            if body_low < last_sl["price"]:
                results.append(
                    MSSEvent(
                        index=i,
                        t=str(c["t"]),
                        direction="bearish",
                        broken_level=last_sl["price"],
                        broken_swing_t=last_sl["t"],
                        displacement=last_sl["price"] - body_low,
                    )
                )

    return results


def latest_mss(candles: list[dict], lookback: int = SWING_LOOKBACK) -> MSSEvent | None:
    events = detect_mss(candles, lookback)
    return events[-1] if events else None
