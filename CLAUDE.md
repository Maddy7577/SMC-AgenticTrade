# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

SMC-TradeAgents is a EURUSD trade intelligence engine for a discretionary SMC (Smart Money Concepts) trader. It does **not** auto-execute trades — it produces VALID/WAIT/NO_TRADE verdicts with reasoning. The user (Maddy, IST timezone) decides whether to act. All detection and agent logic is deterministic Python — no LLM calls inside the analysis loop (Gemini is only used post-gate for narrative generation).

## Commands

```bash
# Run the full engine (OANDA stream + CED + strategies + dashboard)
python3 -m app.main

# Seed or gap-fill the database (safe to re-run, idempotent)
python3 scripts/backfill_history.py

# Replay a past UTC day through the full pipeline (dev/debug)
python3 scripts/replay_day.py

# Run all tests
python3 -m pytest tests/

# Run a single test file
python3 -m pytest tests/detector/test_fvg.py -v

# Run a single test
python3 -m pytest tests/detector/test_fvg.py::test_bullish_fvg_detected -v

# Run with coverage on the 4 critical modules (target ≥70%)
python3 -m pytest tests/ --cov=app/detector --cov=app/strategies --cov=app/clustering --cov=app/gate

# Lint
python3 -m ruff check .

# Auto-fix lint issues
python3 -m ruff check . --fix

# Dashboard (started automatically by app.main, or standalone)
# Opens at http://127.0.0.1:8010
```

Dependencies are installed in system Python 3.10 (not in the `venv/` folder — the venv only has a subset). Run `pip install -r requirements.txt` if anything is missing.

## Architecture: Signal Pipeline

Every minute the engine runs this pipeline:

```
OANDA REST poll → CandlePoller → SQLite candles table
                                        ↓
                              CEDPipeline (app/detector/pipeline.py)
                                        ↓
                              CanonicalContext (app/detector/context.py)
                                        ↓
                          StrategyOrchestrator (app/strategies/orchestrator.py)
                           [5 strategies × 4 agents each, parallel]
                                        ↓
                              signals + agent_scores tables
                                        ↓
                          gate_loop in app/main.py
                           → evaluate_signal (app/gate/decision_gate.py)
                           → process_new_signal (app/clustering/cluster_engine.py)
                           → publish_signal (app/gate/publisher.py)
                                        ↓
                          Flask SSE → dashboard (http://127.0.0.1:8010)
                          Gemini narrative (async, non-blocking)
```

Three asyncio tasks run concurrently in `app/main.py`: `ced.run()`, `orchestrator.run()`, `gate_loop()`. The OANDA stream and Flask run in separate daemon threads to avoid blocking the event loop.

## Key Design Contracts

**CanonicalContext** (`app/detector/context.py`) is the single data object passed from CED to all strategies. All detector outputs (FVGs, OBs, MSS, sweeps, swings, HTF bias, kill zone, SMT, ATR, PD zone) are fields on it. Never pass raw candle lists to strategy agents — they receive a context.

**4-agent debate per strategy**: Each strategy has exactly `opp1` (strict rules), `opp2` (quality), `risk1` (technical risk), `risk2` (contextual risk). `compute_verdict()` in `app/strategies/debate.py` aggregates them into confidence (0–100) and verdict. Weights: opp1=1.5, opp2=1.0, risk1=1.2, risk2=0.8.

**Verdict thresholds**: VALID requires confidence ≥ 75 + strict rules met + RR ≥ 2.0 + price at entry + no hard veto. WAIT requires confidence ≥ 65 + strict rules met + no hard veto. Everything else is NO_TRADE.

**Gate vetoes** run in this order (most likely to reject first): Monday → news blackout → daily losses (max 2) → monthly cap (max 15) → confidence floor → RR floor → spread (max 1.5 pips) → post-SL cooling (20 min). Counter state persists in the `settings` KV table so restarts don't reset counters.

**Clustering**: Signals in the same 5-minute time bucket with matching canonical signatures (direction + price levels rounded to 5-pip buckets) are merged. Ancestry: Unicorn > Silver Bullet > Confirmation (same family); Judas and iFVG are independent roots and never merge with the Unicorn family. The representative gets a confidence boost (10% for 2 members, 15% for 3+).

**Signal signatures** are colon-separated: `strategy_id:direction:sweep_level:mss_level:entry_midpoint`. All prices rounded to 5-pip buckets via `_rnd()`.

## Storage

SQLite at `data/smc.db` with WAL mode. All timestamps stored as UTC ISO-8601 strings. Key tables: `candles`, `events`, `signals`, `agent_scores`, `clusters`, `trades`, `calendar`, `settings` (KV). The `repositories.py` layer owns all typed read/write helpers — never write raw SQL in modules above the storage layer.

## Detectors (`app/detector/`)

All detector functions are **pure functions over candle lists** — no DB access, no side effects. The pipeline orchestrator (`pipeline.py`) calls them and persists events. This makes them straightforward to unit test with hand-crafted candles (see `tests/fixtures/scenarios.py`).

FVG state machine states: `formed → retested → partially_filled / fully_filled / inverted`. Inverted = candle body closes through the entire gap (used by iFVG strategy).

## Strategies (`app/strategies/`)

Each strategy file (`strategy_01_unicorn.py` etc.) defines 4 inner agent classes and a top-level strategy class with `evaluate(ctx) → StrategyResult`. The strategy ID string (`01_unicorn`, `02_judas`, etc.) is the join key across `signals`, `clusters`, `trades`, and `strategy_stats` tables.

Adding a new strategy: implement `BaseStrategy` + 4 `BaseAgent` subclasses, then add to `ALL_STRATEGIES` in `orchestrator.py`.

## Configuration

All tunables live in `config/settings.py` — loaded from `.env` at import time. The `.env` file is gitignored; `.env.example` shows required keys. The three required external API keys are `OANDA_API_TOKEN`, `FINNHUB_API_KEY`, and `GEMINI_API_KEY`.

Kill zone windows are defined in IST (UTC+5:30) in `KILL_ZONES_IST`. The Monday veto and all IST-boundary logic use `ZoneInfo("Asia/Kolkata")` — never pytz.

## Testing

Test fixtures in `tests/fixtures/scenarios.py` provide curated EURUSD candle sequences for each detector scenario. `tests/conftest.py` provides `candle_factory`, `eurusd_meta`, and `flat_candles_20` fixtures.

Gate tests (`tests/strategies/test_gate.py`) use a `tmp_db` pytest fixture (bootstrapped temp SQLite) to avoid touching `data/smc.db`.

The `pyproject.toml` has the pytest config (`testpaths = ["tests"]`). The `ruff.toml` at project root overrides `pyproject.toml` ruff settings — `E741` is suppressed project-wide because `l` is standard OHLC notation for the low price.
