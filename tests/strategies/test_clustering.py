"""Unit tests for clustering ancestry and cluster engine (J4)."""

from __future__ import annotations

import pytest

from app.clustering.ancestry import (
    can_cluster_together,
    get_family,
    select_representative,
)
from app.clustering.signature import build_cluster_key, parse_strategy_signature

# ---------------------------------------------------------------------------
# Ancestry rules
# ---------------------------------------------------------------------------

def test_unicorn_family_members_can_cluster():
    assert can_cluster_together("01_unicorn", "04_silver_bullet") is True
    assert can_cluster_together("01_unicorn", "03_confirmation") is True
    assert can_cluster_together("04_silver_bullet", "03_confirmation") is True


def test_judas_cannot_cluster_with_unicorn_family():
    assert can_cluster_together("02_judas", "01_unicorn") is False
    assert can_cluster_together("02_judas", "04_silver_bullet") is False
    assert can_cluster_together("02_judas", "03_confirmation") is False


def test_ifvg_cannot_cluster_with_unicorn_family():
    assert can_cluster_together("06_ifvg", "01_unicorn") is False
    assert can_cluster_together("06_ifvg", "03_confirmation") is False


def test_independent_roots_cannot_cluster_together():
    assert can_cluster_together("02_judas", "06_ifvg") is False


def test_unicorn_family_same_member_can_cluster():
    assert can_cluster_together("03_confirmation", "03_confirmation") is True


# ---------------------------------------------------------------------------
# Representative selection
# ---------------------------------------------------------------------------

def test_unicorn_is_representative_over_silver_bullet():
    rep = select_representative(["04_silver_bullet", "01_unicorn", "03_confirmation"])
    assert rep == "01_unicorn"


def test_silver_bullet_beats_confirmation():
    rep = select_representative(["03_confirmation", "04_silver_bullet"])
    assert rep == "04_silver_bullet"


def test_confirmation_alone_is_representative():
    rep = select_representative(["03_confirmation"])
    assert rep == "03_confirmation"


def test_judas_alone_is_representative():
    rep = select_representative(["02_judas"])
    assert rep == "02_judas"


# ---------------------------------------------------------------------------
# Family grouping
# ---------------------------------------------------------------------------

def test_unicorn_family_same_group():
    assert get_family("01_unicorn") == get_family("04_silver_bullet")
    assert get_family("04_silver_bullet") == get_family("03_confirmation")


def test_independent_roots_each_own_family():
    assert get_family("02_judas") != get_family("01_unicorn")
    assert get_family("06_ifvg") != get_family("01_unicorn")
    assert get_family("02_judas") != get_family("06_ifvg")


# ---------------------------------------------------------------------------
# Cluster key / signature
# ---------------------------------------------------------------------------

def test_same_parameters_produce_same_key():
    from datetime import datetime, timezone
    t = datetime(2026, 3, 19, 10, 2, 0, tzinfo=timezone.utc)
    key1 = build_cluster_key(t=t, direction="bullish", sweep_level=1.10000, mss_level=1.10050, entry_midpoint=1.10075)
    key2 = build_cluster_key(t=t, direction="bullish", sweep_level=1.10000, mss_level=1.10050, entry_midpoint=1.10075)
    assert key1 == key2


def test_different_direction_produces_different_key():
    from datetime import datetime, timezone
    t = datetime(2026, 3, 19, 10, 2, 0, tzinfo=timezone.utc)
    key_bull = build_cluster_key(t=t, direction="bullish", sweep_level=1.10000, mss_level=1.10050, entry_midpoint=1.10075)
    key_bear = build_cluster_key(t=t, direction="bearish", sweep_level=1.10000, mss_level=1.10050, entry_midpoint=1.10075)
    assert key_bull != key_bear


def test_times_within_same_5min_bucket_produce_same_key():
    from datetime import datetime, timezone
    t1 = datetime(2026, 3, 19, 10, 1, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 19, 10, 4, 59, tzinfo=timezone.utc)  # same 5-min bucket as t1
    key1 = build_cluster_key(t=t1, direction="bullish", sweep_level=1.10000, mss_level=1.10050, entry_midpoint=1.10075)
    key2 = build_cluster_key(t=t2, direction="bullish", sweep_level=1.10000, mss_level=1.10050, entry_midpoint=1.10075)
    assert key1 == key2


def test_parse_valid_signature():
    # Format: strategy_id:direction:sweep_level:mss_level:entry_midpoint
    sig = "03_confirmation:bullish:1.10000:1.10050:1.10075"
    parsed = parse_strategy_signature(sig)
    assert parsed is not None
    assert parsed["direction"] == "bullish"
    assert parsed["strategy_id"] == "03_confirmation"
    assert parsed["sweep_level"] == pytest.approx(1.10000, abs=1e-5)
    assert parsed["mss_level"] == pytest.approx(1.10050, abs=1e-5)
    assert parsed["entry_midpoint"] == pytest.approx(1.10075, abs=1e-5)


def test_parse_invalid_signature_returns_none():
    assert parse_strategy_signature("") is None
    assert parse_strategy_signature("garbage") is None
    assert parse_strategy_signature("only:two:parts") is None


# ---------------------------------------------------------------------------
# Phase 2 ancestry rules (FR-CL2-*)
# ---------------------------------------------------------------------------

def test_cisd_clusters_with_unicorn():
    assert can_cluster_together("14_cisd", "01_unicorn") is True


def test_mmm_clusters_with_silver_bullet():
    assert can_cluster_together("09_mmm", "04_silver_bullet") is True


def test_bpr_cannot_cluster_with_unicorn():
    assert can_cluster_together("15_bpr_ob", "01_unicorn") is False


def test_bpr_cannot_cluster_with_confirmation():
    assert can_cluster_together("15_bpr_ob", "03_confirmation") is False


def test_po3_clusters_with_judas():
    assert can_cluster_together("10_po3", "02_judas") is True


def test_judas_is_representative_over_po3():
    rep = select_representative(["10_po3", "02_judas"])
    assert rep == "02_judas"


def test_mmm_priority_below_silver_bullet():
    rep = select_representative(["09_mmm", "04_silver_bullet"])
    assert rep == "04_silver_bullet"


def test_unicorn_priority_over_mmm_and_cisd():
    rep = select_representative(["14_cisd", "09_mmm", "01_unicorn", "03_confirmation"])
    assert rep == "01_unicorn"


def test_nested_fvg_independent_root():
    assert can_cluster_together("05_nested_fvg", "01_unicorn") is False
    assert can_cluster_together("05_nested_fvg", "05_nested_fvg") is False


def test_ote_fvg_independent_root():
    assert can_cluster_together("07_ote_fvg", "04_silver_bullet") is False


def test_rejection_block_independent_root():
    assert can_cluster_together("08_rejection_block", "01_unicorn") is False


def test_vacuum_independent_root():
    assert can_cluster_together("12_vacuum", "03_confirmation") is False


def test_reclaimed_fvg_independent_root():
    assert can_cluster_together("13_reclaimed_fvg", "09_mmm") is False
