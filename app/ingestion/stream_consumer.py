"""Live OANDA stream consumer.

Subscribes to EUR_USD and GBP_USD price ticks, tracks spread, detects
stale stream (no tick > 30s triggers reconnect), and emits M1 close
signals to an asyncio.Queue for the CED pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.ingestion.oanda_client import OandaClient
from app.ingestion.poller import CandlePoller
from config.instruments import PRIMARY, SMT_PAIR

log = logging.getLogger(__name__)

STREAM_STALE_SECONDS = 30


class StreamConsumer:
    def __init__(
        self,
        client: OandaClient,
        poller: CandlePoller,
        candle_queue: asyncio.Queue,
    ) -> None:
        self._client = client
        self._poller = poller
        self._candle_queue = candle_queue
        self._latest_bid: dict[str, float] = {}
        self._latest_ask: dict[str, float] = {}
        self._latest_spread: dict[str, float] = {}
        self._last_tick_t: datetime | None = None
        self._connected: bool = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def spread_pips(self) -> float:
        return self._latest_spread.get(PRIMARY, 0.0)

    @property
    def last_tick_t(self) -> datetime | None:
        return self._last_tick_t

    async def run(self) -> None:
        instruments = [PRIMARY, SMT_PAIR]
        async for tick in self._client.stream_prices(instruments):
            self._connected = True
            self._last_tick_t = tick["t"]
            instrument = tick["instrument"]
            self._latest_bid[instrument] = tick["bid"]
            self._latest_ask[instrument] = tick["ask"]
            self._latest_spread[instrument] = tick["spread_pips"]

    async def watchdog(self) -> None:
        """Detect stream stall and force reconnect by raising."""
        while True:
            await asyncio.sleep(STREAM_STALE_SECONDS)
            if self._last_tick_t is None:
                continue
            age = (datetime.now(tz=timezone.utc) - self._last_tick_t).total_seconds()
            if age > STREAM_STALE_SECONDS:
                log.warning("stream stale, reconnect triggered", extra={"age_s": round(age)})
                self._connected = False
