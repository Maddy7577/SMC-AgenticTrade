"""Price gap detector for Vacuum Block strategy (FR-C2-05).

Gap up:  curr.low  > prev.high
Gap down: curr.high < prev.low

Classification by time delta between candles:
  weekend_gap: > 24 hours
  news_gap:    1 hour – 24 hours
  session_gap: < 1 hour

Full fill: candle BODY (open/close) closes inside/beyond gap — wick-only entry is NOT a fill.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _parse_t(t) -> datetime:
    if isinstance(t, datetime):
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(t)).replace(tzinfo=timezone.utc)


def _classify_gap(prev_candle: dict, curr_candle: dict) -> str:
    delta = (_parse_t(curr_candle["t"]) - _parse_t(prev_candle["t"])).total_seconds()
    if delta > 86400:
        return "weekend_gap"
    if delta >= 3600:
        return "news_gap"
    return "session_gap"


def detect_gaps(h1_candles: list[dict]) -> list[dict]:
    """Detect open price gaps in H1 candles. Returns list of gap dicts."""
    gaps: list[dict] = []
    for i in range(1, len(h1_candles)):
        prev, curr = h1_candles[i - 1], h1_candles[i]
        if curr["l"] > prev["h"]:
            bottom = prev["h"]
            top = curr["l"]
            ce = round((top + bottom) / 2, 5)
            gaps.append({
                "id": f"gap_up_{i}",
                "gap_type": _classify_gap(prev, curr),
                "direction": "up",
                "top": top,
                "bottom": bottom,
                "ce": ce,
                "filled_pct": 0.0,
                "formed_t": str(curr["t"]),
                "fully_filled": False,
            })
        elif curr["h"] < prev["l"]:
            top = prev["l"]
            bottom = curr["h"]
            ce = round((top + bottom) / 2, 5)
            gaps.append({
                "id": f"gap_down_{i}",
                "gap_type": _classify_gap(prev, curr),
                "direction": "down",
                "top": top,
                "bottom": bottom,
                "ce": ce,
                "filled_pct": 0.0,
                "formed_t": str(curr["t"]),
                "fully_filled": False,
            })
    return gaps


def update_gap_fill_status(gaps: list[dict], new_candle: dict) -> list[dict]:
    """Update fill status for each gap using the new candle body (not wicks)."""
    body_high = max(new_candle["o"], new_candle["c"])
    body_low = min(new_candle["o"], new_candle["c"])
    for gap in gaps:
        if gap["fully_filled"]:
            continue
        top, bottom = gap["top"], gap["bottom"]
        gap_size = top - bottom
        if gap_size <= 0:
            gap["fully_filled"] = True
            gap["filled_pct"] = 100.0
            continue
        # Body overlap with gap
        overlap_top = min(body_high, top)
        overlap_bot = max(body_low, bottom)
        if overlap_top > overlap_bot:
            fill = (overlap_top - overlap_bot) / gap_size
            gap["filled_pct"] = round(min(fill * 100, 100.0), 1)
        # Full fill: body low <= gap bottom (for up-gaps) or body high >= gap top (for down-gaps)
        if gap["direction"] == "up" and body_low <= bottom:
            gap["fully_filled"] = True
            gap["filled_pct"] = 100.0
        elif gap["direction"] == "down" and body_high >= top:
            gap["fully_filled"] = True
            gap["filled_pct"] = 100.0
    return gaps
