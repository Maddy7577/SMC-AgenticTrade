"""Shared scoring helpers used by multiple agents (D3)."""

from __future__ import annotations


def displacement_strength(candle: dict, atr_value: float | None) -> float:
    """Score 0–1: how strong is this displacement candle relative to ATR."""
    if not atr_value or atr_value == 0:
        return 0.5
    body = abs(candle["c"] - candle["o"])
    return min(body / (atr_value * 2), 1.0)


def wick_quality(candle: dict) -> float:
    """Score 0–1: how clean the entry wick is (small wicks = cleaner rejection)."""
    total_range = candle["h"] - candle["l"]
    if total_range == 0:
        return 0.5
    body = abs(candle["c"] - candle["o"])
    return min(body / total_range, 1.0)


def structure_clarity(mss_events: list, fvgs: list) -> float:
    """Score 0–1: how clear the structure is (more events = higher clarity, capped)."""
    score = min(len(mss_events) * 0.25 + len(fvgs) * 0.15, 1.0)
    return score


def rr_score(rr: float, floor: float = 2.0, ideal: float = 3.0) -> float:
    """Score 0–1: map RR to a quality score. Below floor = 0, ideal+ = 1."""
    if rr < floor:
        return 0.0
    if rr >= ideal:
        return 1.0
    return (rr - floor) / (ideal - floor)


def fvg_overlap_pct(fvg1_top: float, fvg1_bot: float, fvg2_top: float, fvg2_bot: float) -> float:
    """Return overlap as a fraction of the smaller FVG's size (0–1)."""
    overlap_top = min(fvg1_top, fvg2_top)
    overlap_bot = max(fvg1_bot, fvg2_bot)
    overlap = max(0.0, overlap_top - overlap_bot)
    size = min(fvg1_top - fvg1_bot, fvg2_top - fvg2_bot)
    if size <= 0:
        return 0.0
    return min(overlap / size, 1.0)
