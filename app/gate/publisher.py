"""Publish fanout — after gate passes, writes trade, triggers narrative, pushes SSE (FR-G-10)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.storage import db as _db
from app.storage.repositories import (
    get_agent_scores,
    get_signal,
    insert_trade,
    update_trade_narrative,
)

log = logging.getLogger(__name__)


def publish_signal(
    signal_id: int,
    cluster_id: int | None = None,
    db_path=_db.DB_PATH,
) -> int | None:
    """Create a trade record, generate narrative async, push SSE. Returns trade_id."""
    with _db.get_connection(db_path) as conn:
        signal = get_signal(conn, signal_id)
        if not signal:
            return None
        if signal["verdict"] == "NO_TRADE":
            return None

        now = datetime.now(tz=timezone.utc)
        trade_id = insert_trade(
            conn,
            signal_id=signal_id,
            cluster_id=cluster_id,
            published_t=now,
            strategy_id=signal["strategy_id"],
            direction=signal["direction"] or "buy",
            entry=signal["entry"] or 0.0,
            sl=signal["sl"] or 0.0,
            tp1=signal["tp1"] or 0.0,
            tp2=signal.get("tp2"),
            tp3=signal.get("tp3"),
            rr_planned=signal.get("rr") or 0.0,
        )
        conn.commit()

    log.info("signal published", extra={"signal_id": signal_id, "trade_id": trade_id})

    # Async narrative (fire-and-forget in thread)
    _request_narrative_async(signal_id, trade_id, db_path)

    # SSE push
    from app.dashboard.routes.sse import push_signal_event
    push_signal_event(signal_id, signal["verdict"], signal["strategy_id"])

    # Telegram alert
    from app.notifications.telegram import send_signal_alert
    from app.storage.repositories import ALL_STRATEGY_META
    _meta_map = dict(ALL_STRATEGY_META)
    strategy_name = _meta_map.get(signal["strategy_id"], signal["strategy_id"])
    send_signal_alert(
        verdict=signal["verdict"],
        strategy_name=strategy_name,
        direction=signal.get("direction"),
        entry=signal.get("entry"),
        sl=signal.get("sl"),
        tp1=signal.get("tp1"),
        rr=signal.get("rr"),
        confidence=signal.get("confidence"),
    )

    return trade_id


def _request_narrative_async(signal_id: int, trade_id: int, db_path) -> None:
    import threading
    threading.Thread(
        target=_generate_narrative,
        args=(signal_id, trade_id, db_path),
        daemon=True,
    ).start()


def _generate_narrative(signal_id: int, trade_id: int, db_path) -> None:
    try:
        with _db.get_connection(db_path) as conn:
            signal = get_signal(conn, signal_id)
            agents = get_agent_scores(conn, signal_id)

        if not signal:
            return

        from app.narrative.gemini_client import generate_narrative

        trade_params = {
            "direction": signal.get("direction"),
            "entry": signal.get("entry"),
            "sl": signal.get("sl"),
            "tp1": signal.get("tp1"),
            "tp2": signal.get("tp2"),
            "rr": signal.get("rr"),
        }
        narrative = generate_narrative(
            strategy_name=signal["strategy_id"],
            rules_summary="SMC strategy with liquidity sweep, MSS, and FVG confirmation",
            evidence=signal.get("payload", {}),
            agent_scores=agents,
            trade_params=trade_params,
            signal_t=datetime.fromisoformat(signal["t"]).replace(tzinfo=timezone.utc) if signal.get("t") else None,
        )

        with _db.get_connection(db_path) as conn:
            update_trade_narrative(conn, trade_id, narrative)
            conn.commit()

        log.info("narrative generated", extra={"trade_id": trade_id})
    except Exception as exc:
        log.warning("narrative generation failed", extra={"trade_id": trade_id, "error": str(exc)})
