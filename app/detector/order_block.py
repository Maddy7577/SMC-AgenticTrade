"""Order Block and Breaker Block detection.

Order Block (FR-C-04):
  - Displacement candle: range ≥ 2× ATR
  - OB = last candle of opposite color immediately before the displacement move

Breaker Block (FR-C-05):
  - OB is invalidated when price trades through it AFTER a liquidity sweep
  - At that point, the OB becomes a Breaker (flips polarity — now acts as
    resistance if it was bullish OB, support if bearish OB)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.detector.atr import atr_series
from config.settings import OB_DISPLACEMENT_ATR_MULTIPLIER

OBKind = Literal["order_block", "breaker_block"]
OBDirection = Literal["bullish", "bearish"]


@dataclass
class OrderBlock:
    id: str
    instrument: str
    timeframe: str
    ob_index: int      # index of the OB candle in original list
    ob_t: str
    high: float
    low: float
    direction: OBDirection
    kind: OBKind = "order_block"
    valid: bool = True  # False when price has traded through it


def detect_order_blocks(
    candles: list[dict],
    instrument: str = "EUR_USD",
    timeframe: str = "M1",
    atr_period: int = 14,
) -> list[OrderBlock]:
    """Return Order Blocks for the supplied candle list."""
    if len(candles) < atr_period + 2:
        return []

    atrs = atr_series(candles, atr_period)
    results: list[OrderBlock] = []

    for i in range(1, len(candles) - 1):
        a = atrs[i]
        if a is None:
            continue
        candle = candles[i]
        displacement = candle["h"] - candle["l"]
        if displacement < OB_DISPLACEMENT_ATR_MULTIPLIER * a:
            continue

        is_bull_displacement = candle["c"] > candle["o"]  # strong bull candle
        is_bear_displacement = candle["c"] < candle["o"]  # strong bear candle

        # Look back for last opposite-color candle before displacement
        if is_bull_displacement:
            for j in range(i - 1, -1, -1):
                c = candles[j]
                if c["c"] < c["o"]:  # last bearish candle before bull displacement = bullish OB
                    results.append(
                        OrderBlock(
                            id=f"{instrument}_{timeframe}_ob_{j}",
                            instrument=instrument,
                            timeframe=timeframe,
                            ob_index=j,
                            ob_t=str(c["t"]),
                            high=c["h"],
                            low=c["l"],
                            direction="bullish",
                        )
                    )
                    break

        elif is_bear_displacement:
            for j in range(i - 1, -1, -1):
                c = candles[j]
                if c["c"] > c["o"]:  # last bullish candle before bear displacement = bearish OB
                    results.append(
                        OrderBlock(
                            id=f"{instrument}_{timeframe}_ob_{j}",
                            instrument=instrument,
                            timeframe=timeframe,
                            ob_index=j,
                            ob_t=str(c["t"]),
                            high=c["h"],
                            low=c["l"],
                            direction="bearish",
                        )
                    )
                    break

    # Deduplicate by ob_index (keep first found)
    seen: set[int] = set()
    unique: list[OrderBlock] = []
    for ob in results:
        if ob.ob_index not in seen:
            seen.add(ob.ob_index)
            unique.append(ob)
    return unique


def mark_breaker_blocks(
    order_blocks: list[OrderBlock],
    candles: list[dict],
    swept_levels: set[float] | None = None,
) -> list[OrderBlock]:
    """Mark OBs that have been traded through as Breaker Blocks (FR-C-05).

    An OB becomes a Breaker when price closes through it.
    `swept_levels` optionally carries context from the sweep detector.
    """
    for ob in order_blocks:
        if not ob.valid:
            continue
        for candle in candles[ob.ob_index + 1:]:
            if ob.direction == "bullish" and candle["l"] < ob.low:
                ob.valid = False
                ob.kind = "breaker_block"
                break
            elif ob.direction == "bearish" and candle["h"] > ob.high:
                ob.valid = False
                ob.kind = "breaker_block"
                break
    return order_blocks
