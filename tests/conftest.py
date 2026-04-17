"""Shared pytest fixtures for SMC-TradeAgents tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config.instruments import InstrumentMeta, INSTRUMENTS


# ---------------------------------------------------------------------------
# Candle builder helpers
# ---------------------------------------------------------------------------

def _candle(
    t: str | datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    v: int = 100,
    instrument: str = "EUR_USD",
) -> dict:
    """Return a candle dict that matches the storage schema."""
    if isinstance(t, str):
        t = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
    return {"instrument": instrument, "t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


@pytest.fixture
def candle_factory():
    return _candle


@pytest.fixture
def eurusd_meta() -> InstrumentMeta:
    return INSTRUMENTS["EUR_USD"]


# ---------------------------------------------------------------------------
# Minimal flat sequence (20 neutral candles, useful as background)
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_candles_20():
    base_price = 1.10000
    candles = []
    for i in range(20):
        ts = datetime(2026, 1, 6, 10, i, 0, tzinfo=timezone.utc)
        candles.append(_candle(ts, base_price, base_price + 0.0005, base_price - 0.0005, base_price))
    return candles
