"""Segment 1 — Performance view (FR-UI-02) + Strategy Settings API."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from app.storage import db as _db
from app.storage.repositories import (
    ALL_STRATEGY_META,
    get_all_strategy_stats,
    get_strategy_overrides,
    set_strategy_override,
)

seg1_bp = Blueprint("seg1", __name__)


@seg1_bp.route("/")
def performance():
    with _db.get_connection() as conn:
        stats_rows = get_all_strategy_stats(conn)
        trades = conn.execute(
            "SELECT * FROM trades ORDER BY published_t DESC LIMIT 200"
        ).fetchall()
        trades = [dict(t) for t in trades]
        overrides = get_strategy_overrides(conn)

    # Build a stats dict keyed by strategy_id for quick lookup
    stats_map = {s["strategy_id"]: s for s in stats_rows}

    # Full 15-row leaderboard: merge known strategies with recorded stats
    full_stats = []
    for sid, _name in ALL_STRATEGY_META:
        row = stats_map.get(sid) or {
            "strategy_id": sid,
            "trades_30d": 0,
            "win_rate_30d": 0.0,
            "avg_rr_30d": 0.0,
            "expectancy_30d": 0.0,
            "trades_alltime": 0,
        }
        row["disabled"] = not overrides.get(sid, {}).get("enabled", True)
        full_stats.append(row)

    return render_template(
        "segment_1.html",
        stats=full_stats,
        trades=trades,
        overrides=overrides,
    )


@seg1_bp.route("/api/strategy-settings", methods=["GET"])
def get_settings():
    with _db.get_connection() as conn:
        overrides = get_strategy_overrides(conn)
    return jsonify(overrides)


@seg1_bp.route("/api/strategy-settings", methods=["POST"])
def save_settings():
    data = request.get_json(force=True) or {}
    with _db.get_connection() as conn:
        for sid, vals in data.items():
            enabled = bool(vals.get("enabled", True))
            raw_threshold = vals.get("threshold")
            threshold: float | None = None
            if raw_threshold not in (None, "", "null"):
                try:
                    threshold = float(raw_threshold)
                except (ValueError, TypeError):
                    pass
            set_strategy_override(conn, sid, enabled, threshold)
        conn.commit()
    return jsonify({"ok": True})
