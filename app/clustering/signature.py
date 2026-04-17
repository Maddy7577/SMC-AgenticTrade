"""Canonical signal signature — used for clustering (FR-CL-01)."""

from __future__ import annotations

from datetime import datetime, timezone


def round_to_bucket(value: float, pip_size: float = 0.0001, pips: float = 5) -> float:
    """Round a price to the nearest N-pip bucket."""
    bucket = pip_size * pips
    return round(round(value / bucket) * bucket, 5)


def time_bucket_5min(t: datetime) -> str:
    """Return UTC time truncated to the nearest 5-minute boundary as ISO string."""
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    t_utc = t.astimezone(timezone.utc)
    floored = t_utc.replace(minute=(t_utc.minute // 5) * 5, second=0, microsecond=0)
    return floored.isoformat()


def build_cluster_key(
    t: datetime,
    direction: str,
    sweep_level: float,
    mss_level: float,
    entry_midpoint: float,
) -> str:
    """Build the canonical cluster key string (FR-CL-01)."""
    tb = time_bucket_5min(t)
    s = round_to_bucket(sweep_level)
    m = round_to_bucket(mss_level)
    e = round_to_bucket(entry_midpoint)
    return f"{tb}|{direction}|{s}|{m}|{e}"


def parse_strategy_signature(sig: str) -> dict | None:
    """Parse the per-strategy signature string into components."""
    parts = sig.split(":")
    if len(parts) != 5:
        return None
    return {
        "strategy_id": parts[0],
        "direction": parts[1],
        "sweep_level": float(parts[2]),
        "mss_level": float(parts[3]),
        "entry_midpoint": float(parts[4]),
    }
