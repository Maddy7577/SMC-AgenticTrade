#!/usr/bin/env python3
"""Replay a past UTC day through the full pipeline for debugging / regression testing.

Usage:
    python scripts/replay_day.py 2026-01-06

Replays all M1 candles for the given date, feeding each through the CED
and strategy orchestrator in-process. Uses a temporary in-memory queue.
Idempotent: safe to run twice (signals deduped by signature+t).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detector.pipeline import CEDPipeline
from app.gate.decision_gate import evaluate_signal
from app.gate.publisher import publish_signal
from app.logging_config import setup_logging
from app.storage.db import bootstrap, get_connection
from app.storage.repositories import get_candles
from app.strategies.orchestrator import StrategyOrchestrator
from config.instruments import PRIMARY

setup_logging()
bootstrap()


async def replay(date_str: str) -> None:
    day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    next_day = day + timedelta(days=1)

    with get_connection() as conn:
        all_m1 = get_candles(conn, PRIMARY, "M1", limit=2000)

    day_candles = [
        c for c in all_m1
        if day <= datetime.fromisoformat(str(c["t"])).replace(tzinfo=timezone.utc) < next_day
    ]

    if not day_candles:
        print(f"No M1 candles found for {date_str}. Run backfill_history.py first.")
        return

    print(f"Replaying {len(day_candles)} M1 candles for {date_str}...")

    stream_q: asyncio.Queue = asyncio.Queue()
    context_q: asyncio.Queue = asyncio.Queue()
    signal_q: asyncio.Queue = asyncio.Queue()

    ced = CEDPipeline(stream_q, context_q)
    orchestrator = StrategyOrchestrator(context_q, signal_q)

    for candle in day_candles:
        await stream_q.put(candle)

    # Process
    for _ in day_candles:
        ctx = await asyncio.wait_for(context_q.get(), timeout=5)
        await asyncio.get_event_loop().run_in_executor(None, orchestrator._evaluate_all, ctx)

    # Gate all produced signals
    total = 0
    published = 0
    while not signal_q.empty():
        signal_id, result = signal_q.get_nowait()
        total += 1
        decision = evaluate_signal(signal_id)
        if decision.published:
            publish_signal(signal_id)
            published += 1

    print(f"Replay complete: {total} signals produced, {published} published.")


if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    asyncio.run(replay(date_str))
