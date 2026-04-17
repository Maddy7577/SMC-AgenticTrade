"""Unit tests for shared scoring helpers (D3)."""

from __future__ import annotations

import pytest

from app.strategies.scoring import (
    displacement_strength,
    fvg_overlap_pct,
    rr_score,
    structure_clarity,
    wick_quality,
)

# ---------------------------------------------------------------------------
# displacement_strength
# ---------------------------------------------------------------------------

def test_displacement_strength_no_atr_returns_half():
    c = {"o": 1.10000, "h": 1.10100, "l": 1.09900, "c": 1.10050}
    assert displacement_strength(c, None) == pytest.approx(0.5)
    assert displacement_strength(c, 0) == pytest.approx(0.5)


def test_displacement_strength_large_body_capped_at_1():
    c = {"o": 1.10000, "h": 1.10500, "l": 1.09500, "c": 1.10400}  # body=0.004
    result = displacement_strength(c, atr_value=0.0010)  # body/2×atr = 2.0, capped at 1.0
    assert result == pytest.approx(1.0)


def test_displacement_strength_weak_body():
    c = {"o": 1.10000, "h": 1.10050, "l": 1.09990, "c": 1.10005}  # body=0.00005
    result = displacement_strength(c, atr_value=0.0010)
    assert result < 0.1


# ---------------------------------------------------------------------------
# wick_quality
# ---------------------------------------------------------------------------

def test_wick_quality_full_body_returns_1():
    # No wicks: open=low, close=high (all body)
    c = {"o": 1.10000, "h": 1.10100, "l": 1.10000, "c": 1.10100}
    assert wick_quality(c) == pytest.approx(1.0)


def test_wick_quality_zero_range_returns_half():
    c = {"o": 1.10000, "h": 1.10000, "l": 1.10000, "c": 1.10000}
    assert wick_quality(c) == pytest.approx(0.5)


def test_wick_quality_small_body_big_wicks():
    # Tiny body relative to range = low quality
    c = {"o": 1.10050, "h": 1.10100, "l": 1.09900, "c": 1.10060}  # body=0.0001, range=0.002
    result = wick_quality(c)
    assert result < 0.1


# ---------------------------------------------------------------------------
# structure_clarity
# ---------------------------------------------------------------------------

def test_structure_clarity_zero_events():
    assert structure_clarity([], []) == pytest.approx(0.0)


def test_structure_clarity_scales_with_events():
    result_low = structure_clarity(mss_events=[], fvgs=["a"])
    result_high = structure_clarity(mss_events=["a", "b"], fvgs=["a", "b"])
    assert result_high > result_low


def test_structure_clarity_capped_at_1():
    # Many events should not exceed 1.0
    result = structure_clarity(mss_events=["a"] * 10, fvgs=["b"] * 10)
    assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# rr_score
# ---------------------------------------------------------------------------

def test_rr_score_below_floor_is_zero():
    assert rr_score(1.5, floor=2.0) == pytest.approx(0.0)
    assert rr_score(1.99, floor=2.0) == pytest.approx(0.0)


def test_rr_score_at_ideal_is_one():
    assert rr_score(3.0, floor=2.0, ideal=3.0) == pytest.approx(1.0)
    assert rr_score(5.0, floor=2.0, ideal=3.0) == pytest.approx(1.0)


def test_rr_score_interpolates():
    # Midpoint between floor (2.0) and ideal (3.0) = 2.5 → score ≈ 0.5
    result = rr_score(2.5, floor=2.0, ideal=3.0)
    assert result == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# fvg_overlap_pct
# ---------------------------------------------------------------------------

def test_fvg_overlap_full():
    # Same FVG → 100% overlap
    result = fvg_overlap_pct(1.101, 1.100, 1.101, 1.100)
    assert result == pytest.approx(1.0)


def test_fvg_overlap_none():
    # No overlap (FVGs are separated)
    result = fvg_overlap_pct(1.101, 1.100, 1.103, 1.102)
    assert result == pytest.approx(0.0)


def test_fvg_overlap_partial():
    # Partial overlap
    result = fvg_overlap_pct(1.102, 1.100, 1.103, 1.101)
    assert 0 < result < 1


def test_fvg_overlap_zero_size_returns_zero():
    result = fvg_overlap_pct(1.100, 1.100, 1.100, 1.100)
    assert result == pytest.approx(0.0)
