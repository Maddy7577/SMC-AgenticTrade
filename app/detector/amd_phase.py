"""AMD (Accumulation-Manipulation-Distribution) phase detector (FR-C2-06).

Phase boundaries (IST / UTC+5:30):
  Accumulation:  05:30 – 12:30  (Asian session)
  Manipulation:  12:30 – 15:30  (London open)
  Distribution:  15:30 – 21:30  (NY session)
  Unknown:       outside all windows
"""

from __future__ import annotations

from datetime import datetime

from config.settings import TZ_IST


def get_amd_phase(
    tick_t: datetime,
    asian_high: float | None,
    asian_low: float | None,
    m5_candles: list[dict],
    htf_bias: str = "neutral",
) -> str:
    """Return current AMD phase string.

    Manipulation is flagged as a phase upgrade when a false breakout of the
    Asian range occurs against HTF bias during the London window.
    """
    t_ist = tick_t.astimezone(TZ_IST)
    hm = t_ist.hour * 60 + t_ist.minute

    accum_start, accum_end = 5 * 60 + 30, 12 * 60 + 30
    manip_start, manip_end = 12 * 60 + 30, 15 * 60 + 30
    dist_start, dist_end = 15 * 60 + 30, 21 * 60 + 30

    if accum_start <= hm < accum_end:
        return "Accumulation"

    if manip_start <= hm < manip_end:
        # Detect manipulation: false breakout of Asian range against HTF bias
        if asian_high is not None and asian_low is not None and m5_candles:
            if _detect_manipulation(m5_candles, asian_high, asian_low, htf_bias):
                return "Manipulation"
        return "Accumulation"  # London is open but no confirmed manipulation yet

    if dist_start <= hm < dist_end:
        return "Distribution"

    return "Unknown"


def detect_manipulation_event(
    m5_candles: list[dict],
    asian_high: float,
    asian_low: float,
    htf_bias: str,
) -> dict | None:
    """Return manipulation event dict or None if no false breakout detected."""
    if not m5_candles:
        return None
    for c in reversed(m5_candles[-20:]):
        if htf_bias == "bullish" and c["h"] > asian_high and c["c"] < asian_high:
            return {
                "direction": "bearish_sweep",
                "asian_high": asian_high,
                "asian_low": asian_low,
                "manipulation_extreme": c["h"],
                "candle_t": str(c["t"]),
            }
        if htf_bias == "bearish" and c["l"] < asian_low and c["c"] > asian_low:
            return {
                "direction": "bullish_sweep",
                "asian_high": asian_high,
                "asian_low": asian_low,
                "manipulation_extreme": c["l"],
                "candle_t": str(c["t"]),
            }
    return None


def _detect_manipulation(
    m5_candles: list[dict],
    asian_high: float,
    asian_low: float,
    htf_bias: str,
) -> bool:
    return detect_manipulation_event(m5_candles, asian_high, asian_low, htf_bias) is not None
