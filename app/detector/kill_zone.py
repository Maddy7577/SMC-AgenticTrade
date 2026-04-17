"""Kill zone clock — returns active session window for a given UTC datetime (FR-C-09).

All windows defined in config/settings.py as IST (UTC+5:30) hour/minute tuples.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from config.settings import KILL_ZONES_IST, TZ_IST

KillZoneLabel = Literal[
    "asian_session",
    "london_kz",
    "silver_bullet_london",
    "ny_kz",
    "silver_bullet_ny_am",
    "silver_bullet_ny_pm",
    "none",
]


def current_kill_zone(dt: datetime | None = None) -> KillZoneLabel:
    """Return the kill zone name active at dt (UTC). Returns 'none' if outside all windows."""
    if dt is None:
        dt = datetime.now(tz=timezone.utc)
    ist = dt.astimezone(TZ_IST)
    return _match_window(ist.hour, ist.minute)


def is_in_kill_zone(
    dt: datetime,
    zone: KillZoneLabel,
) -> bool:
    ist = dt.astimezone(TZ_IST)
    start, end = KILL_ZONES_IST[zone]
    return _in_range(ist.hour, ist.minute, start, end)


def _match_window(hour: int, minute: int) -> KillZoneLabel:
    for name, (start, end) in KILL_ZONES_IST.items():
        if _in_range(hour, minute, start, end):
            return name  # type: ignore[return-value]
    return "none"


def _in_range(
    hour: int,
    minute: int,
    start: tuple[int, int],
    end: tuple[int, int],
) -> bool:
    """Handle ranges that can cross midnight."""
    current_mins = hour * 60 + minute
    start_mins = start[0] * 60 + start[1]
    end_mins = end[0] * 60 + end[1]
    if start_mins <= end_mins:
        return start_mins <= current_mins <= end_mins
    # crosses midnight
    return current_mins >= start_mins or current_mins <= end_mins
