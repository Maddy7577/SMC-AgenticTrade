"""Curated EURUSD candle scenarios for detector and strategy tests (J1).

Each factory function returns a list of candle dicts that represent a
specific market scenario. Candles use realistic EUR_USD price levels.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _c(offset_min: int, o: float, h: float, l: float, c: float, v: int = 100) -> dict:
    t = datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=offset_min)
    return {"instrument": "EUR_USD", "t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def bullish_fvg_scenario() -> list[dict]:
    """3-candle sequence with a clear bullish FVG (10 pips gap — well above 5-pip floor)."""
    return [
        _c(0,  1.10000, 1.10000, 1.09950, 1.09980),  # C1 — high 1.10000
        _c(1,  1.09980, 1.10050, 1.09960, 1.10040),  # C2 — displacement
        _c(2,  1.10100, 1.10200, 1.10100, 1.10150),  # C3 — low 1.10100 (gap 10 pips above C1.h)
    ]


def bearish_fvg_scenario() -> list[dict]:
    """3-candle sequence with a clear bearish FVG (10 pips gap — well above 5-pip floor)."""
    return [
        _c(0,  1.10200, 1.10250, 1.10200, 1.10220),  # C1 — low 1.10200
        _c(1,  1.10220, 1.10230, 1.10130, 1.10140),  # C2 — displacement
        _c(2,  1.10050, 1.10090, 1.10020, 1.10060),  # C3 — high 1.10090 (gap 11 pips below C1.l)
    ]


def fvg_too_small_scenario() -> list[dict]:
    """3-candle with a gap of only 3 pips — below 5-pip minimum."""
    return [
        _c(0,  1.10000, 1.10030, 1.09990, 1.10020),  # C1 — high 1.10030
        _c(1,  1.10020, 1.10060, 1.10010, 1.10055),
        _c(2,  1.10060, 1.10100, 1.10060, 1.10090),  # C3 — low 1.10060 (gap = 3 pips)
    ]


def swing_high_low_scenario() -> list[dict]:
    """25-candle sequence with a clear swing high at index 12 and swing low at index 18."""
    base = 1.10000
    candles = []
    prices = [
        # Rising into swing high
        (base + 0.0000, base + 0.0010, base - 0.0005),
        (base + 0.0005, base + 0.0015, base + 0.0000),
        (base + 0.0010, base + 0.0020, base + 0.0005),
        (base + 0.0015, base + 0.0025, base + 0.0010),
        (base + 0.0020, base + 0.0030, base + 0.0015),
        (base + 0.0025, base + 0.0035, base + 0.0020),
        (base + 0.0030, base + 0.0040, base + 0.0025),
        (base + 0.0035, base + 0.0045, base + 0.0030),
        (base + 0.0040, base + 0.0050, base + 0.0035),
        (base + 0.0045, base + 0.0055, base + 0.0040),
        (base + 0.0050, base + 0.0060, base + 0.0045),
        (base + 0.0055, base + 0.0065, base + 0.0050),
        # Swing high at index 12
        (base + 0.0060, base + 0.0090, base + 0.0055),
        # Falling
        (base + 0.0055, base + 0.0065, base + 0.0050),
        (base + 0.0050, base + 0.0060, base + 0.0045),
        (base + 0.0045, base + 0.0055, base + 0.0040),
        (base + 0.0040, base + 0.0050, base + 0.0035),
        (base + 0.0035, base + 0.0045, base + 0.0030),
        # Swing low at index 18
        (base + 0.0030, base + 0.0040, base - 0.0020),
        # Recovering
        (base + 0.0035, base + 0.0045, base + 0.0030),
        (base + 0.0040, base + 0.0050, base + 0.0035),
        (base + 0.0045, base + 0.0055, base + 0.0040),
        (base + 0.0050, base + 0.0060, base + 0.0045),
        (base + 0.0055, base + 0.0065, base + 0.0050),
        (base + 0.0060, base + 0.0070, base + 0.0055),
    ]
    for i, (o, h, l) in enumerate(prices):
        candles.append(_c(i, o, h, l, (o + (o + h + l) / 3) / 2))
    return candles


def mss_bullish_scenario() -> list[dict]:
    """Candle series ending in a bullish MSS (body closes above last swing high)."""
    base = 1.10000
    candles = [
        _c(0,  base,        base+0.0010, base-0.0005, base+0.0005),
        _c(1,  base+0.0005, base+0.0020, base+0.0000, base+0.0015),
        _c(2,  base+0.0015, base+0.0025, base+0.0010, base+0.0020),
        # swing high at index 3
        _c(3,  base+0.0020, base+0.0050, base+0.0015, base+0.0025),
        _c(4,  base+0.0025, base+0.0035, base+0.0015, base+0.0020),
        _c(5,  base+0.0020, base+0.0030, base+0.0010, base+0.0015),
        # MSS break: body high clears swing high
        _c(6,  base+0.0030, base+0.0080, base+0.0025, base+0.0070),
    ]
    return candles


def mss_bearish_scenario() -> list[dict]:
    """Candle series ending in a bearish MSS (body closes below last swing low)."""
    base = 1.10100
    candles = [
        _c(0,  base,        base+0.0010, base-0.0005, base+0.0005),
        _c(1,  base+0.0005, base+0.0015, base-0.0010, base-0.0005),
        _c(2,  base-0.0005, base+0.0005, base-0.0020, base-0.0015),
        # swing low at index 3
        _c(3,  base-0.0015, base-0.0005, base-0.0060, base-0.0020),
        _c(4,  base-0.0020, base-0.0010, base-0.0040, base-0.0015),
        _c(5,  base-0.0015, base-0.0005, base-0.0030, base-0.0010),
        # MSS break: body low clears swing low
        _c(6,  base-0.0020, base-0.0010, base-0.0090, base-0.0080),
    ]
    return candles


def order_block_bull_scenario() -> list[dict]:
    """20-candle sequence with a bullish OB: last bearish candle before a bull displacement."""
    base = 1.10000
    candles = []
    # 15 neutral candles for ATR seed
    for i in range(15):
        candles.append(_c(i, base, base + 0.0008, base - 0.0008, base + 0.0002))
    # Last bearish candle (the OB) — low set low enough that displacement won't breach it
    candles.append(_c(15, base + 0.0005, base + 0.0010, base - 0.0015, base - 0.0003))
    # Bull displacement: range ≥ 2× ATR (~0.0016 → use 0.0060); low stays above OB.low
    candles.append(_c(16, base - 0.0003, base + 0.0060, base - 0.0001, base + 0.0055))
    # A couple trailing candles
    candles.append(_c(17, base + 0.0055, base + 0.0065, base + 0.0050, base + 0.0060))
    candles.append(_c(18, base + 0.0060, base + 0.0070, base + 0.0055, base + 0.0065))
    return candles


def sweep_pdh_scenario() -> list[dict]:
    """Bearish sweep of PDH: wick above 1.10200, close below."""
    candles = [
        _c(0,  1.10150, 1.10180, 1.10130, 1.10160),
        _c(1,  1.10160, 1.10250, 1.10140, 1.10170),  # wick above PDH 1.10200, close below
    ]
    daily = [
        _c(0,  1.10000, 1.10200, 1.09900, 1.10100),  # prev day high = 1.10200
        _c(1440, 1.10100, 1.10220, 1.10050, 1.10180),
    ]
    return candles, daily


def no_trade_scenario() -> list[dict]:
    """Flat/ranging candles — no clear structure. All strategies should produce NO_TRADE."""
    base = 1.10000
    candles = []
    for i in range(30):
        drift = 0.0001 * ((i % 5) - 2)
        candles.append(_c(i, base + drift, base + drift + 0.0003, base + drift - 0.0003, base + drift))
    return candles
