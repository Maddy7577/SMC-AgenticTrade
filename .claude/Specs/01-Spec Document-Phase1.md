# Phase 1 — Specification Document

**Project:** SMC-TradeAgents
**Phase:** 1 (Foundations)
**Version:** 1.0
**Date:** 2026-04-16
**Status:** Draft — awaiting approval
**Owner:** Maddy
**Author:** Architecture designer
**Parent document:** `.claude/Documents/system_architecture.md` (v1.1)

---

## 1. Purpose & Scope

### 1.1 Purpose
Deliver a working end-to-end EURUSD trade intelligence engine covering **5 SMC strategies**, each evaluated by a 4-agent debate framework, with signal clustering, decision gating, a 3-segment web dashboard, and performance tracking from day one. The system must run on Maddy's Mac using only free services.

### 1.2 In-scope for Phase 1

| Area | Inclusion |
|------|-----------|
| Data ingestion | OANDA v20 (EURUSD + GBPUSD), Finnhub economic calendar |
| Storage | SQLite database with schema for candles, events, signals, clusters, trades, outcomes, agent scores, strategy stats |
| Canonical Event Detector (CED) | FVG, Order Block, Breaker Block, MSS/CHoCH, Liquidity Sweep, Swing Points, ATR, Premium/Discount, Kill Zone, HTF Bias, SMT Divergence |
| Strategies (5) | #3 Confirmation Model, #4 Silver Bullet, #2 Judas Swing, #1 Unicorn Model, #6 iFVG |
| Agent framework | 4 agents per strategy (2 Opportunity + 2 Risk), deterministic Python, debate aggregator |
| Signal clustering | Canonical signatures, ancestry-aware representative selection, confluence boost |
| Decision gate | All veto rules from architecture §7, §15 |
| Output formats | Option A (NO TRADE), Option B (VALID TRADE), Option C (WAIT FOR LEVELS) |
| Web dashboard | 3 segments (Performance, Strategy Cards, Details), Flask + Plotly |
| Narrative LLM | Gemini 2.0 Flash free tier, invoked on VALID/WAIT publish |
| Performance monitor | Outcome capture, rolling stats, expectancy calc, manual override |
| Process management | `launchd` plist for auto-start on Mac login |

### 1.3 Out-of-scope for Phase 1 (deferred to Phase 2 / 3 / later)

| Area | Reason |
|------|--------|
| Strategies 5, 7, 8, 9, 10, 11, 12, 13, 14, 15 | Deferred to Phases 2 and 3 |
| Telegram / email / push alerts | Dashboard is sole output surface in Phase 1 |
| TradingView Pine alert webhook inbound | Optional; dashboard's TV deep-link is sufficient for Phase 1 |
| Cloud hosting (Oracle Cloud Always Free) | Phase 2+ migration once system stable |
| Auto-execution / broker order placement | Not a goal of this project |
| Backtesting engine with equity reports | Phase 1 uses simple replay harness for dev/debug; formal backtest module is Phase 2 |
| Additional instruments beyond EURUSD | Only EURUSD is target; GBPUSD ingested solely for SMT Divergence |
| Multi-user auth | Single-user local-only dashboard |

---

## 2. User Stories

### 2.1 Primary persona
Maddy, discretionary EURUSD trader using SMC, IST timezone, seeking algorithmic confirmation and discipline rather than auto-execution.

### 2.2 Stories

**US-01: Live strategy board**
> As Maddy, I want to see at a glance what each of the 5 enabled strategies is currently saying, so I can assess the market state without reading charts manually.
> **Acceptance:** Segment 2 loads in < 2 seconds, shows one card per strategy with current status, auto-refreshes every 15 seconds.

**US-02: Transparent trade reasoning**
> As Maddy, when a VALID TRADE signal fires, I want to see every reason for and against it, so I can decide whether to take it with full context.
> **Acceptance:** Segment 3 shows all 4 agent opinions with scores, reasons, and supporting evidence; chart snapshot rendered; Gemini narrative generated and shown.

**US-03: Wait-for-level tracking**
> As Maddy, when a setup is forming but price hasn't reached entry, I want the system to tell me the exact price to wait for, along with the full trade plan.
> **Acceptance:** Segment 2 card shows WAIT FOR LEVELS status with wait-zone price range; Segment 3 shows the conditions that must be met before entry qualifies as VALID.

**US-04: Performance tracking**
> As Maddy, I want to see how each strategy is performing over time, so I know which strategies deserve my trust.
> **Acceptance:** Segment 1 shows equity curve, strategy leaderboard, win rate heatmap; data persists across restarts.

**US-05: Manual outcome capture**
> As Maddy, I want to mark which trades I actually took (vs skipped), so my real performance is tracked separately from theoretical.
> **Acceptance:** Segment 3 has "I took / I skipped" buttons; outcomes persisted to DB; stats filterable by taken/theoretical.

**US-06: No trade on Mondays**
> As Maddy, I don't want any trade signals on Mondays given the historical 44% win rate.
> **Acceptance:** Any signal originating on a Monday (IST) is logged but never published to Segment 2; shown in Segment 1 history filter as "vetoed — Monday".

**US-07: News blackout**
> As Maddy, I want signals suppressed around high-impact USD/EUR news.
> **Acceptance:** Within ±30 minutes of a high-impact event, signals are vetoed; Segment 2 ticker shows "BLACKOUT ACTIVE" badge with event details.

**US-08: Discipline enforcement**
> As Maddy, I want the system to enforce my own rules (max 15 trades/month, 2-loss daily stop, 20-min cooling) automatically.
> **Acceptance:** Gate veto fires when any limit breached; dashboard shows current counters (trades this month, losses today, cooling expiry).

**US-09: Confluence awareness**
> As Maddy, when multiple strategies agree on the same setup, I want to know — but I don't want to be fooled by overlapping strategies firing on the same price action as "confluence".
> **Acceptance:** Clustering layer de-duplicates; card shows cluster badge with member strategies; confidence boosted per rules; no signal is double-counted.

**US-10: System resilience**
> As Maddy, if the OANDA connection drops, I want the system to reconnect automatically and not miss signals.
> **Acceptance:** Exponential backoff reconnect; missed candles backfilled on reconnect; health indicator in dashboard shows connection state.

---

## 3. Functional Requirements

### 3.1 Data ingestion — FR-D

| ID | Requirement |
|----|-------------|
| FR-D-01 | System SHALL authenticate to OANDA v20 demo using API token from `.env` |
| FR-D-02 | System SHALL stream live M1 pricing for `EUR_USD` and `GBP_USD` |
| FR-D-03 | System SHALL poll OANDA for closed candles on M1, M5, M15, H1, H4, D timeframes for both instruments |
| FR-D-04 | System SHALL persist every closed candle to SQLite, deduplicated by (instrument, timeframe, candle_time) |
| FR-D-05 | System SHALL backfill the last 30 days of M1/M5/M15 and 1 year of H1/H4/D on first run |
| FR-D-06 | System SHALL detect stream disconnects and reconnect with exponential backoff (1s, 2s, 4s, 8s, 16s, 30s max) |
| FR-D-07 | On reconnect, system SHALL backfill any missed candles before resuming live processing |
| FR-D-08 | System SHALL poll Finnhub `/calendar/economic` every 15 minutes and persist events for USD and EUR currency filters |
| FR-D-09 | System SHALL expose a health indicator (connection state, last candle time, calendar last refresh) to the dashboard |

### 3.2 Canonical Event Detector — FR-C

| ID | Requirement |
|----|-------------|
| FR-C-01 | On every closed M1 candle, CED SHALL compute updated FVGs, OBs, Breaker Blocks, sweeps, swing points, and MSS events across all relevant timeframes |
| FR-C-02 | FVG detection SHALL follow the 3-candle rule (C1 wick does not overlap C3 wick) with minimum 5-pip size for EURUSD |
| FR-C-03 | FVG state SHALL track: `formed`, `retested`, `partially_filled`, `fully_filled`, `inverted` |
| FR-C-04 | Order Block detection SHALL require 2× ATR displacement and identify last opposite-color candle before move |
| FR-C-05 | Breaker Block SHALL be flagged when an OB is invalidated by price trading through it after a liquidity sweep |
| FR-C-06 | Liquidity Sweep detection SHALL monitor PDH, PDL, Equal Highs/Lows (5-pip tolerance), Asian session H/L, and recent swing H/L |
| FR-C-07 | MSS/CHoCH detection SHALL require a break of the most recent swing plus displacement |
| FR-C-08 | Premium/Discount zone SHALL be computed from the most recent H4/Daily dealing range |
| FR-C-09 | Kill Zone clock SHALL return current window membership in IST: London KZ, NY KZ, Silver Bullet London, Silver Bullet NY AM, Silver Bullet NY PM, Asian session, or none |
| FR-C-10 | HTF Bias SHALL return `bullish` / `bearish` / `neutral` derived from D1 and H4 BOS sequence |
| FR-C-11 | SMT Divergence SHALL compare EURUSD vs GBPUSD swing points within the last 50 M5 candles and return `bullish` / `bearish` / `none` |
| FR-C-12 | All CED outputs SHALL be persisted to `events` table with timestamp, type, timeframe, and structured payload |
| FR-C-13 | CED SHALL emit new events to an in-process pub/sub queue consumed by strategy agents |

### 3.3 Strategies & agents — FR-S

| ID | Requirement |
|----|-------------|
| FR-S-01 | System SHALL implement 5 strategies in Phase 1: #3 Confirmation Model, #4 Silver Bullet, #2 Judas Swing, #1 Unicorn Model, #6 iFVG |
| FR-S-02 | Each strategy SHALL have exactly 4 agents: Opportunity Agent 1, Opportunity Agent 2, Risk Agent 1 (Technical), Risk Agent 2 (Contextual) |
| FR-S-03 | Each agent SHALL implement the signature `evaluate(context) -> AgentOpinion` returning score [0–100], verdict (support/oppose/neutral), reasons list, and evidence dict |
| FR-S-04 | Opportunity Agent 1 SHALL apply strict rule compliance (binary pass/fail on each rule) |
| FR-S-05 | Opportunity Agent 2 SHALL apply setup quality scoring (structure cleanness, displacement strength, wick quality) |
| FR-S-06 | Risk Agent 1 (Technical) SHALL evaluate nearby opposing liquidity, HTF conflict, weak displacement, thin FVG, poor RR math |
| FR-S-07 | Risk Agent 2 (Contextual) SHALL evaluate news calendar proximity, Monday, end-of-session, post-stop cooling, spread state |
| FR-S-08 | Each strategy SHALL produce one verdict per evaluation cycle: VALID TRADE, WAIT FOR LEVELS, or NO TRADE |
| FR-S-09 | Verdict decision logic: VALID when confidence ≥ 75 AND all rules strict-met AND RR ≥ 2 AND no hard veto; WAIT when setup valid but price not at entry zone AND confidence ≥ 65; else NO TRADE |
| FR-S-10 | All verdicts (including NO TRADE) SHALL be persisted to `signals` table with per-agent scores in `agent_scores` table |

### 3.4 Strategy-specific behavior — FR-SP

#### Strategy #3 — Confirmation Model
| ID | Requirement |
|----|-------------|
| FR-SP-03-01 | SHALL require ALL FIVE conditions: liquidity taken, MSS present, FVG present, HTF bias aligned, premium/discount aligned |
| FR-SP-03-02 | Entry zone SHALL be FVG boundary or CE (50%) |
| FR-SP-03-03 | SL SHALL be beyond swept wick + 0.75× ATR buffer |
| FR-SP-03-04 | TP1 = entry ± 2× risk (fixed 1:2 RR); TP2 = opposing liquidity pool from H4 |

#### Strategy #4 — Silver Bullet
| ID | Requirement |
|----|-------------|
| FR-SP-04-01 | SHALL only fire within IST windows: 13:30–14:30, 20:30–21:30, 00:30–01:30 |
| FR-SP-04-02 | Both setup and entry SHALL occur within the active 1-hour window |
| FR-SP-04-03 | SHALL require minimum 15-pip distance from entry to target liquidity |
| FR-SP-04-04 | Two SL methods supported: Conservative (beyond sweep extreme), Aggressive (beyond FVG boundary). Phase 1 uses Conservative by default |

#### Strategy #2 — Judas Swing
| ID | Requirement |
|----|-------------|
| FR-SP-02-01 | SHALL mark Asian session H/L (IST 05:30–12:30) |
| FR-SP-02-02 | SHALL detect false breakout of Asian range during London KZ (IST 12:30–15:30) against daily bias |
| FR-SP-02-03 | SHALL require MSS confirmation on M1–M5 after sweep |
| FR-SP-02-04 | Entry via FVG or OB from displacement; SL 10–20 pips beyond Judas swing extreme |
| FR-SP-02-05 | TP1 = opposite side of Asian range; TP2 = PDH/PDL |

#### Strategy #1 — Unicorn Model
| ID | Requirement |
|----|-------------|
| FR-SP-01-01 | SHALL require FVG to geometrically overlap Breaker Block with ≥ 10% overlap |
| FR-SP-01-02 | Entry zone SHALL be the CE (50%) of the overlap region |
| FR-SP-01-03 | SL SHALL be beyond Breaker Block extreme + max(10 pips, 0.5× ATR) |
| FR-SP-01-04 | TP1 = nearest internal liquidity; TP2 = next external liquidity pool (target RR ≥ 3) |
| FR-SP-01-05 | Preferred session: NY AM Silver Bullet window (IST 20:30–21:30) |

#### Strategy #6 — Inverse FVG (iFVG)
| ID | Requirement |
|----|-------------|
| FR-SP-06-01 | SHALL require candle BODY (not wick) to close through the entire original FVG to qualify as iFVG |
| FR-SP-06-02 | SHALL require prior liquidity sweep at a key level |
| FR-SP-06-03 | SMT Divergence (EURUSD vs GBPUSD) SHALL be a strongly-weighted confluence factor but not a hard requirement |
| FR-SP-06-04 | Entry at iFVG boundary or CE; SL at wider of (beyond iFVG zone + 10 pips) or (beyond sweep wick) |
| FR-SP-06-05 | Preferred window: NY session onward (IST 17:30+) |

### 3.5 Signal clustering — FR-CL

| ID | Requirement |
|----|-------------|
| FR-CL-01 | Each strategy signal SHALL carry a canonical signature: (timestamp_bucket_5min, direction, sweep_level_rounded_5pips, mss_level_rounded_5pips, entry_zone_midpoint_rounded_5pips) |
| FR-CL-02 | Clustering SHALL group signals with matching signatures within a 5-minute bucket |
| FR-CL-03 | For a cluster, representative SHALL be the most specific descendant in the ancestry tree (Unicorn > Silver Bullet > Confirmation Model); tie-break by highest individual confidence |
| FR-CL-04 | Confluence boost SHALL apply to representative's confidence: +10% for 2-strategy cluster, +15% for 3+ strategies, cap at +20% |
| FR-CL-05 | Cluster record SHALL list all member strategies and persist to `clusters` table |
| FR-CL-06 | Dashboard SHALL display cluster members on Segment 2 cards as a confluence badge |

### 3.6 Decision gate — FR-G

| ID | Requirement |
|----|-------------|
| FR-G-01 | Gate SHALL veto any signal with confidence < 75 for VALID or < 65 for WAIT |
| FR-G-02 | Gate SHALL veto any VALID signal with RR < 2.0 |
| FR-G-03 | Gate SHALL veto any signal within ±30 minutes of a high-impact USD or EUR event (Finnhub impact='high') |
| FR-G-04 | Gate SHALL veto any signal with IST day-of-week == Monday |
| FR-G-05 | Gate SHALL veto any signal when current daily losses ≥ 2 (counter resets at 00:00 IST) |
| FR-G-06 | Gate SHALL veto any signal when current month trade count ≥ 15 (counter resets on 1st of month IST) |
| FR-G-07 | Gate SHALL veto any signal when current EURUSD spread > 1.5 pips |
| FR-G-08 | Gate SHALL veto any signal within 20 minutes of the most recent stop-out |
| FR-G-09 | Vetoed signals SHALL be persisted with veto reason; NOT published to Segment 2 |
| FR-G-10 | Published signals SHALL fan out to: `trades` table write, Gemini narrative request, Segment 2 card update (SSE push) |

### 3.7 Narrative generation — FR-N

| ID | Requirement |
|----|-------------|
| FR-N-01 | System SHALL call Gemini 2.0 Flash via `google-generativeai` SDK for narrative generation on every VALID or WAIT publish |
| FR-N-02 | Prompt SHALL include: strategy name, rules summary, canonical evidence (FVG/MSS/sweep details), agent scores, trade parameters |
| FR-N-03 | Target output: 80–150 word human-readable rationale in plain English, trader tone, IST timestamps |
| FR-N-04 | Failures (rate limit, API error) SHALL be logged and show fallback text "Narrative unavailable" in Segment 3 — signal must still be published |
| FR-N-05 | Narrative SHALL be persisted to `trades.narrative` column, never re-generated for the same signal |

### 3.8 Dashboard — FR-UI

| ID | Requirement |
|----|-------------|
| FR-UI-01 | Dashboard SHALL be a Flask application bound to 127.0.0.1 only |
| FR-UI-02 | Segment 1 (`/`) SHALL render Performance view with equity curve, leaderboard, heatmap, daily summary |
| FR-UI-03 | Segment 2 (`/strategies`) SHALL render one card per enabled strategy with auto-refresh via SSE or 15s polling |
| FR-UI-04 | Segment 3 (`/signal/<id>`) SHALL render trade card, agent debate panel, evidence panel, chart snapshot, Gemini narrative, outcome action buttons |
| FR-UI-05 | All timestamps in UI SHALL be displayed in IST (Asia/Kolkata); UTC shown in tooltip |
| FR-UI-06 | Economic calendar ticker SHALL pin at top of Segment 2 with next high-impact event and countdown |
| FR-UI-07 | Settings modal (gear icon) SHALL allow per-strategy enable/disable, confidence threshold overrides, API key view/edit |
| FR-UI-08 | Dashboard SHALL use dark theme, high contrast, monospaced numerics |
| FR-UI-09 | Segment 2 SHALL be mobile-readable (single column stacking) |
| FR-UI-10 | Every price level in Segment 3 SHALL have a copy-to-clipboard button |
| FR-UI-11 | Segment 3 SHALL provide a "Open in TradingView" deep-link pre-filling symbol, timeframe, and datetime |

### 3.9 Performance monitor — FR-P

| ID | Requirement |
|----|-------------|
| FR-P-01 | On publish, system SHALL record a trade to `trades` with status `open`, initial entry/SL/TP levels, and strategy reference |
| FR-P-02 | Engine SHALL poll live price and mark outcome: `tp1_hit`, `tp2_hit`, `sl_hit`, `manual_close` |
| FR-P-03 | User SHALL be able to override outcome via Segment 3 action buttons (I took / I skipped, closed at X) |
| FR-P-04 | Realized R SHALL be calculated from entry, exit, and initial risk |
| FR-P-05 | Rolling strategy stats SHALL be recomputed on every outcome update: 30-day WR, all-time WR, avg RR, expectancy |
| FR-P-06 | Stats SHALL be filterable by taken vs theoretical, day-of-week, session, cluster size |
| FR-P-07 | Strategies with ≥ 50 outcomes AND negative expectancy SHALL be flagged for review in Segment 1 (NOT auto-disabled) |

---

## 4. Non-Functional Requirements

### 4.1 Performance — NFR-P

| ID | Requirement |
|----|-------------|
| NFR-P-01 | CED processing of a new M1 candle across all timeframes SHALL complete in < 500 ms on a 2020+ Mac |
| NFR-P-02 | Strategy agent evaluation pass (all 5 × 4 = 20 agents) SHALL complete in < 200 ms |
| NFR-P-03 | Segment 1 page load SHALL complete in < 2 seconds |
| NFR-P-04 | Segment 2 auto-refresh SHALL propagate signal state within 15 seconds of publish |
| NFR-P-05 | Gemini narrative call SHALL complete in < 5 seconds or fall back to placeholder |

### 4.2 Reliability — NFR-R

| ID | Requirement |
|----|-------------|
| NFR-R-01 | System SHALL survive OANDA disconnect and resume without data loss (missed candles backfilled) |
| NFR-R-02 | System SHALL survive restart mid-session without duplicating signals (idempotency via (strategy, signature) unique constraint) |
| NFR-R-03 | SQLite SHALL use WAL mode for concurrent read (dashboard) + write (engine) |
| NFR-R-04 | Unhandled exceptions in one strategy agent SHALL NOT crash the engine; errors logged and strategy marked unhealthy |

### 4.3 Cost — NFR-C

| ID | Requirement |
|----|-------------|
| NFR-C-01 | Zero recurring cost. Only TradingView Premium (already owned) is an external paid dependency |
| NFR-C-02 | No service used SHALL require payment if usage grows to 15 trade signals + 5 narratives per day |
| NFR-C-03 | Gemini calls SHALL be constrained to publish events only (not evaluation cycles) to stay within free tier |

### 4.4 Security — NFR-S

| ID | Requirement |
|----|-------------|
| NFR-S-01 | Dashboard SHALL bind to 127.0.0.1 only; no public exposure in Phase 1 |
| NFR-S-02 | All API keys SHALL be read from `.env`; never logged, never committed |
| NFR-S-03 | SQLite DB SHALL be gitignored |

### 4.5 Observability — NFR-O

| ID | Requirement |
|----|-------------|
| NFR-O-01 | System SHALL log to rotating file (`logs/smc.log`, max 10 MB × 5 files) with INFO by default and DEBUG configurable |
| NFR-O-02 | Log lines SHALL include: timestamp (UTC), level, module, event, key=value context |
| NFR-O-03 | Dashboard SHALL expose a `/health` endpoint returning JSON with: OANDA stream status, Finnhub last sync, last candle time per instrument, current open signal count |

### 4.6 Maintainability — NFR-M

| ID | Requirement |
|----|-------------|
| NFR-M-01 | Python ≥ 3.11, type hints on all public functions, `ruff` clean |
| NFR-M-02 | Each strategy SHALL live in its own module with no cross-strategy imports |
| NFR-M-03 | CED primitives SHALL be pure functions operating on candle lists; testable without I/O |
| NFR-M-04 | `pytest` unit tests for: every CED primitive, every strategy detection, clustering, gate logic |
| NFR-M-05 | Fixture candle sets captured from real OANDA data for regression testing |

---

## 5. Data Specification

### 5.1 Candle schema (per timeframe table)
| Column | Type | Notes |
|--------|------|-------|
| instrument | TEXT | e.g. `EUR_USD` |
| t | TIMESTAMP (UTC) | candle start |
| o, h, l, c | REAL | OHLC |
| v | INTEGER | tick volume |
| PRIMARY KEY | (instrument, t) | |

### 5.2 Events
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| t | TIMESTAMP (UTC) | |
| instrument | TEXT | |
| timeframe | TEXT | m1 / m5 / m15 / h1 / h4 / d |
| event_type | TEXT | fvg / ob / breaker / mss / sweep / swing / ... |
| direction | TEXT | bullish / bearish / null |
| payload | JSON | structured event data |

### 5.3 Signals
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| t | TIMESTAMP (UTC) | |
| strategy_id | TEXT | 01_unicorn, 02_judas, 03_confirm, 04_silver_bullet, 06_ifvg |
| verdict | TEXT | VALID / WAIT / NO_TRADE |
| confidence | REAL | 0–100 |
| probability | REAL | 0–100 |
| direction | TEXT | buy / sell / null |
| entry | REAL | |
| sl | REAL | |
| tp1 | REAL | |
| tp2 | REAL | |
| tp3 | REAL | nullable |
| rr | REAL | |
| signature | TEXT | canonical cluster signature |
| gate_result | TEXT | published / vetoed:<reason> |
| payload | JSON | full setup details |

### 5.4 Clusters
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| t | TIMESTAMP (UTC) | |
| signature | TEXT | |
| representative_signal_id | INTEGER FK signals.id | |
| member_signal_ids | JSON | array of IDs |
| boosted_confidence | REAL | |

### 5.5 Trades
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| signal_id | INTEGER FK | |
| cluster_id | INTEGER FK | nullable |
| published_t | TIMESTAMP (UTC) | |
| strategy_id | TEXT | |
| direction | TEXT | |
| entry, sl, tp1, tp2, tp3 | REAL | |
| rr_planned | REAL | |
| narrative | TEXT | Gemini-generated |
| execution_status | TEXT | taken / skipped / null |
| outcome | TEXT | tp1_hit / tp2_hit / sl_hit / manual_close / open |
| outcome_t | TIMESTAMP (UTC) | nullable |
| realized_r | REAL | nullable |
| notes | TEXT | user free text |

### 5.6 Agent scores
| Column | Type | Notes |
|--------|------|-------|
| signal_id | INTEGER FK | |
| agent_id | TEXT | opp1 / opp2 / risk1 / risk2 |
| score | REAL | |
| verdict | TEXT | support / oppose / neutral |
| reasons | JSON | array of strings |
| evidence | JSON | structured pointers |

### 5.7 Strategy stats (materialized, recomputed on outcome update)
| Column | Type |
|--------|------|
| strategy_id | TEXT PK |
| trades_30d | INTEGER |
| wins_30d | INTEGER |
| win_rate_30d | REAL |
| avg_rr_30d | REAL |
| expectancy_30d | REAL |
| trades_alltime | INTEGER |
| last_updated | TIMESTAMP |

### 5.8 Calendar
| Column | Type |
|--------|------|
| id | INTEGER PK |
| t | TIMESTAMP (UTC) |
| currency | TEXT |
| event_name | TEXT |
| impact | TEXT (low/medium/high) |
| actual, forecast, previous | TEXT (raw strings from Finnhub) |

---

## 6. Output Format Contracts

### 6.1 Option A — NO TRADE (internal log only, shown in Segment 2 card + Segment 1 history)
```
Strategy: <name>
Status:   NO TRADE
Confidence: <0–100>
Rejection reasons:
  - <primary>
  - <secondary>
```

### 6.2 Option B — VALID TRADE (published)
```
Strategy:         <name>
Status:           VALID TRADE
Cluster members:  <list, if any>
Direction:        BUY | SELL
Entry:            1.XXXXX
Stop Loss:        1.XXXXX
Take Profit 1:    1.XXXXX
Take Profit 2:    1.XXXXX
Take Profit 3:    1.XXXXX (optional)
Risk-Reward:      1:X.X
Confidence:       XX / 100
Probability:      XX / 100
Timeframes:       entry=<TF>, bias=<TF>
Reasons FOR:      <list>
Reasons AGAINST:  <list>
Final verdict:    <one-liner>
```

### 6.3 Option C — WAIT FOR LEVELS (published)
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
Conditions to meet:  <checklist>
Reasons FOR:         <list>
Reasons AGAINST:     <list>
Final verdict:       <one-liner>
```

---

## 7. Assumptions

1. OANDA demo account registration is available in Maddy's jurisdiction (India).
2. Finnhub free tier remains available with current rate limits.
3. Gemini 2.0 Flash free tier remains available; if rate limits change, fallback to placeholder narrative is acceptable.
4. Mac remains powered on during trading windows (IST 12:30 – 01:30 next day). Signals that occur while Mac is sleeping will be missed — acceptable for Phase 1.
5. EURUSD spread from OANDA demo is representative enough to use as gate filter. Material drift from real-broker spread will be revisited if performance requires.
6. Source documents (`EURUSD SMC best strategies.md`, `SMC_Algorithmic_Trading_Specifications.md`) remain the canonical rule reference; any ambiguity resolved via explicit Maddy decision.
7. Maddy will manually check the dashboard during trading windows (no push notification need in Phase 1).
8. The 4-agent debate is deterministic in Phase 1 (no LLM inside the debate loop).

---

## 8. Dependencies & Pre-requisites

### 8.1 External accounts to provision before Phase 1 build
| Item | Owner | Status |
|------|-------|--------|
| OANDA v20 demo account + API token | Maddy | Pending |
| Finnhub free API key | Maddy | Pending |
| Google AI Studio account + Gemini API key | Maddy | Pending |
| TradingView Premium | Maddy | Already owned |

### 8.2 Local environment
| Item | Requirement |
|------|-------------|
| Python | 3.11+ |
| Mac OS | Current (Darwin 25.x confirmed) |
| Disk | ~500 MB for DB growth over 6 months |
| RAM | Negligible (< 200 MB runtime) |
| Shell | zsh (confirmed) |

---

## 9. Acceptance Criteria (Phase 1 done-done)

Phase 1 is considered COMPLETE when all of the following are demonstrably true:

### 9.1 Functional acceptance
- [ ] OANDA stream + polling running continuously for ≥ 24 hours without data loss
- [ ] Finnhub calendar populates and displays on Segment 2 ticker
- [ ] All CED primitives produce correct outputs on a curated fixture dataset
- [ ] All 5 strategies detect correctly on at least 3 historical reference setups each (visual-confirmed on TradingView)
- [ ] Each strategy's 4 agents produce distinct, defensible opinions on a given setup
- [ ] Clustering correctly merges a fabricated case where Confirmation + Silver Bullet + Unicorn all fire on the same candle (ends up as 1 cluster with Unicorn as representative)
- [ ] Decision gate correctly vetoes: Monday signal, confidence < 75, RR < 2, news-window signal, 3rd daily loss signal
- [ ] Dashboard renders all 3 segments, auto-refreshes, and links correctly between cards and detail pages
- [ ] Gemini narrative generates on at least one published signal and fallback works when API fails
- [ ] Performance monitor correctly computes rolling stats from recorded outcomes
- [ ] `launchd` plist auto-starts engine + dashboard at Mac login

### 9.2 Non-functional acceptance
- [ ] All API keys in `.env`, never committed
- [ ] `ruff` clean, all public functions type-hinted
- [ ] `pytest` suite green (CED primitives, strategies, clustering, gate — ≥ 70% coverage on `app/detector/`, `app/strategies/`, `app/clustering/`, `app/gate/`)
- [ ] `/health` endpoint returns 200 with expected fields
- [ ] Logs rotate correctly; no log contains API key
- [ ] Zero recurring cost incurred during Phase 1 build + 30-day live run

### 9.3 Operational acceptance
- [ ] System runs continuously for 2 weeks (live) with < 5 minutes cumulative downtime
- [ ] At least 10 signals (VALID + WAIT + vetoed) recorded across the 5 strategies
- [ ] Maddy has successfully used Segment 3 to review at least 5 setups and marked outcomes
- [ ] Segment 1 displays meaningful performance data (even if small sample)

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OANDA demo spread differs materially from real broker spread | Gate veto triggers incorrectly | Log both and revisit filter value after 2 weeks of data |
| Gemini free tier removed or rate-limited | No narrative on signals | Fallback template; optional future swap to Ollama local |
| Mac sleeps during trading window | Missed signals | Phase 2 migration to Oracle Cloud VM. Short-term: caffeinate during windows |
| SMT Divergence logic disagrees with Maddy's manual reading | False confluence | Expose raw swing comparison in Segment 3 evidence panel for audit |
| Clustering merges signals that shouldn't merge | Loss of valid independent signals | Log cluster decisions; review first 20 clusters manually; tune signature tolerance |
| Initial thresholds (75/65) kill too many signals | Low signal rate, slow data accumulation | Threshold is configurable via settings modal; tune after first 2 weeks |
| Monday veto suppresses a genuinely strong setup | Missed opportunity | Accepted tradeoff; aligned with source doc |
| One agent's logic bug | Wrong scores silently | Per-agent unit tests + evidence panel surfaces reasoning for manual review |

---

## 11. Glossary

See `SMC_Algorithmic_Trading_Specifications.md` Appendix. Additional terms for Phase 1:

| Term | Meaning |
|------|---------|
| CED | Canonical Event Detector — shared upstream module that computes SMC primitives once per tick |
| Agent Opinion | A 4-tuple output from each sub-agent: score, verdict, reasons, evidence |
| Canonical signature | Tuple used to de-duplicate signals across strategies |
| Representative | The primary strategy chosen to represent a cluster |
| Confluence boost | Confidence premium applied when multiple strategies agree (de-duplicated) |
| Hard veto | A gate rule that rejects a signal regardless of score |
| Taken vs Theoretical | Distinction between trades Maddy actually placed vs those only flagged by the system |

---

## 12. Approval

This specification is a design-time contract for Phase 1. No code will be written until:
- Maddy explicitly approves this document, OR
- Maddy provides corrections to be applied to version 1.1

**On approval**, the next artifact produced will be `.claude/Plan/01-Implementation Plan-Phase1.md` — task breakdown, sequencing, and test approach derived from this spec.
