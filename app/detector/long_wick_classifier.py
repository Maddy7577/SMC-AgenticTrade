"""Long-wick candle classifier for Rejection Block detection (FR-C2-04)."""

from __future__ import annotations

from config.instruments import price_to_pips


def classify_wick(candle: dict, instrument: str = "EUR_USD") -> dict | None:
    """Return wick classification or None if candle does not qualify.

    Qualifying condition: dominant wick >= 2x body AND dominant wick >= 2x opposing wick.
    Bullish rejection = long lower wick.
    Bearish rejection = long upper wick.
    """
    o, h, l, c = candle["o"], candle["h"], candle["l"], candle["c"]
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    if body == 0:
        return None

    # Bullish rejection: long lower wick
    if lower_wick >= 2 * body and lower_wick >= 2 * upper_wick and lower_wick > 0:
        return {
            "type": "bullish_rejection",
            "wick_pips": round(price_to_pips(lower_wick, instrument), 1),
            "body_pips": round(price_to_pips(body, instrument), 1),
            "ratio": round(lower_wick / body, 2),
        }

    # Bearish rejection: long upper wick
    if upper_wick >= 2 * body and upper_wick >= 2 * lower_wick and upper_wick > 0:
        return {
            "type": "bearish_rejection",
            "wick_pips": round(price_to_pips(upper_wick, instrument), 1),
            "body_pips": round(price_to_pips(body, instrument), 1),
            "ratio": round(upper_wick / body, 2),
        }

    return None
