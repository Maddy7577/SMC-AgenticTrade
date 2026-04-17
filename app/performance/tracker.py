"""Performance tracker — monitors open trades and marks outcomes (FR-P-01/02)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.gate.decision_gate import record_stoploss
from app.storage import db as _db
from app.storage.repositories import get_open_trades, get_trade, update_trade_outcome

log = logging.getLogger(__name__)


def check_open_trades(current_prices: dict[str, float], db_path=_db.DB_PATH) -> None:
    """Poll live prices and auto-close open trades that have hit TP1/TP2/SL."""
    mid = current_prices.get("EUR_USD", 0.0)
    if not mid:
        return

    with _db.get_connection(db_path) as conn:
        open_trades = get_open_trades(conn)
        now = datetime.now(tz=timezone.utc)

        for trade in open_trades:
            direction = trade["direction"]
            tp1 = trade["tp1"]
            tp2 = trade.get("tp2")
            sl = trade["sl"]

            outcome = None
            if direction == "buy":
                if tp2 and mid >= tp2:
                    outcome = "tp2_hit"
                elif mid >= tp1:
                    outcome = "tp1_hit"
                elif mid <= sl:
                    outcome = "sl_hit"
            else:  # sell
                if tp2 and mid <= tp2:
                    outcome = "tp2_hit"
                elif mid <= tp1:
                    outcome = "tp1_hit"
                elif mid >= sl:
                    outcome = "sl_hit"

            if outcome:
                risk = abs(trade["entry"] - sl)
                reward = abs(mid - trade["entry"])
                realized_r = round(reward / risk, 2) if risk > 0 else 0.0
                if outcome == "sl_hit":
                    realized_r = -1.0

                update_trade_outcome(conn, trade["id"], outcome, now, realized_r)
                log.info(
                    "trade closed",
                    extra={
                        "trade_id": trade["id"],
                        "outcome": outcome,
                        "realized_r": realized_r,
                    },
                )
                if outcome == "sl_hit":
                    record_stoploss(db_path)

        conn.commit()


def mark_outcome(
    trade_id: int,
    outcome: str,
    outcome_t: datetime,
    realized_r: float | None = None,
    execution_status: str | None = None,
    notes: str | None = None,
    db_path=_db.DB_PATH,
) -> None:
    """Manual outcome override from dashboard (FR-P-03)."""
    with _db.get_connection(db_path) as conn:
        trade = get_trade(conn, trade_id)
        if not trade:
            return
        if realized_r is None and trade.get("entry") and trade.get("sl"):
            risk = abs(trade["entry"] - trade["sl"])
            if outcome == "sl_hit":
                realized_r = -1.0
            elif outcome in ("tp1_hit", "tp2_hit") and trade.get("tp1"):
                tp = trade["tp2"] if outcome == "tp2_hit" else trade["tp1"]
                reward = abs(tp - trade["entry"]) if tp else 0
                realized_r = round(reward / risk, 2) if risk > 0 else 0.0

        update_trade_outcome(conn, trade_id, outcome, outcome_t, realized_r, execution_status, notes)
        conn.commit()

    if outcome == "sl_hit":
        record_stoploss(db_path)

    # Trigger stats recompute
    from app.performance.stats import recompute_strategy_stats
    trade = None
    with _db.get_connection(db_path) as conn:
        trade = get_trade(conn, trade_id)
    if trade:
        recompute_strategy_stats(trade["strategy_id"], db_path)
