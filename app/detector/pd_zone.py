"""Premium / Discount zone from H4 or Daily dealing range (FR-C-08).

Premium zone: price > 50% of the dealing range (above CE)
Discount zone: price < 50% of the dealing range (below CE)

The dealing range is the most recent significant swing high to swing low
(or vice versa) on H4 or Daily timeframe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PDLabel = Literal["premium", "discount", "equilibrium"]


@dataclass
class PDZone:
    range_high: float
    range_low: float
    equilibrium: float   # CE (50%)

    def classify(self, price: float) -> PDLabel:
        if price > self.equilibrium:
            return "premium"
        elif price < self.equilibrium:
            return "discount"
        return "equilibrium"

    @property
    def premium_upper(self) -> float:
        return self.range_high

    @property
    def premium_lower(self) -> float:
        return self.equilibrium

    @property
    def discount_upper(self) -> float:
        return self.equilibrium

    @property
    def discount_lower(self) -> float:
        return self.range_low


def compute_pd_zone(htf_candles: list[dict]) -> PDZone | None:
    """Derive dealing range from the most recent significant swing on HTF candles."""
    if len(htf_candles) < 2:
        return None

    recent_high = max(c["h"] for c in htf_candles[-20:])
    recent_low = min(c["l"] for c in htf_candles[-20:])
    eq = round((recent_high + recent_low) / 2, 5)
    return PDZone(range_high=recent_high, range_low=recent_low, equilibrium=eq)
