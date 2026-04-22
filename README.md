# SMC-TradeAgents

A real-time trade intelligence engine for EURUSD built on Smart Money Concepts (SMC). It watches price action continuously, runs 15 independent strategies through a structured 4-agent debate, filters every candidate through a 9-rule discipline gate, and presents VALID / WAIT / NO_TRADE verdicts with full reasoning — all without executing a single trade automatically.

**The trader (Maddy, IST timezone) makes every final decision.**

---

## Why I Built This

Discretionary SMC trading is conceptually rigorous but mentally exhausting in real time. Marking up confluences across six timeframes, checking session windows, tracking daily loss limits, remembering whether an FVG has been reclaimed — all of it compounds under live-market pressure and leads to skipped setups or impulsive entries.

This engine removes the mechanical checklist burden. It monitors everything simultaneously, enforces rules without emotion, and surfaces only setups that pass every condition. The trader's job becomes purely: *does this setup make sense right now given what I see on the chart?*

No auto-execution. No black box. Every verdict comes with the full chain of reasoning.

---

## Core Design Principles

- **Deterministic Python throughout the decision loop.** No LLMs, no ML models, no probabilistic shortcuts. Every rule maps directly to a named SMC concept with a specific price-based condition.
- **4-agent debate per strategy.** Two agents argue *for* the trade (strict rules, quality), two argue *against* (technical risk, contextual risk). A weighted consensus produces the confidence score. A single hard veto from either risk agent kills the signal regardless of confidence.
- **Gate before publish.** Even a high-confidence VALID signal is suppressed if it's Monday, near a news event, after two losses today, over 15 trades this month, or during a post-SL cooldown window.
- **Clustering over duplication.** When multiple strategies fire on the same price level within five minutes, they merge into a cluster with a representative signal and a confidence boost rather than flooding the dashboard with duplicates.
- **Everything persists across restarts.** Daily/monthly counters, active FVG states, signal history — all live in SQLite. Restarting the engine doesn't reset risk tracking.

---

## Architecture

```
OANDA REST (1-min poll) ──► CandlePoller ──► SQLite candles table
                                                      │
                                             CEDPipeline (pipeline.py)
                                          Runs all detectors, builds context
                                                      │
                                           CanonicalContext (context.py)
                                    Single snapshot object passed downstream
                                                      │
                                    StrategyOrchestrator (orchestrator.py)
                                     15 strategies × 4 agents, sequential
                                                      │
                                         signals + agent_scores tables
                                                      │
                                      gate_loop  (app/main.py)
                                    ├── evaluate_signal (decision_gate.py)
                                    ├── process_new_signal (cluster_engine.py)
                                    └── publish_signal (publisher.py)
                                                      │
                              ┌───────────────────────┴───────────────────────┐
                    Flask SSE dashboard                            Gemini narrative
                  http://127.0.0.1:8010                     (async, non-blocking)
```

Three asyncio tasks run concurrently in `app/main.py`: `ced.run()`, `orchestrator.run()`, `gate_loop()`. OANDA stream and Flask run in separate daemon threads.

---

## The 15 Strategies

Each strategy implements exactly four inner agent classes (`opp1`, `opp2`, `risk1`, `risk2`) and a top-level `evaluate(ctx)` method returning a `StrategyResult`. Agent weights: opp1=1.5 (strict rules), opp2=1.0, risk1=1.2, risk2=0.8.

### Phase 1 Strategies (Core SMC Setups)

#### 01 — Unicorn Model
**Concept:** FVG that physically overlaps a Breaker Block, creating a high-conviction confluence zone.

The overlap must be ≥10% of the FVG's range. Entry is at the Confluence Equilibrium (CE midpoint of the overlap zone). Requires a confirmed MSS, a prior sweep, and a non-neutral HTF bias. SL is placed beyond the Breaker Block extreme plus `max(10 pips, 0.5×ATR)`. Target RR ≥3.

Best during the NY AM Silver Bullet window (IST 20:30–21:30).

#### 02 — Judas Swing
**Concept:** Asian range false breakout engineered to hunt retail stops before the real move.

The Asian high/low is marked between IST 05:30–12:30. During London (IST 12:30–15:30), price sweeps one side of the range against the daily bias (a bearish day's high gets swept, not the low). MSS confirms the reversal; an FVG in the displacement leg provides entry. SL goes beyond the sweep wick plus 15 pips. TP1 = opposite Asian range boundary; TP2 = prior day high/low.

The London kill zone window is a hard requirement.

#### 03 — Confirmation Model
**Concept:** Full five-condition confluence — all five must be met simultaneously.

1. Liquidity sweep present
2. MSS confirmed after the sweep
3. FVG visible in the displacement move
4. HTF bias non-neutral
5. Price inside the aligned Premium or Discount zone

All five = 90% base confidence. Each missing condition degrades the score proportionally. SL = sweep wick extreme ± 0.75×ATR. TP1 = 2×risk; TP2 = opposing H4 liquidity pool.

#### 04 — Silver Bullet
**Concept:** ICT Silver Bullet — time-window-constrained, high-precision confluence setup.

The window constraint is a hard gate: both the setup formation AND the entry tick must occur inside one of three one-hour windows (IST 13:30–14:30, 20:30–21:30, 00:30–01:30). If price is not within the entry zone when the window opens, the signal is discarded. Requires MSS + FVG. Entry target must be ≥15 pips from the nearest opposing level.

Outside the window = hard NO_TRADE regardless of confluence quality.

### Phase 2 Strategies (Advanced SMC Concepts)

#### 05 — Nested FVG Stack
**Concept:** Three or more FVGs formed inside a single displacement leg (consolidation-breakout structure).

Requires ≥5 consecutive same-direction M15 candles forming the displacement. The first FVG is the breakaway gap; subsequent gaps are measuring/runaway gaps. The breakaway gap must remain unfilled — if price closes back through it, the thesis is invalidated immediately. Entry at the CE of the last FVG in the stack. SL trails dynamically beyond the entry FVG extreme ± 5 pips.

#### 06 — Inverse FVG (iFVG)
**Concept:** An original FVG where price has since closed a full candle *body* completely through the gap, flipping its polarity.

The inversion requires body closure (not just a wick) through the entire gap range. This transforms the FVG from support/resistance to the opposite role. Prior liquidity sweep required. SMT divergence is strongly weighted (not a hard requirement). Entry at the iFVG midpoint. SL = wider of (iFVG zone ± 10 pips) or (beyond the sweep wick).

Best in the NY session onward (IST 17:30+).

#### 07 — OTE + FVG Confluence
**Concept:** M15 FVG sitting inside the Optimal Trade Entry zone of a higher-timeframe impulse.

The OTE band spans the 0.618–0.786 Fibonacci retracement of a qualifying H4 impulse (minimum 3×ATR). The M15 FVG must physically overlap this band. Entry = 0.705 fib level. SL = 100% retracement ± 15 pips. Targets: TP1 = 0.0 (swing origin), TP2 = −0.27 extension, TP3 = −0.62 extension. An order block inside the OTE band adds confluence.

#### 08 — Rejection Block at Key Levels
**Concept:** Long-wick rejection candle at a higher-timeframe structural level.

Wick must be ≥2× the candle body. Fib retracement 80–90% of the prior swing. Within 10 pips of a meaningful HTF level (PDH/PDL, swing extreme, OB boundary). MSS/CHoCH confirmation required. Hard veto: if the candle body subsequently penetrates >50% of the wick, `strict_rules_met` is set False permanently and the signal becomes NO_TRADE.

#### 09 — Market Maker Model (MMM)
**Concept:** Entering only in Phase 3 (Distribution) of the Market Maker four-phase cycle.

The MMM cycle (detected from H4+D price structure) has four phases: Accumulation, Manipulation, Distribution, Re-Accumulation. This strategy only fires in Phase 3. Phases 1, 2, and 4 produce automatic zero scores from the opposition agents, ensuring NO_TRADE. Entry requires MSS at an HTF PD array and a subsequent FVG.

#### 10 — Power of 3 / AMD Intraday
**Concept:** Intraday AMD (Accumulation-Manipulation-Distribution) with manipulation event detection.

Maps the daily session phases to the AMD framework. The Accumulation phase (IST 05:30–12:30) produces NO_TRADE. A manipulation event is detected when price breaks the Asian range against the HTF daily bias (a false breakout engineered by smart money). Entry requires MSS after the manipulation event. Distribution phase = VALID candidate; Manipulation phase = capped at WAIT.

Ancestry: shares the Judas family. When both Judas Swing and Power of 3 fire in the same cluster, Judas is always the representative.

#### 11 — Propulsion Block
**Concept:** Order block with a propulsion candle inside it, followed by an FVG, showing institutional acceleration.

Requires a valid (untouched since formation) OB. A propulsion candle inside the OB zone must have a body/range ratio ≥0.6 (strong, full candles — not indecision). An FVG must form in the three candles immediately after the propulsion candle. The OB must not be retouched after the propulsion. H1 accumulated liquidity (swing level touched ≥2 times in 50 candles) adds context. Entry at OB midpoint, SL beyond OB extreme ± 10 pips.

#### 12 — Vacuum Block
**Concept:** Unfilled price gap (weekend, news, or session) acting as a magnet.

An open gap exists when `curr.low > prev.high` (bullish) or `curr.high < prev.low` (bearish) on H1 candles. Gap fill is defined strictly: a candle *body* closing inside the gap = fully filled. A wick touch alone doesn't count. Hard veto: if the gap is fully filled, `strict_rules_met` = False. Requires an LTF MSS within 10 pips of the gap CE. Entry = gap CE. SL = 5 pips beyond the gap boundary.

#### 13 — Reclaimed FVG
**Concept:** FVG that has been tested multiple times with price respecting the CE on each test.

Requires ≥2 respected CE tests: price enters the FVG zone, and the candle closes back above/below the midpoint (CE) rather than escaping through it. Any failed test — where price closes beyond the CE — invalidates the thesis permanently. Three or more respected tests earns a +10 bonus. An FVG with a gap of ≤1 pip is flagged as a "perfect FVG" for additional confluence. Entry at the CE, SL at the FVG extreme ± 5 pips.

#### 14 — CISD (Change in State of Delivery)
**Concept:** Sequence reversal candle pattern near HTF structure.

Requires ≥3 consecutive bearish M5 candles. The CISD trigger candle closes *above* the open of the first candle in the sequence — breaking the delivery state. Entry at a subsequent FVG or OB retest. Must be within 15 pips of an HTF key level. Prior sweep required.

By design, `opp1` is capped at a maximum score of 65, which prevents a standalone CISD signal from reaching VALID. It is designed to cluster with a Confirmation family signal and reach VALID through the confluence boost.

#### 15 — BPR in Order Block
**Concept:** Balanced Price Range (overlapping bullish and bearish FVGs) inside an HTF order block.

The BPR forms when a bullish FVG and a bearish FVG on M15 overlap by ≥3 pips inside an H4+ OB. This creates a zone where both buy-side and sell-side imbalances exist — a high-probability reversion point. Entry at the BPR midpoint (CE of overlap). SL beyond the full OB extreme ± 10 pips. HTF bias must align with OB direction. LTF MSS required.

BPR is an independent ancestry root and **never clusters** with any other strategy.

---

## Verdict Logic

**VALID** — all of the following must be true:
- Confidence ≥ 75
- `strict_rules_met` = True (strategy-specific hard conditions passed)
- RR ≥ 2.0
- Price is currently at the entry level
- No hard veto from any risk agent

**WAIT** — setup is confirmed but entry hasn't been reached:
- Confidence ≥ 65
- `strict_rules_met` = True
- No hard veto
- Price not yet at entry

**NO_TRADE** — everything else, including any hard veto.

---

## Detectors

All detectors are pure functions over candle lists — no database access, no side effects. The pipeline calls them and persists results.

| Detector | What it Detects | Key Rule |
|---|---|---|
| `fvg.py` | Fair Value Gaps (bullish/bearish) | C1 wick doesn't overlap C3 wick; gap ≥ 5 pips |
| `sweep.py` | Liquidity sweeps | Wick hunts level (±5 pip tolerance), close reverses |
| `mss.py` | Market Structure Shift / CHoCH | Candle *body* closes beyond most recent swing |
| `order_block.py` | Order Blocks + Breaker Blocks | Last candle before displacement; range ≥ 2×ATR |
| `swings.py` | Swing highs and lows | 10-bar lookback each side |
| `atr.py` | Average True Range | Wilder smoothing (SMA seed → EMA), 14-period |
| `fibonacci.py` | Fib retracement / extension levels | 0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0, −0.27, −0.62 |
| `gap_detector.py` | Unfilled price gaps on H1 | Weekend / news / session gap types; body fill rule |
| `htf_bias.py` | D1/H4 trend bias | HH+HL = bullish; LH+LL = bearish; D1 breaks H4 ties |
| `kill_zone.py` | Session window (IST) | Asian, London, NY, Silver Bullet windows |
| `pd_zone.py` | Premium / Discount zone | Recent H4/D swing range; CE = 50% midpoint |
| `smt_divergence.py` | EURUSD vs GBPUSD divergence | One pair makes LL, other makes HL = bullish div |
| `amd_phase.py` | Intraday AMD phase | IST time-based: 05:30–12:30 Accum, 12:30–15:30 Manip, 15:30–21:30 Dist |
| `mmm_phase.py` | Market Maker 4-phase cycle | Detected from H4+D consolidation structure |
| `long_wick_classifier.py` | Rejection wick candles | Wick ≥ 2× body; bullish = lower wick; bearish = upper wick |

The `pipeline.py` orchestrates all of these every M1 close (budget < 500 ms), carries FVG and gap state machines across ticks, deduplicates events so the same sweep/MSS/fibonacci level isn't re-inserted on every tick, and emits a `CanonicalContext` to the strategy queue.

---

## Decision Gate

Nine veto rules run in order before any signal is published. They're checked fastest-to-reject first.

| Rule | Condition |
|---|---|
| Strategy disabled | Strategy is toggled off in settings |
| Monday | No trading on Mondays (gap risk) |
| News blackout | ±30 minutes around any high-impact event (Finnhub calendar) |
| Daily loss limit | 2 stop-losses hit today |
| Monthly trade cap | 15 trades completed this month |
| Post-SL cooling | Within 20 minutes of a stop-loss hit |
| High spread | Live spread > 1.5 pips |
| Confidence floor | Below WAIT threshold |
| Hard veto | Any risk agent returned a hard "oppose" |

Counter state (daily losses, monthly count) persists in the `settings` KV table so engine restarts don't reset the risk tracking.

---

## Clustering

When multiple strategies detect a setup at the same price level simultaneously, it's more signal than noise. The clustering system merges them rather than duplicating the alert.

**How it works:**
- Signals sharing the same `direction + entry_midpoint (rounded to 5-pip buckets)` within a 5-minute window share a cluster
- Ancestry rules determine which strategies can merge (Confirmation family: Confirmation/Silver Bullet/CISD; Judas family: Judas/Power of 3; all others are independent roots and never cluster)
- The representative signal gets a confidence boost: +10 for 2 members, +15 for 3 or more (capped at +20 total)
- BPR (Strategy 15) is always an independent root — never clusters with anything

**Signal signature format:** `strategy_id:direction:sweep_level:mss_level:entry_midpoint` — all prices rounded to 5-pip buckets.

---

## Configuration

All tunables live in `config/settings.py` and load from `.env` at import time.

| Setting | Default | Meaning |
|---|---|---|
| `CONFIDENCE_VALID_THRESHOLD` | 75.0 | Minimum confidence for VALID |
| `CONFIDENCE_WAIT_THRESHOLD` | 65.0 | Minimum confidence for WAIT |
| `RR_FLOOR` | 2.0 | Minimum risk-to-reward |
| `FVG_MIN_PIPS` | 5.0 | FVGs smaller than this are ignored |
| `OB_DISPLACEMENT_ATR_MULTIPLIER` | 2.0 | OB candle must be ≥ 2× ATR |
| `MAX_DAILY_LOSSES` | 2 | Stop trading after 2 SL hits today |
| `MAX_MONTHLY_TRADES` | 15 | Monthly trade cap |
| `POST_STOPLOSS_COOLING_MINUTES` | 20 | Cooldown after a stop-loss |
| `MAX_SPREAD_PIPS` | 1.5 | Reject if spread exceeds this |
| `NEWS_BLACKOUT_MINUTES` | 30 | Window around high-impact events |

**Kill zone windows (IST):**

| Session | Window |
|---|---|
| Asian Session | 05:30 – 12:30 |
| London Kill Zone | 12:30 – 15:30 |
| Silver Bullet (London) | 13:30 – 14:30 |
| NY Kill Zone | 17:30 – 20:30 |
| Silver Bullet (NY AM) | 20:30 – 21:30 |
| Silver Bullet (NY PM) | 00:30 – 01:30 |

---

## Storage

SQLite at `data/smc.db` in WAL mode (concurrent reads + writes).

| Table | Contents |
|---|---|
| `candles` | OHLCV per instrument per timeframe |
| `events` | Raw detector outputs (FVGs, sweeps, MSS, gaps, phases) |
| `signals` | Strategy verdicts with confidence, trade parameters, gate result |
| `agent_scores` | Individual scores from all four agents per signal |
| `clusters` | Merged signal groups with representative and member IDs |
| `trades` | Recorded outcomes (TP/SL hit, realized R) |
| `calendar` | Economic events from Finnhub |
| `settings` | KV store: daily loss counter, monthly count, MMM phase, etc. |

`repositories.py` owns all typed read/write helpers. No raw SQL is written anywhere above the storage layer. All timestamps are UTC ISO-8601 strings.

---

## Dashboard

Flask app at `http://127.0.0.1:8010`, started automatically with the engine.

**Segment 1 — Performance:**
- Strategy leaderboard: 30-day stats, win rate, expectancy per strategy
- Full trade history table with realized R per trade

**Segment 2 — Live Strategies:**
- 15 strategy cards updating via Server-Sent Events
- Each card shows: last verdict badge (VALID/WAIT/NO_TRADE), confidence score, entry/SL/TP levels, signal history dots (last 10)
- Click any signal to see the full 4-agent breakdown

**Segment 3 — Signal Detail:**
- Full agent opinions (score + reasoning for each of the four agents)
- Gate result with which rule fired (if rejected)
- Evidence list: what conditions were met or missed
- Cluster membership if applicable

**Recording outcomes:** A button on each published signal lets you mark it as TP1/TP2 hit or SL hit. The system computes realized R and feeds the performance stats.

---

## Notifications

Telegram alerts are sent for every VALID signal, including the strategy name, direction, entry/SL/TP, confidence score, and the gate passage summary. Configuration in `.env`.

---

## Running the Engine

```bash
# First time: copy and fill in your API keys
cp .env.example .env

# Seed the database with historical candles
python3 scripts/backfill_history.py

# Start the full engine (CED + strategies + gate + dashboard)
python3 -m app.main

# Dashboard opens at http://127.0.0.1:8010
```

**Replay a past day for debugging:**
```bash
python3 scripts/replay_day.py 2026-01-06
```

**Run tests:**
```bash
python3 -m pytest tests/                    # all tests
python3 -m pytest tests/ --cov=app/detector --cov=app/strategies --cov=app/clustering --cov=app/gate  # with coverage
```

**Lint:**
```bash
python3 -m ruff check .       # check
python3 -m ruff check . --fix # auto-fix
```

Dependencies run on system Python 3.10. The `venv/` has a subset only.

---

## Required API Keys

| Key | Purpose |
|---|---|
| `OANDA_API_TOKEN` | Live/practice EURUSD candles and streaming prices |
| `FINNHUB_API_KEY` | Economic calendar (news blackout enforcement) |
| `GEMINI_API_KEY` | Post-gate narrative generation (non-blocking, optional) |

---

## Project Structure

```
app/
├── main.py                    # Engine entrypoint, asyncio task wiring
├── detector/
│   ├── pipeline.py            # CED orchestrator (calls all detectors per tick)
│   ├── context.py             # CanonicalContext dataclass
│   ├── fvg.py                 # FVG detector + state machine
│   ├── sweep.py               # Liquidity sweep detector
│   ├── mss.py                 # Market structure shift
│   ├── order_block.py         # OB + Breaker Block
│   ├── swings.py              # Swing high/low
│   ├── atr.py                 # ATR (Wilder)
│   ├── fibonacci.py           # Fib levels
│   ├── gap_detector.py        # Price gap detector
│   ├── htf_bias.py            # D1/H4 trend bias
│   ├── kill_zone.py           # Session window classifier
│   ├── pd_zone.py             # Premium/Discount zone
│   ├── smt_divergence.py      # SMT divergence (EUR vs GBP)
│   ├── amd_phase.py           # AMD intraday phase
│   ├── mmm_phase.py           # Market Maker 4-phase
│   └── long_wick_classifier.py
├── strategies/
│   ├── base.py                # BaseStrategy, BaseAgent, StrategyResult
│   ├── debate.py              # compute_verdict (weighted 4-agent)
│   ├── orchestrator.py        # Runs all 15 strategies per context
│   ├── strategy_01_unicorn.py
│   ├── strategy_02_judas.py
│   ├── strategy_03_confirmation.py
│   ├── strategy_04_silver_bullet.py
│   ├── strategy_05_nested_fvg.py
│   ├── strategy_06_ifvg.py
│   ├── strategy_07_ote_fvg.py
│   ├── strategy_08_rejection_block.py
│   ├── strategy_09_mmm.py
│   ├── strategy_10_po3.py
│   ├── strategy_11_propulsion.py
│   ├── strategy_12_vacuum.py
│   ├── strategy_13_reclaimed_fvg.py
│   ├── strategy_14_cisd.py
│   └── strategy_15_bpr_ob.py
├── gate/
│   ├── decision_gate.py       # 9-rule veto gate
│   └── publisher.py           # Publishes passing signals
├── clustering/
│   ├── cluster_engine.py      # 5-min bucket clustering
│   └── ancestry.py            # Strategy family rules
├── storage/
│   ├── db.py                  # Schema bootstrap, connection factory
│   └── repositories.py        # All typed DB helpers
├── ingestion/
│   ├── oanda_client.py        # OANDA REST + stream
│   ├── stream_consumer.py     # Live tick consumer
│   ├── poller.py              # Minute-candle polling
│   └── finnhub_client.py      # Economic calendar
├── dashboard/
│   ├── flask_app.py           # Flask + SSE
│   ├── routes/                # Segment endpoints
│   ├── templates/             # Jinja2 HTML
│   └── static/                # CSS, JS
├── notifications/
│   └── telegram.py            # VALID signal alerts
└── performance/
    └── tracker.py             # Trade outcome tracking
config/
├── settings.py                # All tunables (loaded from .env)
└── instruments.py             # Instrument specs, pip helpers
scripts/
├── backfill_history.py        # Seed historical candles
└── replay_day.py              # Replay a past day through full pipeline
tests/
├── detector/                  # Unit tests for all detectors
├── strategies/                # Strategy verdict + gate + clustering tests
└── fixtures/                  # Curated EURUSD candle scenarios
```

---

## What This Is Not

- Not an auto-trader. No orders are placed, ever.
- Not an indicator overlay on TradingView. The engine runs locally and watches independently.
- Not an AI signal service. All logic is deterministic Python rules — the confidence score is a weighted average of explicit conditions, not a neural network output.

The Gemini integration generates a plain-English summary of *why* a signal was produced (e.g., "Bullish FVG formed at 1.08420 overlapping breaker block after Asian sweep. MSS confirmed at 1.08380. NY Silver Bullet window active.") — but it receives the already-computed verdict and evidence, it doesn't produce the verdict.
