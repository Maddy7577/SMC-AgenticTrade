"""Unit tests for Premium/Discount zone (J2)."""

from __future__ import annotations

import pytest

from app.detector.pd_zone import PDZone, compute_pd_zone


def _candles(highs: list[float], lows: list[float]) -> list[dict]:
    return [
        {"o": (h + l) / 2, "h": h, "l": l, "c": (h + l) / 2}
        for h, l in zip(highs, lows, strict=False)
    ]


# ---------------------------------------------------------------------------
# PDZone dataclass
# ---------------------------------------------------------------------------

def test_pdzone_classify_premium():
    z = PDZone(range_high=1.11000, range_low=1.09000, equilibrium=1.10000)
    assert z.classify(1.10500) == "premium"


def test_pdzone_classify_discount():
    z = PDZone(range_high=1.11000, range_low=1.09000, equilibrium=1.10000)
    assert z.classify(1.09500) == "discount"


def test_pdzone_classify_equilibrium():
    z = PDZone(range_high=1.11000, range_low=1.09000, equilibrium=1.10000)
    assert z.classify(1.10000) == "equilibrium"


def test_pdzone_properties():
    z = PDZone(range_high=1.11000, range_low=1.09000, equilibrium=1.10000)
    assert z.premium_upper == 1.11000
    assert z.premium_lower == 1.10000
    assert z.discount_upper == 1.10000
    assert z.discount_lower == 1.09000


# ---------------------------------------------------------------------------
# compute_pd_zone
# ---------------------------------------------------------------------------

def test_compute_pd_zone_returns_none_for_tiny_list():
    assert compute_pd_zone([]) is None
    assert compute_pd_zone([{"o": 1.1, "h": 1.11, "l": 1.09, "c": 1.10}]) is None


def test_compute_pd_zone_basic():
    highs = [1.10000 + i * 0.0010 for i in range(25)]
    lows = [1.09900 + i * 0.0010 for i in range(25)]
    candles = _candles(highs, lows)
    zone = compute_pd_zone(candles)
    assert zone is not None
    assert zone.range_high > zone.range_low
    assert zone.range_low < zone.equilibrium < zone.range_high


def test_compute_pd_zone_equilibrium_is_midpoint():
    candles = _candles([1.11000] * 5, [1.09000] * 5)
    zone = compute_pd_zone(candles)
    assert zone is not None
    assert zone.equilibrium == pytest.approx(1.10000, abs=1e-5)


def test_compute_pd_zone_uses_recent_20_candles():
    # 30 candles — old ones have different range, recent 20 should dominate
    old = _candles([1.10000] * 10, [1.09000] * 10)
    recent = _candles([1.12000] * 20, [1.10500] * 20)
    candles = old + recent
    zone = compute_pd_zone(candles)
    assert zone is not None
    assert zone.range_high == pytest.approx(1.12000, abs=1e-5)
    assert zone.range_low == pytest.approx(1.10500, abs=1e-5)
