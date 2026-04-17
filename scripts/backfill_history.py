#!/usr/bin/env python3
"""Seed the database with historical OANDA candles.

Usage:
    python scripts/backfill_history.py

Respects BACKFILL_DAYS_INTRADAY (30d for M1/M5/M15) and
BACKFILL_DAYS_DAILY (365d for H1/H4/D) from config/settings.py.
Safe to re-run — upserts are idempotent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.oanda_client import OandaClient
from app.ingestion.poller import CandlePoller
from app.logging_config import setup_logging
from app.storage.db import bootstrap

setup_logging()
bootstrap()

client = OandaClient()
poller = CandlePoller(client)

print("Starting historical backfill — this may take a few minutes...")
poller.backfill()
print("Backfill complete.")
