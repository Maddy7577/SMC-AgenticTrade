"""OANDA v20 REST + streaming client.

REST: closed-candle polling for M1/M5/M15/H1/H4/D × EUR_USD+GBP_USD.
Stream: live M1 pricing (bid/ask) used for spread gate and real-time tick.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import oandapyV20
import oandapyV20.endpoints.instruments as v20instruments
import oandapyV20.endpoints.pricing as v20pricing

from config.settings import (
    OANDA_ACCOUNT_ID,
    OANDA_API_TOKEN,
    OANDA_ENVIRONMENT,
    RECONNECT_BACKOFF_SEQUENCE,
    TIMEFRAMES,
)

log = logging.getLogger(__name__)


def _parse_oanda_time(t: str) -> datetime:
    """Parse OANDA timestamp, truncating nanoseconds to microseconds."""
    t = re.sub(r'(\.\d{6})\d+', r'\1', t.replace("Z", "+00:00"))
    return datetime.fromisoformat(t)

# Map our internal timeframe codes to OANDA granularity labels
_TF_MAP: dict[str, str] = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "H1": "H1",
    "H4": "H4",
    "D": "D",
}

_CANDLES_PER_REQUEST = 500  # OANDA max per request


class OandaClient:
    def __init__(self) -> None:
        # oandapyV20 expects "practice" (not "demo") for demo accounts
        env = "practice" if OANDA_ENVIRONMENT in ("demo", "practice") else "live"
        self._api = oandapyV20.API(
            access_token=OANDA_API_TOKEN,
            environment=env,
        )
        self._account_id = OANDA_ACCOUNT_ID

    # ------------------------------------------------------------------
    # Candle polling (REST)
    # ------------------------------------------------------------------

    def fetch_candles(
        self,
        instrument: str,
        timeframe: str,
        since: datetime | None = None,
        count: int = _CANDLES_PER_REQUEST,
    ) -> list[dict]:
        """Return a list of closed candle dicts from OANDA REST."""
        params: dict = {
            "granularity": _TF_MAP[timeframe],
            "price": "M",  # midpoint
            "count": min(count, _CANDLES_PER_REQUEST),
        }
        if since:
            params["from"] = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            del params["count"]

        endpoint = v20instruments.InstrumentsCandles(instrument, params=params)
        try:
            self._api.request(endpoint)
        except Exception as exc:
            log.error("oanda candle fetch failed", extra={"instrument": instrument, "tf": timeframe, "error": str(exc)})
            raise

        candles = []
        for raw in endpoint.response.get("candles", []):
            if not raw.get("complete", False):
                continue  # skip the open (in-progress) candle
            mid = raw["mid"]
            candles.append(
                {
                    "instrument": instrument,
                    "timeframe": timeframe,
                    "t": _parse_oanda_time(raw["time"]),
                    "o": float(mid["o"]),
                    "h": float(mid["h"]),
                    "l": float(mid["l"]),
                    "c": float(mid["c"]),
                    "v": int(raw.get("volume", 0)),
                }
            )
        return candles

    def fetch_candles_range(
        self,
        instrument: str,
        timeframe: str,
        since: datetime,
        until: datetime,
    ) -> list[dict]:
        """Paginate OANDA to fetch all closed candles in [since, until)."""
        all_candles: list[dict] = []
        cursor = since
        while cursor < until:
            batch = self.fetch_candles(instrument, timeframe, since=cursor)
            if not batch:
                break
            all_candles.extend(batch)
            last_t: datetime = batch[-1]["t"]
            if last_t <= cursor:
                break
            cursor = last_t + timedelta(seconds=1)
        return [c for c in all_candles if c["t"] < until]

    # ------------------------------------------------------------------
    # Live pricing stream
    # ------------------------------------------------------------------

    async def stream_prices(
        self,
        instruments: list[str],
    ) -> AsyncIterator[dict]:
        """Yield live price ticks. Reconnects on error with exponential backoff."""
        backoff_seq = list(RECONNECT_BACKOFF_SEQUENCE)
        attempt = 0
        while True:
            try:
                log.info("oanda stream connecting", extra={"instruments": ",".join(instruments)})
                params = {"instruments": ",".join(instruments)}
                endpoint = v20pricing.PricingStream(self._account_id, params=params)
                for msg in self._api.request(endpoint):
                    attempt = 0  # reset on first successful message
                    if msg.get("type") == "PRICE":
                        yield self._parse_price(msg)
                    elif msg.get("type") == "HEARTBEAT":
                        log.debug("oanda heartbeat")
            except Exception as exc:
                delay = backoff_seq[min(attempt, len(backoff_seq) - 1)]
                log.warning(
                    "oanda stream error, reconnecting",
                    extra={"error": str(exc), "delay_s": delay, "attempt": attempt + 1},
                )
                attempt += 1
                await asyncio.sleep(delay)

    @staticmethod
    def _parse_price(msg: dict) -> dict:
        bids = msg.get("bids", [{}])
        asks = msg.get("asks", [{}])
        bid = float(bids[0].get("price", 0)) if bids else 0.0
        ask = float(asks[0].get("price", 0)) if asks else 0.0
        spread = round((ask - bid) * 10_000, 2)  # pips (5-digit pair)
        return {
            "instrument": msg.get("instrument", ""),
            "t": _parse_oanda_time(msg["time"]),
            "bid": bid,
            "ask": ask,
            "mid": round((bid + ask) / 2, 5),
            "spread_pips": spread,
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        try:
            ep = v20instruments.InstrumentsCandles("EUR_USD", params={"granularity": "M1", "count": 1})
            self._api.request(ep)
            return True
        except Exception:
            return False
