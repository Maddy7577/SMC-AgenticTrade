"""Health snapshot aggregator — feeds the /health endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.storage import db as _db
from app.storage.repositories import get_latest_candle_time
from config.instruments import PRIMARY, SMT_PAIR
from config.settings import TIMEFRAMES

if TYPE_CHECKING:
    from app.ingestion.finnhub_client import FinnhubClient
    from app.ingestion.stream_consumer import StreamConsumer


def build_health_snapshot(
    stream: "StreamConsumer",
    finnhub: "FinnhubClient",
    db_path=_db.DB_PATH,
) -> dict:
    now = datetime.now(tz=timezone.utc)

    # Last candle time per instrument × timeframe
    last_candles: dict[str, dict[str, str | None]] = {}
    with _db.get_connection(db_path) as conn:
        for symbol in [PRIMARY, SMT_PAIR]:
            last_candles[symbol] = {}
            for tf in TIMEFRAMES:
                t = get_latest_candle_time(conn, symbol, tf)
                last_candles[symbol][tf] = t.isoformat() if t else None

    return {
        "ok": True,
        "timestamp": now.isoformat(),
        "oanda_stream": {
            "connected": stream.is_connected,
            "last_tick": stream.last_tick_t.isoformat() if stream.last_tick_t else None,
            "spread_pips": stream.spread_pips,
        },
        "finnhub": {
            "last_sync": finnhub.last_sync.isoformat() if finnhub.last_sync else None,
        },
        "last_candles": last_candles,
    }
