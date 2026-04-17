"""Closed-candle poller.

Runs on a schedule (once per minute for M1, less often for higher TFs).
On startup: triggers backfill for any gaps since last stored candle.
On reconnect: called again to fill the gap caused by the disconnect.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from app.ingestion.oanda_client import OandaClient
from app.storage import db as _db
from app.storage.repositories import get_latest_candle_time, upsert_candle
from config.instruments import INSTRUMENTS, PRIMARY, SMT_PAIR
from config.settings import BACKFILL_DAYS_DAILY, BACKFILL_DAYS_INTRADAY, TIMEFRAMES

log = logging.getLogger(__name__)

_INTRADAY_TFS = {"M1", "M5", "M15"}


class CandlePoller:
    def __init__(self, client: OandaClient) -> None:
        self._client = client

    def backfill(self, db_path=_db.DB_PATH) -> None:
        """On first run fill history; on reconnect fill any gap."""
        now = datetime.now(tz=timezone.utc)
        for symbol in [PRIMARY, SMT_PAIR]:
            for tf in TIMEFRAMES:
                max_days = BACKFILL_DAYS_INTRADAY if tf in _INTRADAY_TFS else BACKFILL_DAYS_DAILY
                default_since = now - timedelta(days=max_days)
                with _db.get_connection(db_path) as conn:
                    last = get_latest_candle_time(conn, symbol, tf)
                since = last if last else default_since
                if since >= now - timedelta(minutes=1):
                    continue  # already up to date
                log.info(
                    "backfilling candles",
                    extra={"symbol": symbol, "tf": tf, "since": since.isoformat()},
                )
                self._fetch_and_store(symbol, tf, since, now, db_path)

    def poll_latest(self, db_path=_db.DB_PATH) -> None:
        """Fetch the most recent closed candle for all TFs and persist."""
        now = datetime.now(tz=timezone.utc)
        for symbol in [PRIMARY, SMT_PAIR]:
            for tf in TIMEFRAMES:
                try:
                    candles = self._client.fetch_candles(symbol, tf, count=2)
                    with _db.get_connection(db_path) as conn:
                        for c in candles:
                            upsert_candle(conn, c["instrument"], c["timeframe"], c["t"], c["o"], c["h"], c["l"], c["c"], c["v"])
                        conn.commit()
                except Exception as exc:
                    log.error(
                        "poll_latest error",
                        extra={"symbol": symbol, "tf": tf, "error": str(exc)},
                    )

    def _fetch_and_store(
        self,
        symbol: str,
        tf: str,
        since: datetime,
        until: datetime,
        db_path=_db.DB_PATH,
    ) -> int:
        try:
            candles = self._client.fetch_candles_range(symbol, tf, since, until)
        except Exception as exc:
            log.error("backfill fetch error", extra={"symbol": symbol, "tf": tf, "error": str(exc)})
            return 0
        stored = 0
        with _db.get_connection(db_path) as conn:
            for c in candles:
                upsert_candle(conn, c["instrument"], c["timeframe"], c["t"], c["o"], c["h"], c["l"], c["c"], c["v"])
                stored += 1
            conn.commit()
        log.info("backfill complete", extra={"symbol": symbol, "tf": tf, "candles": stored})
        return stored
