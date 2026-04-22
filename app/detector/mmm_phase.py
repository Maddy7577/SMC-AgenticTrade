"""Market Maker Model phase detector (FR-C2-07).

Phases:
  1 = Consolidation  (range-bound, ≥3 touches each boundary over 50-candle Daily lookback)
  2 = Sell Program   (bearish expansion away from consolidation)
  3 = Smart Money Reversal
  4 = Buy Program (or inverse)
  0 = Unknown

Phase transitions are persisted to the settings KV table (NFR-R2-03).
"""

from __future__ import annotations

from config.instruments import price_to_pips

_CONSOL_TOUCH_LOOKBACK = 50
_CONSOL_MIN_TOUCHES = 3
_EXPANSION_PIPS = 20.0


def detect_mmm_phase(
    h4_candles: list[dict],
    d_candles: list[dict],
) -> dict:
    """Return MMM phase dict from H4/Daily candles.

    Returns:
        {phase: int, consolidation_low: float|None, consolidation_high: float|None, direction: str|None}
    """
    result: dict = {
        "phase": 0,
        "consolidation_low": None,
        "consolidation_high": None,
        "direction": None,
    }
    if len(d_candles) < 10:
        return result

    lookback = d_candles[-_CONSOL_TOUCH_LOOKBACK:]
    consol = _find_consolidation(lookback)
    if consol is None:
        return result

    consol_low, consol_high = consol
    result["consolidation_low"] = consol_low
    result["consolidation_high"] = consol_high
    result["phase"] = 1  # consolidation confirmed

    # Check for expansion (Phase 2 or 4) using recent H4 candles
    if len(h4_candles) >= 3:
        recent = h4_candles[-10:]
        bearish_break = any(c["l"] < consol_low - price_to_pips(_EXPANSION_PIPS) for c in recent)
        bullish_break = any(c["h"] > consol_high + price_to_pips(_EXPANSION_PIPS) for c in recent)

        if bearish_break:
            result["phase"] = 2
            result["direction"] = "bearish"
            # Phase 3: Smart Money Reversal — look for bullish reversal after bearish break
            if _detect_smr(h4_candles, "bearish", consol_low):
                result["phase"] = 3
                result["direction"] = "bullish"
        elif bullish_break:
            result["phase"] = 4
            result["direction"] = "bullish"
            if _detect_smr(h4_candles, "bullish", consol_high):
                result["phase"] = 3
                result["direction"] = "bearish"

    return result


def _find_consolidation(
    candles: list[dict],
) -> tuple[float, float] | None:
    """Return (low, high) of consolidation zone if ≥3 touches each boundary, else None."""
    if len(candles) < 10:
        return None
    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]
    range_high = max(highs)
    range_low = min(lows)
    span = range_high - range_low
    if span <= 0:
        return None
    tolerance = span * 0.1

    high_touches = sum(1 for h in highs if h >= range_high - tolerance)
    low_touches = sum(1 for l in lows if l <= range_low + tolerance)

    if high_touches >= _CONSOL_MIN_TOUCHES and low_touches >= _CONSOL_MIN_TOUCHES:
        return range_low, range_high
    return None


def _detect_smr(
    h4_candles: list[dict],
    break_direction: str,
    break_level: float,
) -> bool:
    """Detect Smart Money Reversal: price sweeps beyond break level then closes back above/below."""
    if len(h4_candles) < 5:
        return False
    recent = h4_candles[-8:]
    if break_direction == "bearish":
        swept = [c for c in recent if c["l"] < break_level]
        recovered = any(c["c"] > break_level for c in recent[-3:])
        return bool(swept) and recovered
    else:
        swept = [c for c in recent if c["h"] > break_level]
        recovered = any(c["c"] < break_level for c in recent[-3:])
        return bool(swept) and recovered
