"""Strategy stats — rolling 30d and all-time win rate, avg RR, expectancy (FR-P-05/06/07)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.storage import db as _db
from app.storage.repositories import upsert_strategy_stats

log = logging.getLogger(__name__)


def recompute_strategy_stats(strategy_id: str, db_path=_db.DB_PATH) -> None:
    with _db.get_connection(db_path) as conn:
        now = datetime.now(tz=timezone.utc)
        cutoff_30d = (now - timedelta(days=30)).isoformat()

        rows_30d = conn.execute(
            """
            SELECT outcome, realized_r FROM trades
            WHERE strategy_id=? AND outcome NOT IN ('open','manual_close')
            AND published_t >= ? AND execution_status != 'skipped'
            """,
            (strategy_id, cutoff_30d),
        ).fetchall()

        rows_all = conn.execute(
            """
            SELECT outcome, realized_r FROM trades
            WHERE strategy_id=? AND outcome NOT IN ('open','manual_close')
            AND execution_status != 'skipped'
            """,
            (strategy_id,),
        ).fetchall()

        stats_30d = _calc(rows_30d)
        stats_all = _calc(rows_all)

        upsert_strategy_stats(
            conn,
            strategy_id=strategy_id,
            trades_30d=stats_30d["trades"],
            wins_30d=stats_30d["wins"],
            win_rate_30d=stats_30d["win_rate"],
            avg_rr_30d=stats_30d["avg_rr"],
            expectancy_30d=stats_30d["expectancy"],
            trades_alltime=stats_all["trades"],
            last_updated=now,
        )
        conn.commit()

        # FR-P-07: flag negative expectancy if ≥ 50 outcomes (logged, not auto-disabled)
        if stats_all["trades"] >= 50 and stats_30d["expectancy"] < 0:
            log.warning(
                "strategy flagged: negative expectancy",
                extra={"strategy": strategy_id, "expectancy": stats_30d["expectancy"]},
            )


def _calc(rows) -> dict:
    trades = len(rows)
    if not trades:
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "avg_rr": 0.0, "expectancy": 0.0}

    wins = sum(1 for r in rows if r["outcome"] in ("tp1_hit", "tp2_hit"))
    rr_vals = [r["realized_r"] for r in rows if r["realized_r"] is not None]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 3) if rr_vals else 0.0
    win_rate = round(wins / trades, 4)
    expectancy = round(win_rate * avg_rr - (1 - win_rate), 3)

    return {"trades": trades, "wins": wins, "win_rate": win_rate, "avg_rr": avg_rr, "expectancy": expectancy}


def recompute_all_strategies(db_path=_db.DB_PATH) -> None:
    with _db.get_connection(db_path) as conn:
        strategy_ids = [r[0] for r in conn.execute("SELECT DISTINCT strategy_id FROM trades").fetchall()]
    for sid in strategy_ids:
        recompute_strategy_stats(sid, db_path)
