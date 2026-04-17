"""Finnhub economic calendar client.

Polls /calendar/economic every 15 minutes (via APScheduler in main.py) and
persists USD + EUR events to the `calendar` table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import finnhub

from app.storage import db as _db
from app.storage.repositories import upsert_calendar_event
from config.settings import FINNHUB_API_KEY

log = logging.getLogger(__name__)

_WATCHED_CURRENCIES = {"USD", "EUR"}


class FinnhubClient:
    def __init__(self) -> None:
        self._client = finnhub.Client(api_key=FINNHUB_API_KEY)
        self._last_sync: datetime | None = None

    @property
    def last_sync(self) -> datetime | None:
        return self._last_sync

    def refresh(self, db_path=_db.DB_PATH, lookahead_days: int = 7) -> int:
        """Fetch upcoming events and upsert to DB. Returns count of events stored."""
        now = datetime.now(tz=timezone.utc)
        from_dt = now - timedelta(hours=2)  # include recently started events
        to_dt = now + timedelta(days=lookahead_days)

        try:
            data = self._client.economic_calendar(
                _from=from_dt.strftime("%Y-%m-%d"),
                to=to_dt.strftime("%Y-%m-%d"),
            )
        except Exception as exc:
            log.error("finnhub calendar fetch failed", extra={"error": str(exc)})
            return 0

        events = data.get("economicCalendar", [])
        stored = 0
        with _db.get_connection(db_path) as conn:
            for ev in events:
                currency = (ev.get("country") or "").upper()
                if currency not in _WATCHED_CURRENCIES:
                    continue
                impact_raw = (ev.get("impact") or "").lower()
                # Finnhub uses 1/2/3 numeric OR low/medium/high text — normalise
                impact = _normalise_impact(impact_raw)
                try:
                    t = datetime.fromisoformat(ev["time"].replace("Z", "+00:00"))
                except (KeyError, ValueError):
                    continue
                upsert_calendar_event(
                    conn,
                    t=t,
                    currency=currency,
                    event_name=ev.get("event", "Unknown"),
                    impact=impact,
                    actual=ev.get("actual"),
                    forecast=ev.get("estimate"),
                    previous=ev.get("prev"),
                )
                stored += 1
            conn.commit()

        self._last_sync = now
        log.info("finnhub calendar refreshed", extra={"events": stored})
        return stored


def _normalise_impact(raw: str) -> str:
    mapping = {"1": "low", "2": "medium", "3": "high", "low": "low", "medium": "medium", "high": "high"}
    return mapping.get(raw, "low")
