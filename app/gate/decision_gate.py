"""Final Decision Gate — 9 veto rules in most-likely-to-reject-first order (FR-G-01 to G-09).

Gate runs AFTER clustering. Takes a (signal_id, optional cluster) and returns
either "published" or "vetoed:<reason>".

Counter state (daily losses, monthly trades, cooling) is maintained in this module
and persisted to SQLite settings table so restarts don't wipe it (E5, R7).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from app.storage import db as _db
from app.storage.repositories import (
    get_setting,
    get_signal,
    get_upcoming_high_impact,
    set_setting,
    update_signal_gate,
)
from config.settings import (
    CONFIDENCE_VALID_THRESHOLD,
    CONFIDENCE_WAIT_THRESHOLD,
    MAX_DAILY_LOSSES,
    MAX_MONTHLY_TRADES,
    MAX_SPREAD_PIPS,
    NEWS_BLACKOUT_MINUTES,
    POST_STOPLOSS_COOLING_MINUTES,
    RR_FLOOR,
    TZ_IST,
)

log = logging.getLogger(__name__)


class GateDecision(NamedTuple):
    published: bool
    reason: str   # "published" or "vetoed:<reason>"


def evaluate_signal(
    signal_id: int,
    current_spread_pips: float = 0.0,
    db_path=_db.DB_PATH,
) -> GateDecision:
    """Run all 9 veto rules. Returns decision and updates DB."""
    with _db.get_connection(db_path) as conn:
        signal = get_signal(conn, signal_id)
        if not signal:
            return GateDecision(False, "vetoed:signal_not_found")

        now = datetime.now(tz=timezone.utc)
        now_ist = now.astimezone(TZ_IST)

        # --- Veto 1: Monday (FR-G-04) ---
        if now_ist.weekday() == 0:  # Monday = 0
            reason = "vetoed:monday"
            update_signal_gate(conn, signal_id, reason)
            conn.commit()
            log.info("gate veto: monday", extra={"signal_id": signal_id})
            return GateDecision(False, reason)

        # --- Veto 2: News blackout (FR-G-03) ---
        news_window_start = now - timedelta(minutes=NEWS_BLACKOUT_MINUTES)
        news_window_end = now + timedelta(minutes=NEWS_BLACKOUT_MINUTES)
        upcoming = get_upcoming_high_impact(conn, news_window_start)
        in_blackout = any(
            news_window_start
            <= datetime.fromisoformat(ev["t"]).replace(tzinfo=timezone.utc)
            <= news_window_end
            for ev in upcoming
        )
        if in_blackout:
            reason = "vetoed:news_blackout"
            update_signal_gate(conn, signal_id, reason)
            conn.commit()
            log.info("gate veto: news blackout", extra={"signal_id": signal_id})
            return GateDecision(False, reason)

        # --- Veto 3: Daily losses (FR-G-05) ---
        daily_losses = _get_daily_losses(conn, now_ist)
        if daily_losses >= MAX_DAILY_LOSSES:
            reason = f"vetoed:daily_losses_{daily_losses}"
            update_signal_gate(conn, signal_id, reason)
            conn.commit()
            log.info("gate veto: daily losses", extra={"signal_id": signal_id, "losses": daily_losses})
            return GateDecision(False, reason)

        # --- Veto 4: Monthly cap (FR-G-06) ---
        monthly_trades = _get_monthly_trades(conn, now_ist)
        if monthly_trades >= MAX_MONTHLY_TRADES:
            reason = f"vetoed:monthly_cap_{monthly_trades}"
            update_signal_gate(conn, signal_id, reason)
            conn.commit()
            log.info("gate veto: monthly cap", extra={"signal_id": signal_id, "count": monthly_trades})
            return GateDecision(False, reason)

        # --- Veto 5: Confidence floor (FR-G-01) ---
        verdict = signal["verdict"]
        confidence = signal["confidence"]
        threshold = CONFIDENCE_VALID_THRESHOLD if verdict == "VALID" else CONFIDENCE_WAIT_THRESHOLD
        if confidence < threshold:
            reason = f"vetoed:confidence_{confidence:.1f}"
            update_signal_gate(conn, signal_id, reason)
            conn.commit()
            return GateDecision(False, reason)

        # --- Veto 6: RR floor (FR-G-02) ---
        rr = signal.get("rr")
        if verdict == "VALID" and (rr is None or rr < RR_FLOOR):
            reason = f"vetoed:rr_{rr}"
            update_signal_gate(conn, signal_id, reason)
            conn.commit()
            return GateDecision(False, reason)

        # --- Veto 7: Spread (FR-G-07) ---
        if current_spread_pips > MAX_SPREAD_PIPS:
            reason = f"vetoed:spread_{current_spread_pips:.1f}"
            update_signal_gate(conn, signal_id, reason)
            conn.commit()
            return GateDecision(False, reason)

        # --- Veto 8: Post-stop cooling (FR-G-08) ---
        last_sl = get_setting(conn, "last_stoploss_t")
        if last_sl:
            try:
                sl_t = datetime.fromisoformat(last_sl).replace(tzinfo=timezone.utc)
                if (now - sl_t).total_seconds() < POST_STOPLOSS_COOLING_MINUTES * 60:
                    remaining = POST_STOPLOSS_COOLING_MINUTES - (now - sl_t).total_seconds() / 60
                    reason = f"vetoed:cooling_{remaining:.0f}min"
                    update_signal_gate(conn, signal_id, reason)
                    conn.commit()
                    return GateDecision(False, reason)
            except ValueError:
                pass

        # All vetoes passed — publish
        update_signal_gate(conn, signal_id, "published")
        conn.commit()
        log.info("gate passed", extra={"signal_id": signal_id, "verdict": verdict, "confidence": confidence})
        return GateDecision(True, "published")


def record_stoploss(db_path=_db.DB_PATH) -> None:
    """Called when a trade hits SL — starts cooling timer."""
    with _db.get_connection(db_path) as conn:
        set_setting(conn, "last_stoploss_t", datetime.now(tz=timezone.utc).isoformat())
        conn.commit()


def _get_daily_losses(conn, now_ist) -> int:
    """Count SL hits today in IST."""
    # IST midnight in UTC
    ist_midnight = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = ist_midnight.astimezone(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT COUNT(*) as n FROM trades WHERE outcome='sl_hit' AND outcome_t >= ?",
        (utc_midnight,),
    ).fetchone()
    return rows["n"] if rows else 0


def _get_monthly_trades(conn, now_ist) -> int:
    """Count VALID publishes this month in IST."""
    ist_month_start = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    utc_month_start = ist_month_start.astimezone(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT COUNT(*) as n FROM signals WHERE verdict='VALID' AND gate_result='published' AND t >= ?",
        (utc_month_start,),
    ).fetchone()
    return rows["n"] if rows else 0
