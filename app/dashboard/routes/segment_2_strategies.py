"""Segment 2 — Strategy cards (FR-UI-03)."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, render_template

from app.storage import db as _db
from app.storage.repositories import get_signals, get_upcoming_high_impact

seg2_bp = Blueprint("seg2", __name__)

STRATEGY_NAMES = {
    "01_unicorn": "Unicorn Model",
    "02_judas": "Judas Swing",
    "03_confirmation": "Confirmation Model",
    "04_silver_bullet": "Silver Bullet",
    "06_ifvg": "Inverse FVG",
}


@seg2_bp.route("/strategies")
def strategies():
    now = datetime.now(tz=timezone.utc)

    with _db.get_connection() as conn:
        # Last signal per strategy
        cards = []
        for sid, sname in STRATEGY_NAMES.items():
            sigs = get_signals(conn, strategy_id=sid, limit=10)
            published = [s for s in sigs if s["gate_result"] == "published"]
            last_sig = published[0] if published else None
            # Most recent signal with computed levels (for "watching" display)
            watching = next((s for s in sigs if s.get("entry") is not None), None)
            # Last 10 verdicts for dot display
            last_10 = sigs[:10]
            cards.append({
                "strategy_id": sid,
                "strategy_name": sname,
                "last_signal": last_sig,
                "watching": watching,
                "last_10": last_10,
            })

        # Calendar ticker (FR-UI-06)
        upcoming_events = get_upcoming_high_impact(conn, after=now, limit=5)

    return render_template(
        "segment_2.html",
        cards=cards,
        upcoming_events=upcoming_events,
        now=now,
    )
