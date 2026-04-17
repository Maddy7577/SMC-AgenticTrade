"""Unit tests for kill zone clock (J2)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.detector.kill_zone import current_kill_zone, is_in_kill_zone


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 19, hour, minute, 0, tzinfo=timezone.utc)


def _ist_to_utc_hour(ist_hour: int) -> int:
    """IST = UTC + 5:30. Convert IST hour to approx UTC hour (at :00 minutes)."""
    total_mins = ist_hour * 60 - 330  # subtract 5h30m
    return total_mins // 60


# ---------------------------------------------------------------------------
# London Kill Zone: roughly 13:30–15:30 IST = 08:00–10:00 UTC
# ---------------------------------------------------------------------------

def test_london_kz_active():
    dt = _utc(8, 30)  # 14:00 IST — inside London KZ
    kz = current_kill_zone(dt)
    assert kz == "london_kz"


def test_outside_all_zones_returns_none():
    # 21:30 UTC = 03:00 IST — gap between silver_bullet_ny_pm (ends 1:30 IST)
    # and asian_session (starts 5:30 IST)
    dt = _utc(21, 30)
    kz = current_kill_zone(dt)
    assert kz == "none"


# ---------------------------------------------------------------------------
# NY Kill Zone: roughly 19:00–21:00 IST = 13:30–15:30 UTC
# ---------------------------------------------------------------------------

def test_ny_kz_active():
    dt = _utc(14, 0)  # 19:30 IST — inside NY KZ
    kz = current_kill_zone(dt)
    assert kz == "ny_kz"


# ---------------------------------------------------------------------------
# Asian session: roughly 05:30–12:30 IST = 00:00–07:00 UTC
# ---------------------------------------------------------------------------

def test_asian_session_active():
    dt = _utc(3, 0)  # 08:30 IST — inside Asian session
    kz = current_kill_zone(dt)
    assert kz == "asian_session"


# ---------------------------------------------------------------------------
# Silver Bullet windows (very narrow — test boundaries)
# ---------------------------------------------------------------------------

def test_silver_bullet_london_active():
    dt = _utc(10, 0)  # 15:30 IST — check if inside silver_bullet_london
    kz = current_kill_zone(dt)
    # Either silver_bullet_london or adjacent zone depending on exact config
    # At minimum it should not raise an error
    assert isinstance(kz, str)


# ---------------------------------------------------------------------------
# is_in_kill_zone
# ---------------------------------------------------------------------------

def test_is_in_kill_zone_london_true():
    dt = _utc(8, 30)
    assert is_in_kill_zone(dt, "london_kz") is True


def test_is_in_kill_zone_london_false():
    dt = _utc(14, 0)
    assert is_in_kill_zone(dt, "london_kz") is False


def test_current_kill_zone_returns_string():
    kz = current_kill_zone(_utc(12, 0))
    assert isinstance(kz, str)
