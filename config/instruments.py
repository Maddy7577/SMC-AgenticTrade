"""Instrument metadata for all symbols the engine handles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentMeta:
    oanda_symbol: str   # e.g. "EUR_USD"
    pip_size: float     # one pip in price units
    tick_size: float    # smallest price increment
    digits: int         # decimal places quoted by broker


INSTRUMENTS: dict[str, InstrumentMeta] = {
    "EUR_USD": InstrumentMeta(
        oanda_symbol="EUR_USD",
        pip_size=0.0001,
        tick_size=0.00001,
        digits=5,
    ),
    "GBP_USD": InstrumentMeta(
        oanda_symbol="GBP_USD",
        pip_size=0.0001,
        tick_size=0.00001,
        digits=5,
    ),
}

# Primary trading instrument
PRIMARY = "EUR_USD"
# SMT pair (used only for divergence comparison)
SMT_PAIR = "GBP_USD"


def pips_to_price(pips: float, instrument: str = PRIMARY) -> float:
    return pips * INSTRUMENTS[instrument].pip_size


def price_to_pips(price_diff: float, instrument: str = PRIMARY) -> float:
    return price_diff / INSTRUMENTS[instrument].pip_size
