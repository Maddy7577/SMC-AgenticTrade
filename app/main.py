"""SMC-TradeAgents main entrypoint (I1).

Wires together:
  OANDA stream → CED pipeline → Strategy orchestrator → Clustering → Gate → Publisher
  + APScheduler for Finnhub polling and M1 candle polling
  + Flask dashboard in a separate thread
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.clustering.cluster_engine import process_new_signal
from app.dashboard.flask_app import create_app
from app.dashboard.routes.health import init_health
from app.detector.pipeline import CEDPipeline
from app.gate.decision_gate import evaluate_signal
from app.gate.publisher import publish_signal
from app.ingestion.finnhub_client import FinnhubClient
from app.ingestion.oanda_client import OandaClient
from app.ingestion.poller import CandlePoller
from app.ingestion.stream_consumer import StreamConsumer
from app.logging_config import setup_logging
from app.performance.tracker import check_open_trades
from app.storage.db import bootstrap
from app.strategies.orchestrator import StrategyOrchestrator
from config.settings import FLASK_HOST, FLASK_PORT

setup_logging()
log = logging.getLogger(__name__)


def run_flask(stream: StreamConsumer, finnhub: FinnhubClient) -> None:
    app = create_app()
    init_health(stream, finnhub)
    log.info("dashboard starting", extra={"host": FLASK_HOST, "port": FLASK_PORT})
    app.run(host=FLASK_HOST, port=FLASK_PORT, use_reloader=False, threaded=True)


async def main() -> None:
    log.info("SMC-TradeAgents starting")
    bootstrap()

    oanda = OandaClient()
    poller = CandlePoller(oanda)
    finnhub = FinnhubClient()

    # Backfill history on startup
    log.info("running backfill")
    await asyncio.get_event_loop().run_in_executor(None, poller.backfill)
    log.info("backfill complete")

    # Finnhub initial load
    await asyncio.get_event_loop().run_in_executor(None, finnhub.refresh)

    # Queues
    stream_candle_q: asyncio.Queue = asyncio.Queue(maxsize=500)
    context_q: asyncio.Queue = asyncio.Queue(maxsize=100)
    signal_q: asyncio.Queue = asyncio.Queue(maxsize=500)

    stream = StreamConsumer(oanda, poller, stream_candle_q)

    # Flask in a daemon thread
    flask_thread = threading.Thread(
        target=run_flask,
        args=(stream, finnhub),
        daemon=True,
    )
    flask_thread.start()

    # OANDA stream runs in a daemon thread (uses synchronous requests — must not block asyncio loop)
    def run_stream_sync():
        import asyncio as _asyncio
        _asyncio.run(stream.run())

    stream_thread = threading.Thread(target=run_stream_sync, daemon=True)
    stream_thread.start()

    # APScheduler: poll candles every minute, Finnhub every 15 min, check open trades every minute
    loop = asyncio.get_event_loop()

    def poll_and_trigger():
        poller.poll_latest()
        # Push a trigger candle to the CED queue so the pipeline evaluates
        from datetime import datetime, timezone
        trigger = {"instrument": "EUR_USD", "t": datetime.now(tz=timezone.utc)}
        asyncio.run_coroutine_threadsafe(stream_candle_q.put(trigger), loop)

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(poll_and_trigger, "interval", seconds=60, id="candle_poll")
    scheduler.add_job(finnhub.refresh, "interval", seconds=900, id="finnhub_poll")
    scheduler.add_job(
        lambda: check_open_trades({"EUR_USD": stream._latest_bid.get("EUR_USD", 0.0)}),
        "interval",
        seconds=60,
        id="outcome_check",
    )
    scheduler.start()

    # CED pipeline
    ced = CEDPipeline(stream_candle_q, context_q)

    # Strategy orchestrator
    orchestrator = StrategyOrchestrator(context_q, signal_q)

    # Gate + publisher loop
    async def gate_loop() -> None:
        pending_window: list[dict] = []  # signals for clustering
        while True:
            signal_id, result = await signal_q.get()
            try:
                decision = evaluate_signal(signal_id, stream.spread_pips)
                if decision.published:
                    # Cluster check
                    with __import__("app.storage.db", fromlist=["get_connection"]).get_connection() as conn:
                        sig = __import__("app.storage.repositories", fromlist=["get_signal"]).get_signal(conn, signal_id)
                    cluster_result = process_new_signal(signal_id, pending_window)
                    cluster_id = cluster_result.cluster_id if cluster_result else None
                    publish_signal(signal_id, cluster_id)
                    if sig:
                        pending_window.append(sig)
                        pending_window = pending_window[-50:]  # keep last 50 for clustering
            except Exception as exc:
                log.error("gate loop error", extra={"signal_id": signal_id, "error": str(exc)})
            finally:
                signal_q.task_done()

    # Run async tasks (stream runs in its own thread above, not here)
    log.info("engine running")
    await asyncio.gather(
        ced.run(),
        orchestrator.run(),
        gate_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
