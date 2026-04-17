"""Unit tests for Decision Gate — one test per veto rule (J5)."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.gate.decision_gate import GateDecision, evaluate_signal
from app.storage.db import _SCHEMA_SQL, bootstrap

# ---------------------------------------------------------------------------
# Temp DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a Path to a bootstrapped temporary SQLite DB."""
    db_path = tmp_path / "test_smc.db"
    bootstrap(db_path)
    return db_path


def _insert_signal(
    db_path: Path,
    *,
    verdict: str = "VALID",
    confidence: float = 80.0,
    rr: float = 2.5,
    t: str | None = None,
    strategy_id: str = "03_confirmation",
) -> int:
    """Insert a minimal signal row and return its id."""
    if t is None:
        t = datetime.now(tz=timezone.utc).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.execute(
        """INSERT INTO signals
           (t, strategy_id, verdict, confidence, probability, direction,
            entry, sl, tp1, rr, gate_result)
           VALUES (?, ?, ?, ?, 0.5, 'buy', 1.10000, 1.09900, 1.10250, ?, 'pending')""",
        (t, strategy_id, verdict, confidence, rr),
    )
    conn.commit()
    sig_id = cur.lastrowid
    conn.close()
    return sig_id


# ---------------------------------------------------------------------------
# Veto 1 — Monday
# ---------------------------------------------------------------------------

def test_monday_veto(tmp_db):
    sig_id = _insert_signal(tmp_db)
    monday_ist = datetime(2026, 4, 13, 10, 0, 0, tzinfo=timezone.utc)  # known Monday UTC
    with patch("app.gate.decision_gate.datetime") as mock_dt:
        mock_dt.now.return_value = monday_ist
        mock_dt.fromisoformat.side_effect = datetime.fromisoformat
        result = evaluate_signal(sig_id, db_path=tmp_db)
    assert result.published is False
    assert "monday" in result.reason


# ---------------------------------------------------------------------------
# Veto 5 — Confidence below threshold
# ---------------------------------------------------------------------------

def test_confidence_74_vetoed(tmp_db):
    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=74.9)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert result.published is False
    assert "confidence" in result.reason


def test_confidence_75_passes(tmp_db):
    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=75.0, rr=2.5)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    # Should not be vetoed by confidence (may pass or fail other vetoes)
    assert "confidence" not in result.reason


def test_wait_confidence_64_vetoed(tmp_db):
    sig_id = _insert_signal(tmp_db, verdict="WAIT", confidence=64.9)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert result.published is False
    assert "confidence" in result.reason


def test_wait_confidence_65_passes_confidence_veto(tmp_db):
    sig_id = _insert_signal(tmp_db, verdict="WAIT", confidence=65.0)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert "confidence" not in result.reason


# ---------------------------------------------------------------------------
# Veto 6 — RR below floor
# ---------------------------------------------------------------------------

def test_rr_19_vetoed(tmp_db):
    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=80.0, rr=1.9)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert result.published is False
    assert "rr" in result.reason


def test_rr_20_passes_rr_veto(tmp_db):
    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=80.0, rr=2.0)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert "rr" not in result.reason


# ---------------------------------------------------------------------------
# Veto 7 — Spread too wide
# ---------------------------------------------------------------------------

def test_spread_too_wide_vetoed(tmp_db):
    from config.settings import MAX_SPREAD_PIPS
    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=80.0, rr=2.5)
    result = evaluate_signal(sig_id, current_spread_pips=MAX_SPREAD_PIPS + 1, db_path=tmp_db)
    assert result.published is False
    assert "spread" in result.reason


# ---------------------------------------------------------------------------
# Veto 8 — Post-SL cooling
# ---------------------------------------------------------------------------

def test_cooling_period_veto(tmp_db):
    from app.storage.db import get_connection
    from app.storage.repositories import set_setting
    from config.settings import POST_STOPLOSS_COOLING_MINUTES

    # Record a stop-loss hit 5 minutes ago (within cooling window)
    recent_sl = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
    with get_connection(tmp_db) as conn:
        set_setting(conn, "last_stoploss_t", recent_sl)
        conn.commit()

    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=80.0, rr=2.5)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert result.published is False
    assert "cooling" in result.reason


def test_cooling_expired_does_not_veto(tmp_db):
    from app.storage.db import get_connection
    from app.storage.repositories import set_setting
    from config.settings import POST_STOPLOSS_COOLING_MINUTES

    # Stop-loss hit well outside the cooling window
    old_sl = (datetime.now(tz=timezone.utc) - timedelta(minutes=POST_STOPLOSS_COOLING_MINUTES + 5)).isoformat()
    with get_connection(tmp_db) as conn:
        set_setting(conn, "last_stoploss_t", old_sl)
        conn.commit()

    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=80.0, rr=2.5)
    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert "cooling" not in result.reason


# ---------------------------------------------------------------------------
# Signal not found
# ---------------------------------------------------------------------------

def test_nonexistent_signal_id_vetoed(tmp_db):
    result = evaluate_signal(99999, db_path=tmp_db)
    assert result.published is False
    assert "not_found" in result.reason


# ---------------------------------------------------------------------------
# Daily losses veto (Veto 3)
# ---------------------------------------------------------------------------

def test_daily_losses_veto(tmp_db):
    from app.storage.db import get_connection
    from config.settings import MAX_DAILY_LOSSES

    # Insert MAX_DAILY_LOSSES sl_hit trades today
    today = datetime.now(tz=timezone.utc).isoformat()
    sig_id = _insert_signal(tmp_db, verdict="VALID", confidence=80.0, rr=2.5)

    with get_connection(tmp_db) as conn:
        for _ in range(MAX_DAILY_LOSSES):
            conn.execute(
                """INSERT INTO trades
                   (signal_id, published_t, strategy_id, direction, entry, sl, tp1,
                    rr_planned, outcome, outcome_t)
                   VALUES (?, ?, '03_confirmation', 'buy', 1.1, 1.099, 1.105, 2.0, 'sl_hit', ?)""",
                (sig_id, today, today),
            )
        conn.commit()

    result = evaluate_signal(sig_id, db_path=tmp_db)
    assert result.published is False
    assert "daily_losses" in result.reason
