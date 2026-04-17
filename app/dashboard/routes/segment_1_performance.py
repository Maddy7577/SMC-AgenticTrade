"""Segment 1 — Performance view (FR-UI-02)."""

from __future__ import annotations

from flask import Blueprint, render_template

from app.storage import db as _db
from app.storage.repositories import get_all_strategy_stats

seg1_bp = Blueprint("seg1", __name__)


@seg1_bp.route("/")
def performance():
    with _db.get_connection() as conn:
        stats = get_all_strategy_stats(conn)
        trades = conn.execute(
            "SELECT * FROM trades ORDER BY published_t DESC LIMIT 200"
        ).fetchall()
        trades = [dict(t) for t in trades]

    return render_template("segment_1.html", stats=stats, trades=trades)
