"""SQLite schema, connection factory, and bootstrap migration.

WAL mode is enabled for concurrent dashboard reads + engine writes (NFR-R-03).
All timestamps are stored as UTC ISO-8601 strings (TEXT affinity in SQLite).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("data/smc.db")

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------ candles
CREATE TABLE IF NOT EXISTS candles (
    instrument  TEXT    NOT NULL,
    timeframe   TEXT    NOT NULL,
    t           TEXT    NOT NULL,   -- UTC ISO-8601
    o           REAL    NOT NULL,
    h           REAL    NOT NULL,
    l           REAL    NOT NULL,
    c           REAL    NOT NULL,
    v           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (instrument, timeframe, t)
);

-- ------------------------------------------------------------------ events
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    t           TEXT    NOT NULL,
    instrument  TEXT    NOT NULL,
    timeframe   TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    direction   TEXT,
    payload     TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_t ON events (t);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (instrument, event_type);

-- ------------------------------------------------------------------ signals
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    t               TEXT    NOT NULL,
    strategy_id     TEXT    NOT NULL,
    verdict         TEXT    NOT NULL,   -- VALID / WAIT / NO_TRADE
    confidence      REAL    NOT NULL,
    probability     REAL    NOT NULL DEFAULT 0,
    direction       TEXT,               -- buy / sell / null
    entry           REAL,
    sl              REAL,
    tp1             REAL,
    tp2             REAL,
    tp3             REAL,
    rr              REAL,
    signature       TEXT,
    gate_result     TEXT    NOT NULL DEFAULT 'pending',
    payload         TEXT    NOT NULL DEFAULT '{}',
    UNIQUE (strategy_id, signature, t)  -- idempotency guard (NFR-R-02)
);
CREATE INDEX IF NOT EXISTS idx_signals_t ON signals (t);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals (strategy_id);

-- ---------------------------------------------------------------- agent_scores
CREATE TABLE IF NOT EXISTS agent_scores (
    signal_id   INTEGER NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    agent_id    TEXT    NOT NULL,   -- opp1 / opp2 / risk1 / risk2
    score       REAL    NOT NULL,
    verdict     TEXT    NOT NULL,   -- support / oppose / neutral
    reasons     TEXT    NOT NULL DEFAULT '[]',
    evidence    TEXT    NOT NULL DEFAULT '{}',
    PRIMARY KEY (signal_id, agent_id)
);

-- ----------------------------------------------------------------- clusters
CREATE TABLE IF NOT EXISTS clusters (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    t                       TEXT    NOT NULL,
    signature               TEXT    NOT NULL,
    representative_signal_id INTEGER NOT NULL REFERENCES signals(id),
    member_signal_ids       TEXT    NOT NULL DEFAULT '[]',
    boosted_confidence      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clusters_sig ON clusters (signature);

-- ------------------------------------------------------------------ trades
CREATE TABLE IF NOT EXISTS trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id           INTEGER NOT NULL REFERENCES signals(id),
    cluster_id          INTEGER REFERENCES clusters(id),
    published_t         TEXT    NOT NULL,
    strategy_id         TEXT    NOT NULL,
    direction           TEXT    NOT NULL,
    entry               REAL    NOT NULL,
    sl                  REAL    NOT NULL,
    tp1                 REAL    NOT NULL,
    tp2                 REAL,
    tp3                 REAL,
    rr_planned          REAL    NOT NULL,
    narrative           TEXT,
    execution_status    TEXT,           -- taken / skipped / null
    outcome             TEXT    NOT NULL DEFAULT 'open',
    outcome_t           TEXT,
    realized_r          REAL,
    notes               TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_published ON trades (published_t);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades (strategy_id);
CREATE INDEX IF NOT EXISTS idx_trades_outcome ON trades (outcome);

-- -------------------------------------------------------------- strategy_stats
CREATE TABLE IF NOT EXISTS strategy_stats (
    strategy_id     TEXT    PRIMARY KEY,
    trades_30d      INTEGER NOT NULL DEFAULT 0,
    wins_30d        INTEGER NOT NULL DEFAULT 0,
    win_rate_30d    REAL    NOT NULL DEFAULT 0,
    avg_rr_30d      REAL    NOT NULL DEFAULT 0,
    expectancy_30d  REAL    NOT NULL DEFAULT 0,
    trades_alltime  INTEGER NOT NULL DEFAULT 0,
    last_updated    TEXT
);

-- --------------------------------------------------------------- calendar
CREATE TABLE IF NOT EXISTS calendar (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    t           TEXT    NOT NULL,
    currency    TEXT    NOT NULL,
    event_name  TEXT    NOT NULL,
    impact      TEXT    NOT NULL,   -- low / medium / high
    actual      TEXT,
    forecast    TEXT,
    previous    TEXT,
    UNIQUE (t, currency, event_name)
);
CREATE INDEX IF NOT EXISTS idx_calendar_t ON calendar (t);

-- ---------------------------------------------------------- settings (KV)
CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def bootstrap(db_path: Path = DB_PATH) -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    with get_connection(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
