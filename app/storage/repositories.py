"""Typed upsert / read helpers for every table in the schema.

All functions accept a sqlite3.Connection so callers control transactions.
Datetimes are serialised to UTC ISO-8601 strings before persistence and
deserialised back on read.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(dt: datetime) -> str:
    """Render a datetime as UTC ISO-8601 string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


# ---------------------------------------------------------------------------
# Candles
# ---------------------------------------------------------------------------

def upsert_candle(
    conn: sqlite3.Connection,
    instrument: str,
    timeframe: str,
    t: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    v: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO candles (instrument, timeframe, t, o, h, l, c, v)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument, timeframe, t) DO NOTHING
        """,
        (instrument, timeframe, _ts(t), o, h, l, c, v),
    )


def get_candles(
    conn: sqlite3.Connection,
    instrument: str,
    timeframe: str,
    since: datetime | None = None,
    limit: int = 500,
) -> list[dict]:
    if since:
        rows = conn.execute(
            "SELECT * FROM candles WHERE instrument=? AND timeframe=? AND t>=? ORDER BY t DESC LIMIT ?",
            (instrument, timeframe, _ts(since), limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM candles WHERE instrument=? AND timeframe=? ORDER BY t DESC LIMIT ?",
            (instrument, timeframe, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in reversed(rows)]


def get_latest_candle_time(
    conn: sqlite3.Connection,
    instrument: str,
    timeframe: str,
) -> datetime | None:
    row = conn.execute(
        "SELECT MAX(t) AS mt FROM candles WHERE instrument=? AND timeframe=?",
        (instrument, timeframe),
    ).fetchone()
    if row and row["mt"]:
        return datetime.fromisoformat(row["mt"]).replace(tzinfo=timezone.utc)
    return None


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def insert_event(
    conn: sqlite3.Connection,
    t: datetime,
    instrument: str,
    timeframe: str,
    event_type: str,
    direction: str | None,
    payload: dict,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO events (t, instrument, timeframe, event_type, direction, payload)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _ts(t),
            instrument,
            timeframe,
            event_type,
            direction,
            json.dumps(payload),
        ),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_events(
    conn: sqlite3.Connection,
    instrument: str,
    event_types: list[str] | None = None,
    since: datetime | None = None,
    limit: int = 200,
) -> list[dict]:
    clauses = ["instrument = ?"]
    params: list[Any] = [instrument]
    if event_types:
        placeholders = ",".join("?" * len(event_types))
        clauses.append(f"event_type IN ({placeholders})")
        params.extend(event_types)
    if since:
        clauses.append("t >= ?")
        params.append(_ts(since))
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY t DESC LIMIT ?",
        params,
    ).fetchall()
    result = []
    for r in reversed(rows):
        d = _row_to_dict(r)
        d["payload"] = json.loads(d["payload"])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def insert_signal(
    conn: sqlite3.Connection,
    *,
    t: datetime,
    strategy_id: str,
    verdict: str,
    confidence: float,
    probability: float = 0.0,
    direction: str | None = None,
    entry: float | None = None,
    sl: float | None = None,
    tp1: float | None = None,
    tp2: float | None = None,
    tp3: float | None = None,
    rr: float | None = None,
    signature: str | None = None,
    gate_result: str = "pending",
    payload: dict | None = None,
) -> int | None:
    try:
        cur = conn.execute(
            """
            INSERT INTO signals
                (t, strategy_id, verdict, confidence, probability, direction,
                 entry, sl, tp1, tp2, tp3, rr, signature, gate_result, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _ts(t),
                strategy_id,
                verdict,
                confidence,
                probability,
                direction,
                entry,
                sl,
                tp1,
                tp2,
                tp3,
                rr,
                signature,
                gate_result,
                json.dumps(payload or {}),
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]
    except sqlite3.IntegrityError:
        return None  # duplicate signature — idempotency guard


def update_signal_gate(conn: sqlite3.Connection, signal_id: int, gate_result: str) -> None:
    conn.execute(
        "UPDATE signals SET gate_result=? WHERE id=?",
        (gate_result, signal_id),
    )


def get_signal(conn: sqlite3.Connection, signal_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
    if not row:
        return None
    d = _row_to_dict(row)
    d["payload"] = json.loads(d["payload"])
    return d


def get_signals(
    conn: sqlite3.Connection,
    strategy_id: str | None = None,
    verdict: str | None = None,
    gate_result: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if strategy_id:
        clauses.append("strategy_id=?")
        params.append(strategy_id)
    if verdict:
        clauses.append("verdict=?")
        params.append(verdict)
    if gate_result:
        clauses.append("gate_result=?")
        params.append(gate_result)
    if since:
        clauses.append("t>=?")
        params.append(_ts(since))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM signals {where} ORDER BY t DESC LIMIT ?",
        params,
    ).fetchall()
    result = []
    for r in rows:
        d = _row_to_dict(r)
        d["payload"] = json.loads(d["payload"])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Agent scores
# ---------------------------------------------------------------------------

def insert_agent_score(
    conn: sqlite3.Connection,
    signal_id: int,
    agent_id: str,
    score: float,
    verdict: str,
    reasons: list[str],
    evidence: dict,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO agent_scores
            (signal_id, agent_id, score, verdict, reasons, evidence)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (signal_id, agent_id, score, verdict, json.dumps(reasons), json.dumps(evidence)),
    )


def get_agent_scores(conn: sqlite3.Connection, signal_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM agent_scores WHERE signal_id=?",
        (signal_id,),
    ).fetchall()
    result = []
    for r in rows:
        d = _row_to_dict(r)
        d["reasons"] = json.loads(d["reasons"])
        d["evidence"] = json.loads(d["evidence"])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

def insert_cluster(
    conn: sqlite3.Connection,
    t: datetime,
    signature: str,
    representative_signal_id: int,
    member_signal_ids: list[int],
    boosted_confidence: float,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO clusters
            (t, signature, representative_signal_id, member_signal_ids, boosted_confidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        (_ts(t), signature, representative_signal_id, json.dumps(member_signal_ids), boosted_confidence),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_cluster(conn: sqlite3.Connection, cluster_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM clusters WHERE id=?", (cluster_id,)).fetchone()
    if not row:
        return None
    d = _row_to_dict(row)
    d["member_signal_ids"] = json.loads(d["member_signal_ids"])
    return d


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def insert_trade(
    conn: sqlite3.Connection,
    *,
    signal_id: int,
    cluster_id: int | None,
    published_t: datetime,
    strategy_id: str,
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float | None = None,
    tp3: float | None = None,
    rr_planned: float,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO trades
            (signal_id, cluster_id, published_t, strategy_id, direction,
             entry, sl, tp1, tp2, tp3, rr_planned)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_id,
            cluster_id,
            _ts(published_t),
            strategy_id,
            direction,
            entry,
            sl,
            tp1,
            tp2,
            tp3,
            rr_planned,
        ),
    )
    return cur.lastrowid  # type: ignore[return-value]


def update_trade_narrative(conn: sqlite3.Connection, trade_id: int, narrative: str) -> None:
    conn.execute("UPDATE trades SET narrative=? WHERE id=?", (narrative, trade_id))


def update_trade_outcome(
    conn: sqlite3.Connection,
    trade_id: int,
    outcome: str,
    outcome_t: datetime,
    realized_r: float | None = None,
    execution_status: str | None = None,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE trades
        SET outcome=?, outcome_t=?, realized_r=?, execution_status=?, notes=?
        WHERE id=?
        """,
        (outcome, _ts(outcome_t), realized_r, execution_status, notes, trade_id),
    )


def get_trade(conn: sqlite3.Connection, trade_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_open_trades(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM trades WHERE outcome='open' ORDER BY published_t",
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Strategy stats
# ---------------------------------------------------------------------------

def upsert_strategy_stats(
    conn: sqlite3.Connection,
    strategy_id: str,
    trades_30d: int,
    wins_30d: int,
    win_rate_30d: float,
    avg_rr_30d: float,
    expectancy_30d: float,
    trades_alltime: int,
    last_updated: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO strategy_stats
            (strategy_id, trades_30d, wins_30d, win_rate_30d, avg_rr_30d,
             expectancy_30d, trades_alltime, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(strategy_id) DO UPDATE SET
            trades_30d=excluded.trades_30d,
            wins_30d=excluded.wins_30d,
            win_rate_30d=excluded.win_rate_30d,
            avg_rr_30d=excluded.avg_rr_30d,
            expectancy_30d=excluded.expectancy_30d,
            trades_alltime=excluded.trades_alltime,
            last_updated=excluded.last_updated
        """,
        (
            strategy_id,
            trades_30d,
            wins_30d,
            win_rate_30d,
            avg_rr_30d,
            expectancy_30d,
            trades_alltime,
            _ts(last_updated),
        ),
    )


def get_all_strategy_stats(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM strategy_stats ORDER BY strategy_id").fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def upsert_calendar_event(
    conn: sqlite3.Connection,
    t: datetime,
    currency: str,
    event_name: str,
    impact: str,
    actual: str | None,
    forecast: str | None,
    previous: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO calendar (t, currency, event_name, impact, actual, forecast, previous)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(t, currency, event_name) DO UPDATE SET
            impact=excluded.impact,
            actual=excluded.actual,
            forecast=excluded.forecast,
            previous=excluded.previous
        """,
        (_ts(t), currency, event_name, impact, actual, forecast, previous),
    )


def get_upcoming_high_impact(
    conn: sqlite3.Connection,
    after: datetime,
    currencies: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    currencies = currencies or ["USD", "EUR"]
    placeholders = ",".join("?" * len(currencies))
    rows = conn.execute(
        f"""
        SELECT * FROM calendar
        WHERE t >= ? AND currency IN ({placeholders}) AND impact='high'
        ORDER BY t
        LIMIT ?
        """,
        (_ts(after), *currencies, limit),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Settings (KV)
# ---------------------------------------------------------------------------

def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
