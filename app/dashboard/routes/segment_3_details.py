"""Segment 3 — Trade detail view (FR-UI-04)."""

from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request

from app.storage import db as _db
from app.storage.repositories import (
    get_agent_scores,
    get_cluster,
    get_signal,
    get_trade,
    update_trade_outcome,
)
from app.performance.tracker import mark_outcome

seg3_bp = Blueprint("seg3", __name__)


@seg3_bp.route("/signal/<int:signal_id>")
def signal_detail(signal_id: int):
    with _db.get_connection() as conn:
        signal = get_signal(conn, signal_id)
        if not signal:
            abort(404)
        agents = get_agent_scores(conn, signal_id)
        trade_row = conn.execute(
            "SELECT * FROM trades WHERE signal_id=? ORDER BY id DESC LIMIT 1",
            (signal_id,),
        ).fetchone()
        trade = dict(trade_row) if trade_row else None
        cluster = None
        if trade and trade.get("cluster_id"):
            cluster = get_cluster(conn, trade["cluster_id"])

    return render_template(
        "segment_3.html",
        signal=signal,
        agents=agents,
        trade=trade,
        cluster=cluster,
    )


@seg3_bp.route("/api/outcome/<int:trade_id>", methods=["POST"])
def record_outcome(trade_id: int):
    """Endpoint called by 'I took / I skipped' buttons (FR-P-03)."""
    data = request.get_json()
    if not data:
        abort(400)

    from datetime import datetime, timezone
    outcome = data.get("outcome", "manual_close")
    exec_status = data.get("execution_status")
    realized_r = data.get("realized_r")
    notes = data.get("notes")

    mark_outcome(
        trade_id=trade_id,
        outcome=outcome,
        outcome_t=datetime.now(tz=timezone.utc),
        realized_r=float(realized_r) if realized_r is not None else None,
        execution_status=exec_status,
        notes=notes,
    )
    return jsonify({"ok": True})
