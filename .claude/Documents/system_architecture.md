# SMC-TradeAgents — System Architecture

**Version:** 1.2 (design only, no implementation yet)
**Date:** 2026-04-18
**Status:** Architecture approved; Phase 1 complete; Phase 2 spec and plan approved
**Owner:** Maddy
**Timezone convention:** all internal timestamps stored in UTC; all user-facing displays rendered in **IST (Asia/Kolkata, UTC+5:30)**.

### Revision history
- **1.0 (2026-04-16)** — initial architecture, 7-route dashboard, Ollama narrative, Telegram alerts.
- **1.1 (2026-04-16)** — Gemini 2.0 Flash (free) replaces Ollama; Telegram deferred out of Phase 1; dashboard redesigned as 3-segment web app; IST as display timezone; Monday veto; confidence thresholds (VALID ≥ 75, WAIT ≥ 65); confluence boost accepted; Phase 1 hosting on Mac (launchd), migration path to Oracle Cloud Always Free for Phase 2+.
- **1.2 (2026-04-18)** — Phase plan restructured: Phase 2 now delivers all 10 remaining strategies (#5, #7–#15) bringing total to 15; Phase 3 becomes Oracle Cloud Always Free migration and infrastructure hardening only. Architecture diagram and §9.2 / §13 updated accordingly.

---

## 1. Executive Summary

SMC-TradeAgents is a zero-cost (except TradingView Premium, already owned) EURUSD trade intelligence engine. It continuously evaluates 15 Smart Money Concepts (SMC) strategies against live market data, subjects each strategy to a 4-agent debate (2 Opportunity + 2 Risk), de-duplicates overlapping signals, and publishes one of three verdicts per strategy:

- **VALID TRADE** — enter now, full trade plan provided
- **WAIT FOR LEVELS** — valid setup forming, wait for price to reach defined level
- **NO TRADE** — conditions not met

The system is **analysis only**. No auto-execution. No paid services.

### Key architectural decisions (approved)
- **Deterministic rule-based agents**, not LLM calls for detection — cost, speed, reliability
- **Shared Canonical Event Detector** feeds all 60 agents to eliminate duplicate work
- **2-layer de-duplication** via canonical signatures and parent/child strategy ancestry
- **3-phase delivery**: Phase 1 = 5 strategies; Phase 2 = all 15 strategies; Phase 3 = infrastructure migration
- **Data hybrid**: OANDA demo (primary feed) + Finnhub free (calendar) + TradingView Premium (manual verification + optional Pine alerts)
- **Narrative LLM: Gemini 2.0 Flash free tier** — invoked only on published (VALID/WAIT) signals to generate human-readable rationale in Segment 3
- **Single output surface in Phase 1: web dashboard** (3 segments). Telegram and other alert channels deferred to future phases.
- **Display timezone: IST** everywhere in the UI. Internal storage stays UTC.

---

## 2. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐     │
│  │ OANDA v20    │  │ Finnhub      │  │ TradingView Pine alerts  │     │
│  │ EURUSD,GBPUSD│  │ Econ calendar│  │ (optional webhook in)    │     │
│  │ M1/M5/M15/H1 │  │ (news filter)│  │                          │     │
│  │ /H4/Daily    │  │              │  │                          │     │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘     │
└─────────┼─────────────────┼─────────────────────┼─────────────────────┘
          │                 │                     │
┌─────────▼─────────────────▼─────────────────────▼─────────────────────┐
│                    INGESTION & STORAGE                                │
│   OANDA streaming + polling loop → SQLite (candles, events, trades)   │
└─────────────────────────────────┬─────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼─────────────────────────────────────┐
│              CANONICAL EVENT DETECTOR (shared, runs once per tick)    │
│  FVG · OB · Breaker · MSS/CHoCH · Liquidity Sweep · Swing Points ·    │
│  ATR · Premium/Discount Zone · Kill Zone · HTF Bias · SMT Divergence  │
└─────────────────────────────────┬─────────────────────────────────────┘
                                  │  canonical events bus
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
┌─────────▼────────┐    ┌─────────▼────────┐    ┌─────────▼────────┐
│ STRATEGY AGENTS  │    │ STRATEGY AGENTS  │    │ STRATEGY AGENTS  │
│   (Phase 1)      │    │   (Phase 2 add)  │    │  (Phase 2 add)   │
│  5 strategies    │    │  5 strategies    │    │  5 strategies    │
│  × 4 agents each │    │  × 4 agents each │    │  × 4 agents each │
│  = 20 agents     │    │  = 20 agents     │    │  = 20 agents     │
└─────────┬────────┘    └─────────┬────────┘    └─────────┬────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │  strategy verdicts + signatures
                                  ▼
                   ┌──────────────────────────────┐
                   │  SIGNAL CLUSTERING LAYER     │
                   │  groups duplicate setups     │
                   │  picks representative        │
                   │  applies confluence boost    │
                   └──────────────┬───────────────┘
                                  │  clustered signals
                                  ▼
                   ┌──────────────────────────────┐
                   │  FINAL DECISION GATE         │
                   │  threshold checks · RR ·     │
                   │  news filter · daily limits  │
                   └──────────────┬───────────────┘
                                  │  published trades
          ┌───────────────────────┴───────────────────────┐
          ▼                                               ▼
   ┌─────────────────────────────────┐           ┌──────────────────┐
   │  Flask Web Dashboard            │           │  SQLite          │
   │  ┌───────────────────────────┐  │           │  signals/trades/ │
   │  │ Segment 1: Performance    │  │           │  outcomes log    │
   │  │ Segment 2: Strategy cards │  │           └────────┬─────────┘
   │  │ Segment 3: Details        │  │                    │
   │  └───────────────────────────┘  │      ┌─────────────▼──────────────┐
   │  Gemini 2.0 Flash narrative ────┼─▶    │  PERFORMANCE MONITOR       │
   │  only on VALID/WAIT publish     │      │  tracks outcomes,          │
   └─────────────────────────────────┘      │  updates strategy win rates│
                                            │  feeds back into scoring   │
                                            └────────────────────────────┘
```

---

## 3. Data Layer

### 3.1 OANDA v20 (primary feed)
- **Account type:** Demo (free, permanent)
- **Instruments:** `EUR_USD`, `GBP_USD`, `DXY` equivalent if needed
- **Python SDK:** `oandapyV20`
- **Timeframes ingested:** M1, M5, M15, H1, H4, Daily
- **Mode:**
  - **Streaming** for live M1 prices (pricing stream endpoint)
  - **Polling** for historical candle top-ups on higher timeframes (every minute for M1, every 5 min for M5, etc.)
- **Reconnect policy:** exponential backoff (1s → 30s max), max 5 retries then alert
- **Auth:** API token in `.env`, never committed

### 3.2 Finnhub (economic calendar)
- **Endpoint:** `/calendar/economic`
- **Poll frequency:** every 15 minutes
- **Used by:** news-filter module; blocks trade signals ±30 min around high-impact events (USD, EUR)
- **Auth:** free API key in `.env`

### 3.3 TradingView (manual + optional Pine alerts)
- **Primary use:** visual chart verification on Maddy's laptop
- **Optional integration:** Pine Script alerts can POST JSON to a local webhook endpoint (`POST /tv-alert`) and be stored as a "second opinion" signal alongside our engine's output. Not required for Phase 1.

### 3.4 Storage — SQLite
Single file `data/smc.db`. Tables:

| Table | Purpose |
|-------|---------|
| `candles_m1`, `candles_m5`, `candles_m15`, `candles_h1`, `candles_h4`, `candles_d` | OHLCV per timeframe per instrument |
| `events` | Canonical detector outputs (sweeps, MSS, FVGs, OBs, etc.) |
| `calendar` | Economic calendar events |
| `signals` | Raw per-strategy verdicts (incl. NO TRADE) |
| `clusters` | Clustered signals with representative + members |
| `trades` | Published trades (VALID TRADE or WAIT FOR LEVELS only) |
| `outcomes` | Realized trade outcomes (hit TP/SL/manual close) |
| `agent_scores` | Per-agent scoring breakdown for audit/debate transparency |
| `strategy_stats` | Rolling win rate, avg RR, sample size per strategy |

SQLite is fine up to several years of tick data for a single pair. Migration to Postgres only needed if we later add more instruments.

---

## 4. Canonical Event Detector (CED)

**Purpose:** compute all SMC primitives ONCE per tick, so the 60 strategy agents read from a shared event bus instead of recomputing.

### 4.1 Modules inside CED

| Module | Output |
|--------|--------|
| `fvg_detector` | List of active FVGs per timeframe with top/bottom/CE/type/age/breach_status |
| `ob_detector` | Active Order Blocks (incl. Breaker/Mitigation flags) |
| `mss_detector` | Recent MSS/CHoCH events with level and direction |
| `sweep_detector` | Liquidity sweeps (BSL/SSL) on PDH/PDL/EQH/EQL/Asian range/swing highs & lows |
| `swing_points` | Rolling swing highs/lows with lookback |
| `atr_calculator` | ATR per timeframe |
| `pd_zone` | Premium/Discount split from active dealing range |
| `kill_zone_clock` | Boolean: are we currently in London KZ / NY KZ / SB window? |
| `htf_bias` | D1/H4 bias: bullish / bearish / neutral (via BOS sequence) |
| `smt_divergence` | EURUSD vs GBPUSD swing comparison → bullish/bearish/none |

### 4.2 Execution model
- Runs as a single async task on every new M1 candle close
- Emits events to an in-memory pub/sub (Python `asyncio.Queue`)
- Persists fresh events to SQLite `events` table for audit + backtesting replay
- Strategy agents subscribe to events they care about

---

## 5. Strategy Agent Framework

### 5.1 Per-strategy structure (4 agents)

```
┌─────────────────────────────────────────────────────┐
│             Strategy N (e.g., Unicorn Model)        │
├─────────────────────────────────────────────────────┤
│  Opportunity Agent 1 (primary rule compliance)      │
│    → score_1, reasons_for[]                         │
│  Opportunity Agent 2 (alternate rule lens)          │
│    → score_2, reasons_for[]                         │
│  Risk Agent 1 (disconfirming conditions set A)      │
│    → score_3, reasons_against[]                     │
│  Risk Agent 2 (disconfirming conditions set B)      │
│    → score_4, reasons_against[]                     │
├─────────────────────────────────────────────────────┤
│  Debate Aggregator                                  │
│    confidence = f(score_1, score_2, score_3, score_4)│
│    verdict    = threshold logic                     │
│    → VALID TRADE | WAIT FOR LEVELS | NO TRADE       │
└─────────────────────────────────────────────────────┘
```

### 5.2 Agent interface (rule-based, not LLM)

Each agent is a Python class with a single method:

```
evaluate(context: CanonicalContext) -> AgentOpinion
    returns: {
        score: float [0..100],
        verdict: "support" | "oppose" | "neutral",
        reasons: List[str],
        evidence: Dict       # structured pointers to events
    }
```

### 5.3 How two Opportunity agents differ (not a duplicate)
They use **different rule emphases** on the same canonical inputs:

| Opportunity Agent 1 | Opportunity Agent 2 |
|---------------------|---------------------|
| Strict rule compliance (binary pass/fail on each rule) | Quality scoring (how *clean* is the setup?) |
| Counts conditions met | Weights structure clarity, wick quality, displacement strength |
| High precision, lower recall | Higher recall, admits "B+" setups |

Agreement of both = strong setup. Disagreement = flagged for opposition review.

### 5.4 How two Risk agents differ
| Risk Agent 1 (Technical) | Risk Agent 2 (Contextual) |
|---------------------------|---------------------------|
| Looks at price structure risk: nearby opposing liquidity, HTF conflict, weak displacement, thin FVG, poor RR math | Looks at environmental risk: upcoming high-impact news, Monday filter, end-of-session, post-stop cooling period, spread widening windows |

Both must clear for a trade to publish.

### 5.5 Scoring bands (initial, tunable)

| Bucket | Score range |
|--------|-------------|
| Excellent | 85–100 |
| Good | 70–84 |
| Marginal | 55–69 |
| Weak | 0–54 |

### 5.6 Verdict decision logic (per strategy)

```
confidence   = weighted_mean(opp1, opp2) - weighted_mean(risk1_oppose, risk2_oppose)
probability  = (agreement_factor) * (confluence_factor) * (clarity_factor)

IF all rules strictly met AND confidence >= 70 AND no hard risk veto AND RR >= 2:
    → VALID TRADE
ELIF rules largely met AND trade location not yet reached AND confidence >= 60:
    → WAIT FOR LEVELS (define entry zone)
ELSE:
    → NO TRADE (record reasons)
```

Hard risk vetoes (immediate NO TRADE regardless of score):
- High-impact news within ±30 min
- Active 2-loss daily stop
- Price in wrong premium/discount zone
- Trade frequency cap for the month reached (≥15)

---

## 6. Signal Clustering Layer (de-duplication)

### 6.1 Canonical signature per signal

```
signature = (
    timestamp_bucket_5min,
    direction,                         # bullish/bearish
    sweep_level_rounded_5pips,
    mss_level_rounded_5pips,
    entry_zone_midpoint_rounded_5pips
)
```

### 6.2 Strategy ancestry table

```
ROOT: Confirmation Model (Strategy 3)
    ├── Silver Bullet (Strategy 4)          — adds time-window filter
    ├── Unicorn Model (Strategy 1)          — adds Breaker/FVG overlap
    ├── Market Maker Model (Strategy 9)     — HTF scale parent
    └── CISD (Strategy 14)                  — earlier-trigger sibling

ROOT: Daily Manipulation (Strategy 2, Judas Swing)
    └── Power of 3 (Strategy 10)            — same event, macro framing

INDEPENDENT (no parent):
    5 Nested FVGs, 6 iFVG, 7 OTE+FVG, 8 Rejection Block,
    11 Propulsion, 12 Vacuum, 13 Reclaimed FVG, 15 BPR in OB
```

### 6.3 Clustering algorithm (per tick window)

```
1. Collect all strategy signals with matching signatures within 5-minute bucket.
2. For each cluster:
     a. Pick REPRESENTATIVE:
          - most specific descendant in ancestry tree (Unicorn > SB > Confirmation)
          - if tie, highest individual confidence score
     b. CONFLUENCE BOOST:
          - 1 strategy:  +0%
          - 2 strategies: +10%
          - 3+ strategies: +15% (capped +20%)
     c. Cluster confidence = representative.confidence + boost
3. Publish clustered signal with primary + members listed.
```

**Example output:** `"Unicorn Model (primary) · confluence: Silver Bullet, Confirmation Model · boosted confidence: 88"`

---

## 7. Final Decision Gate

Before a clustered signal is published to the dashboard:

| Check | Veto? | Notes |
|-------|-------|-------|
| Confidence ≥ **75** for VALID TRADE | Yes | Strict initial threshold; tunable downward after 20+ logged signals |
| Confidence ≥ **65** for WAIT FOR LEVELS | Yes | Slightly permissive; WAIT is observational, not execution |
| RR ≥ 2.0 | Yes | |
| Not within ±30 min of high-impact USD/EUR news | Yes | Source: Finnhub economic calendar |
| **Monday veto** | **Yes** | Hard veto — no signals published on Mondays (historical 44% WR per source doc) |
| Active 2-loss daily stop not triggered | Yes | Counter resets at 00:00 IST |
| Monthly trade count < 15 | Yes | Counter resets on 1st of month |
| Spread within acceptable band (< 1.5 pips EURUSD) | Yes | From live OANDA pricing stream |
| Cooling period (20 min) since last stopped-out trade cleared | Yes | |

Failures are logged to `signals` table with veto reason but NOT published to Segment 2. Operator can review them in Segment 1's history filter.

---

## 8. Output Formats

### Option A — NO TRADE
```
Strategy: <name>
Status:   NO TRADE
Confidence: <0-100>
Rejection reasons:
  - <primary reason>
  - <secondary reasons>
```

### Option B — VALID TRADE
```
Strategy:         <name>
Status:           VALID TRADE
Cluster members:  <list of confluent strategies, if any>
Direction:        BUY | SELL
Entry:            1.XXXXX
Stop Loss:        1.XXXXX
Take Profit 1:    1.XXXXX (partial 50%)
Take Profit 2:    1.XXXXX (runner 50%)
Take Profit 3:    1.XXXXX (optional)
Risk-Reward:      1:X.X
Confidence:       XX / 100
Probability:      XX / 100
Timeframes:       <entry TF, bias TF>
Reasons FOR:      <list from Opportunity agents>
Reasons AGAINST:  <list from Risk agents>
Final verdict:    <one-line summary>
```

### Option C — WAIT FOR LEVELS
```
Strategy:            <name>
Status:              WAIT FOR LEVELS
Direction Bias:      BUY | SELL
Wait-for Zone:       1.XXXXX – 1.XXXXX
Precise Entry:       1.XXXXX
Stop Loss:           1.XXXXX
Take Profit 1:       1.XXXXX
Take Profit 2:       1.XXXXX
Take Profit 3:       1.XXXXX (optional)
Estimated RR:        1:X.X
Confidence:          XX / 100
Probability:         XX / 100
Conditions to meet:  <checklist before entry>
Reasons FOR:         <list>
Reasons AGAINST:     <list>
Final verdict:       <one-line summary>
```

---

## 9. Web Dashboard — 3-Segment Design

The dashboard is the **sole output surface in Phase 1**. Three segments reflect how a trader actually consumes the system:

1. **Overall Dashboard / Performance** — "How am I doing?"
2. **Strategy Summary (cards)** — "What is each strategy saying right now?"
3. **Details (per-setup reasoning)** — "Why? Convince me."

Framework: Flask backend + server-rendered templates + Plotly.js for charts. Vanilla JS (no heavy frontend framework). All times displayed in IST.

### 9.1 Segment 1 — Overall Dashboard / Performance

**Route:** `/` (landing page)

**Purpose:** track historical and in-flight performance at a glance.

| Component | Contents |
|-----------|----------|
| Headline stats strip | Cumulative R · overall win rate · avg RR · expectancy · trades this month (X/15 cap) · today's P&L in R |
| Equity curve chart | Plotly line chart of cumulative R over time; toggle: per-strategy overlay |
| Strategy leaderboard | Table: strategy · trades · win rate · avg RR · expectancy · cumulative R. Sortable, color-coded |
| Day/session heatmap | Win rate by day-of-week × session (London/NY AM/NY PM) |
| Daily summary card | Today: signals fired, trades taken, wins/losses, daily-loss-stop status (active/cleared), next session countdown (IST) |
| Filters | Date range, strategy, session, cluster size |

### 9.2 Segment 2 — Strategy Summary (cards)

**Route:** `/strategies`

**Purpose:** live board showing current state of every enabled strategy.

- One card per active strategy (5 in Phase 1, 15 in Phase 2)
- Grid layout: 3-4 cards per row on desktop, 1 per row on mobile
- Auto-refresh every 15 seconds
- **Economic calendar ticker strip** pinned at the top: next high-impact USD/EUR event + countdown + "BLACKOUT ACTIVE" label if within ±30 min

**Each card contains:**

| Element | Purpose |
|---------|---------|
| Strategy name + short description | Identification |
| Status badge | `VALID TRADE` (green) · `WAIT FOR LEVELS` (amber) · `NO TRADE` (grey) |
| Primary metrics (if VALID or WAIT) | Direction (BUY/SELL), Entry, SL, TP1, TP2, RR |
| Confidence / Probability | Two numeric chips (0–100) |
| Rejection reason (if NO TRADE) | One-line text |
| Cluster indicator | Badge like `+ Silver Bullet, Confirmation` if this strategy is part of a confluence cluster |
| Recent history dots | Last 10 signals as win/loss/no-trade dots |
| 30-day win rate chip | Small stat |
| Details button | Opens Segment 3 for this signal |

**Settings access:** gear icon top-right of page → modal for per-strategy enable/disable, confidence threshold overrides, API key management.

### 9.3 Segment 3 — Details (per-setup reasoning)

**Route:** `/signal/<signal_id>` (full page) or modal overlay from Segment 2 card click.

**Purpose:** full transparency — every reason for and against the setup, so Maddy can choose to take or skip with full context.

**Panels:**

1. **Trade card (top)** — full Option A/B/C output (Direction, Entry, SL, TP1–TP3, RR, Confidence, Probability, Timeframes, Final verdict)
2. **Agent debate panel**
   - Opportunity Agent 1 — score, verdict, bullet-list reasons for
   - Opportunity Agent 2 — score, verdict, bullet-list reasons for
   - Risk Agent 1 (Technical) — score, verdict, bullet-list reasons against
   - Risk Agent 2 (Contextual) — score, verdict, bullet-list reasons against
   - Final confidence math shown transparently: weighted_mean(opp) − weighted_mean(risk) = confidence; agreement × confluence × clarity = probability
3. **Evidence panel**
   - Structured view of the canonical events this setup rests on: FVG zone (top/bottom/CE), MSS level, sweep candle timestamp + wick price, HTF bias, premium/discount zone, ATR value, kill zone window active
   - "Show raw detector output" expandable JSON block
4. **Chart snapshot**
   - Plotly candlestick of the relevant timeframe with FVG/OB/MSS/sweep annotations drawn on
   - Deep-link button: "Open in TradingView" (pre-fills symbol + timeframe + datetime for manual verification)
5. **Gemini narrative**
   - Human-readable paragraph auto-generated when signal was first published
   - Example: *"At 13:47 IST, EURUSD swept the Asian session low (1.08241) by 3 pips before reversing sharply. The rejection printed a Bullish MSS at 1.08315 and left a clean 5-pip FVG between 1.08270 and 1.08275 — overlapping with a Breaker Block from the prior London session sweep. Setup qualifies as Unicorn Model within the 13:30–14:30 IST Silver Bullet window…"*
6. **Outcome actions**
   - "I took this trade" / "I skipped" buttons — updates `trades.execution_status`
   - If taken: free-text lot size field (for realized P&L tracking, separate from theoretical R)
   - If closed: mark TP1/TP2/SL/manual_close

### 9.4 Design priorities
- Dark theme, trader-friendly (high contrast, monospaced numerics)
- Zero-click latency for refresh (Server-Sent Events or 15s polling; SSE preferred)
- Copy-to-clipboard buttons on every price level
- All timestamps displayed in IST with UTC in tooltip for clarity
- Mobile-readable (Segment 2 cards stack vertically) — useful for checking setups away from desk

---

## 10. Alerting — deferred

**Phase 1: no push alerts.** The web dashboard (Segment 2) is the sole notification surface; Maddy checks it during trading windows.

**Future phases (optional, user decision):** Telegram bot, email, or browser push notifications. Nothing in the Phase 1 architecture precludes adding any of these later — the published-signal event stream can fan out to any additional channel without engine changes.

---

## 11. Performance Monitoring

### 11.1 Outcome capture
- Each published trade recorded to `trades` with initial parameters
- Engine polls live price and marks outcome: `TP1_hit`, `TP2_hit`, `SL_hit`, `manual_close`
- Manual override available in dashboard (Maddy can mark trades he did NOT take, to track theoretical vs taken performance)

### 11.2 Rolling statistics per strategy
- Win rate (last 30 trades, last 90 days, all-time)
- Average RR achieved
- Expectancy = (WR × avg_win_R) − ((1 − WR) × 1)
- Per-day-of-week and per-session breakdown
- Per-cluster-size breakdown (did "3 strategy confluence" beat "1 strategy" historically?)

### 11.3 Feedback into scoring
- Starting `confidence_multiplier` per strategy = 1.0 (win rate unknown)
- After 20 trades: multiplier adjusts from `expectancy`
- Strategies with negative expectancy over 50+ trades → auto-flagged for review (not auto-disabled; Maddy decides)

---

## 12. Directory & Module Structure

```
SMC-TradeAgents/
├── EURUSD SMC best strategies.md          # source doc
├── SMC_Algorithmic_Trading_Specifications.md  # source doc
├── .claude/
│   └── Documents/
│       └── system_architecture.md         # THIS FILE
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── config/
│   ├── settings.py                        # thresholds, toggles
│   └── instruments.py                     # symbol metadata, pip values
├── data/
│   └── smc.db                             # SQLite (gitignored)
├── app/
│   ├── __init__.py
│   ├── main.py                            # entrypoint, async loop
│   ├── ingestion/
│   │   ├── oanda_client.py
│   │   ├── finnhub_client.py
│   │   └── tv_webhook.py                  # optional
│   ├── storage/
│   │   ├── db.py                          # SQLite schema + migrations
│   │   └── repositories.py
│   ├── detector/                          # Canonical Event Detector
│   │   ├── fvg.py
│   │   ├── order_block.py
│   │   ├── mss.py
│   │   ├── sweep.py
│   │   ├── swings.py
│   │   ├── atr.py
│   │   ├── pd_zone.py
│   │   ├── kill_zone.py
│   │   ├── htf_bias.py
│   │   └── smt_divergence.py
│   ├── strategies/
│   │   ├── base.py                        # Strategy + Agent interfaces
│   │   ├── debate.py                      # aggregator
│   │   ├── strategy_01_unicorn.py
│   │   ├── strategy_02_judas.py
│   │   ├── strategy_03_confirmation.py
│   │   ├── strategy_04_silver_bullet.py
│   │   ├── strategy_06_ifvg.py
│   │   └── ... (phase 2 and 3 added later)
│   ├── clustering/
│   │   └── cluster_engine.py
│   ├── gate/
│   │   └── decision_gate.py
│   ├── narrative/
│   │   └── gemini_client.py               # generates Segment 3 narrative on publish
│   ├── performance/
│   │   ├── tracker.py
│   │   └── stats.py
│   └── dashboard/
│       ├── flask_app.py
│       ├── routes/
│       │   ├── segment_1_performance.py
│       │   ├── segment_2_strategies.py
│       │   └── segment_3_details.py
│       ├── templates/
│       │   ├── base.html
│       │   ├── segment_1.html
│       │   ├── segment_2.html
│       │   └── segment_3.html
│       └── static/
│           ├── css/
│           └── js/
├── tests/
│   ├── detector/
│   ├── strategies/
│   └── fixtures/                          # recorded OANDA candles for replay
└── scripts/
    ├── backfill_history.py                # seed DB with N years of OANDA candles
    └── replay_day.py                      # re-run engine on a past day for debugging
```

---

## 13. Phase Plan

### Phase 1 — Foundations
**Scope:** Data layer + CED + 5 strategies + clustering + gate + dashboard + Telegram.

**Strategies:** 3 Confirmation, 4 Silver Bullet, 2 Judas, 1 Unicorn, 6 iFVG.

**Deliverable:** End-to-end working system producing VALID/WAIT/NO TRADE signals on live EURUSD during London & NY sessions, with audit trail.

### Phase 2 — Full strategy expansion (all 15 strategies)
**Adds:** 5 Nested FVGs, 7 OTE+FVG, 8 Rejection Block, 9 Market Maker Model, 10 Power of 3, 11 Propulsion Block, 12 Vacuum Block, 13 Reclaimed FVG, 14 CISD, 15 BPR in OB.

**New CED primitives required:** Fibonacci module (body-to-body), long-wick classifier, gap detector, AMD phase tracker, MMM phase state machine, FVG CE-test history enrichment.

**Deliverable:** All 15 strategies live, Segment 2 showing 15 cards, full clustering ancestry tree active, dashboard evidence panels for all strategy types.

**Gate to Phase 3:** Phase 2 engine stable for ≥2 weeks; ≥25 signals recorded; at least one signal from each of the 10 new strategies observed.

### Phase 3 — Infrastructure migration (Oracle Cloud Always Free)
**Scope:** Migrate from Mac launchd to Oracle Cloud Always Free VM (1 OCPU ARM, 6 GB RAM) for 24/7 uptime. No new strategies or analysis logic.

**Deliverables:**
- Engine deployed to Oracle Cloud Always Free VM via `systemd`
- Dashboard behind Cloudflare Tunnel (free) with HTTP basic auth
- Mac retained as fallback during migration testing period
- Uptime target: < 10 minutes cumulative downtime per month

**Gate to Phase 3:** Oracle Cloud account created by Maddy; Cloudflare Tunnel configured.

---

## 14. Technology Stack Summary

| Layer | Choice | Cost |
|-------|--------|------|
| Language | Python 3.11+ | Free |
| Async runtime | `asyncio` | Free |
| HTTP | `httpx` | Free |
| OANDA SDK | `oandapyV20` | Free (demo account) |
| Data crunching | `pandas`, `numpy` | Free |
| DB | `sqlite3` via `SQLAlchemy` core (no ORM overkill) | Free |
| Web framework | `Flask` (you already use it in Gold Strategy) | Free |
| Live push to browser | Server-Sent Events (`flask-sse` or plain SSE) | Free |
| Charts in dashboard | `Plotly.js` (client-side, CDN) | Free |
| Scheduler | `APScheduler` | Free |
| **Narrative LLM** | **Gemini 2.0 Flash via `google-generativeai` SDK** (free tier: 15 RPM / 1M tokens per day — far above our ~5 calls/day need) | Free |
| Testing | `pytest` | Free |
| Formatting / lint | `ruff` (single tool) | Free |
| Env | `python-dotenv` | Free |
| Process manager (Phase 1) | `launchd` plist on Mac (auto-start at login) | Free |
| Process manager (Phase 3 migration) | `systemd` on Oracle Cloud Always Free VM | Free |

No paid services. TradingView Premium used for manual verification only (already paid, not a project cost).

---

## 15. Risk Controls (codified in the gate)

| Rule | Enforcement |
|------|-------------|
| 1% max risk per trade | Position-size calculator in trade card (Segment 3) |
| Two-loss daily stop | Gate veto after 2 losses today; resets 00:00 IST |
| 20-min cooling period | Gate veto after any stop-out |
| 15 trades / month cap | Gate veto on 16th signal; resets 1st of month IST |
| **Monday veto** | **Gate hard veto — no signals published on Mondays** |
| News blackout ±30 min | Gate veto on high-impact USD/EUR events (Finnhub feed) |
| Spread cap | Gate veto if EURUSD spread > 1.5 pips |
| VALID confidence floor | ≥ 75 |
| WAIT confidence floor | ≥ 65 |

Confluence boost accepted as starting values: +10% for 2-strategy cluster, +15% for 3+ strategies, cap +20%.

---

## 16. Security & Secrets

- `.env` contains: `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `FINNHUB_API_KEY`, `GEMINI_API_KEY`, `FLASK_SECRET_KEY`
- `.env` in `.gitignore`, `.env.example` committed with placeholders
- No keys ever logged
- SQLite file in `data/`, gitignored
- Dashboard bound to `127.0.0.1` only (local-only, no public exposure in Phase 1)
- When Phase 3 migrates to Oracle Cloud: dashboard behind Cloudflare Tunnel (free) with basic auth — not publicly indexable

---

## 17. What this document deliberately does NOT include

- Full strategy pseudocode (already exists in `SMC_Algorithmic_Trading_Specifications.md`)
- Exact scoring weights per agent (to be tuned during Phase 1 implementation with live feedback)
- Pine Script snippets for TradingView (optional, Phase 1.5 if desired)
- Backtest engine design (separate doc; simple replay harness sufficient for Phase 1)
- Dashboard HTML/CSS — layout described, visuals tuned during build

---

## 18. Resolved design decisions (previously open questions)

All Section 18 questions from v1.0 have been answered. Locked decisions:

| # | Question | Decision |
|---|----------|----------|
| 1 | Telegram bot | **Deferred out of Phase 1.** Web dashboard is the sole output surface. |
| 2 | OANDA demo account | Not yet registered — included as Phase 1 setup task (register + generate token). |
| 3 | Hosting | **Mac launchd for Phase 1 and Phase 2** (fast iteration, simple). Migration to Oracle Cloud Always Free VM in Phase 3 once all 15 strategies are stable and 24/7 uptime matters more than iteration speed. |
| 4 | Confluence boost | **Accepted as starting values**: +10% for 2-strategy, +15% for 3+, cap +20%. Tunable after Phase 1 data. |
| 5 | Monday filter | **Hard veto** — no signals published on Mondays. Simpler than a penalty, aligned with source doc's 44% WR warning. |
| 6 | VALID confidence threshold | **75** (strict). WAIT threshold = 65. Both tunable after 20+ logged signals per strategy. |
| 7 | Timezone | **Display in IST** (Asia/Kolkata, UTC+5:30). Internal UTC. |
| 8 | LLM narrative | **Gemini 2.0 Flash free tier**, included in Phase 1. Runs only on VALID/WAIT publish (~≤5 calls/day). |

### Kill Zone reference in IST (for Segment 2 ticker + gate checks)

| Window (source doc EST) | UTC | **IST (displayed)** |
|--------------------------|-----|---------------------|
| London KZ (02:00–05:00 EST) | 07:00–10:00 | **12:30–15:30** |
| NY KZ (07:00–10:00 EST) | 12:00–15:00 | **17:30–20:30** |
| Silver Bullet — London (03:00–04:00 EST) | 08:00–09:00 | **13:30–14:30** |
| Silver Bullet — NY AM (10:00–11:00 EST) | 15:00–16:00 | **20:30–21:30** |
| Silver Bullet — NY PM (14:00–15:00 EST) | 19:00–20:00 | **00:30–01:30 (next day)** |
| Asian session (19:00–02:00 EST) | 00:00–07:00 | **05:30–12:30** |

All prime trading windows fall within reasonable waking hours in IST.

---

## 19. Approval needed before implementation

This document is a design only. No code has been written.

**Next artifact (on approval):** Phase 1 implementation plan — task breakdown, sequencing, test approach, milestone checklist. Still a document, not code, until you greenlight that too.

Per the standing rule, implementation begins only after explicit confirmation.
