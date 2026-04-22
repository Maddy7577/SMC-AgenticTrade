# SMC TradeAgents — User Manual

**Version:** Phase 2 · Last updated: April 2026  
**Instrument:** EURUSD (OANDA practice account)  
**Timezone:** All times in IST (Asia/Kolkata, UTC+5:30) unless stated otherwise

---

## Table of Contents

1. [What This Tool Does](#1-what-this-tool-does)
2. [Starting the Engine](#2-starting-the-engine)
3. [Dashboard Overview](#3-dashboard-overview)
4. [Performance Page](#4-performance-page)
5. [Strategies Page](#5-strategies-page)
6. [Signal Detail Page](#6-signal-detail-page)
7. [Recording Trade Outcomes](#7-recording-trade-outcomes)
8. [Strategy Settings Modal](#8-strategy-settings-modal)
9. [The Decision Gate — Why Signals Get Vetoed](#9-the-decision-gate--why-signals-get-vetoed)
10. [Kill Zones](#10-kill-zones)
11. [The 15 Strategies](#11-the-15-strategies)
12. [How Clustering Works](#12-how-clustering-works)
13. [Reading the Agent Debate](#13-reading-the-agent-debate)
14. [Understanding Verdicts and Confidence](#14-understanding-verdicts-and-confidence)
15. [Economic Calendar & News Blackout](#15-economic-calendar--news-blackout)
16. [Performance Metrics Explained](#16-performance-metrics-explained)
17. [Data Management](#17-data-management)
18. [Troubleshooting](#18-troubleshooting)
19. [Quick Reference Card](#19-quick-reference-card)

---

## 1. What This Tool Does

SMC TradeAgents is a **trade intelligence engine** — not an auto-trader. It watches EURUSD price action in real time, runs 15 Smart Money Concepts strategies simultaneously, and presents you with structured trade setups for your review. You decide whether to act.

**What it does:**
- Monitors EURUSD every minute via OANDA
- Runs 15 SMC-based strategies through a 4-agent debate per strategy
- Filters all signals through a 9-rule safety gate
- Groups correlated signals into clusters with a confidence boost
- Generates a Gemini AI narrative explaining each setup in plain English
- Tracks your trade outcomes and computes live performance stats

**What it does not do:**
- Execute trades automatically
- Give financial advice
- Guarantee any outcome

Every signal is labelled **VALID**, **WAIT**, or **NO_TRADE**. Only VALID and WAIT signals that pass the gate appear in your dashboard.

---

## 2. Starting the Engine

### First-time setup

Copy the example environment file and fill in your API keys:
```bash
cp .env.example .env
# Edit .env: add OANDA_API_TOKEN, FINNHUB_API_KEY, GEMINI_API_KEY
```

Seed the database with historical candles (run once, safe to re-run):
```bash
python3 scripts/backfill_history.py
```
This takes 2–4 minutes and pulls 30 days of M1/M5/M15 and 1 year of H1/H4/D candles from OANDA.

### Starting the engine
```bash
python3 -m app.main
```
Then open your browser to: **http://127.0.0.1:8010**

The engine runs three concurrent tasks:
- **CED Pipeline** — reads new candles every minute, runs all detectors, builds a `CanonicalContext` snapshot
- **Strategy Orchestrator** — evaluates all 15 strategies against that snapshot
- **Gate Loop** — filters, clusters, and publishes qualifying signals

The dashboard auto-updates via Server-Sent Events (SSE). You do not need to refresh manually.

### Stopping
`Ctrl+C` in the terminal. All state (daily/monthly counters, active setups, signal history) is persisted to SQLite (`data/smc.db`), so nothing is lost across restarts.

---

## 3. Dashboard Overview

The dashboard has three pages:

| Page | URL | Purpose |
|------|-----|---------|
| Performance | `/` | Trade history, leaderboard, strategy settings |
| Strategies | `/strategies` | Live signal cards for all 15 strategies |
| Signal Detail | `/signal/{id}` | Full breakdown of one signal |

Navigation is via the top bar. A health indicator in the top-right corner shows whether the OANDA stream is connected.

---

## 4. Performance Page (`/`)

This is your home page. It has two sections.

### 4.1 Strategy Leaderboard

A table showing how each strategy is performing over the last 30 days and all-time.

| Column | What It Shows |
|--------|---------------|
| Strategy | Strategy ID and name |
| 30d Trades | Number of trades taken in last 30 days |
| 30d Win Rate | % of those trades that hit TP1 or TP2 (green ≥ 50%, red < 50%) |
| 30d Avg RR | Average realised risk-to-reward ratio over 30 days |
| Expectancy | Average R per trade: (Win% × Avg Win R) − (Loss% × 1). Green ≥ 0, red < 0 |
| All-time | Total trade count since the engine started |
| Status | Active (green) or disabled (red) |

**Flagged rows** appear with an orange background when a strategy has a negative 30-day expectancy AND at least 50 all-time trades — statistically significant underperformance. Consider disabling that strategy via Settings.

### 4.2 Recent Trade History

The last 200 trades, newest first.

| Column | What It Shows |
|--------|---------------|
| Time (IST) | When the signal was published |
| Strategy | Which strategy generated it |
| Direction | BUY (blue) or SELL (red) |
| Entry | Price level to enter at |
| SL | Stop loss level |
| TP1 | First take profit target |
| RR | Planned risk-to-reward ratio |
| Outcome | open / tp1_hit / tp2_hit / sl_hit |
| R Realised | Actual profit/loss in R units (green = profit, red = loss, "—" = not recorded yet) |

Click any price value to copy it to clipboard.

---

## 5. Strategies Page (`/strategies`)

This is your real-time signal dashboard. It shows a card for each of the 15 strategies, updating live.

### 5.1 Calendar Ticker

At the top of the page, a ticker bar shows the next high-impact economic event affecting EUR or USD, with its IST time and impact level. When a news blackout is active (30 minutes before or after a high-impact event), a **BLACKOUT ACTIVE** badge appears and no new signals are published.

### 5.2 Strategy Cards

Each card shows:

- **Strategy name** and last verdict badge (VALID / WAIT / NO_TRADE)
- **Direction** (BUY / SELL) for VALID and WAIT setups
- **Confidence** score (0–100)
- **Entry, SL, TP1** price levels (click to copy)
- **"→ Details"** link to the full signal breakdown
- **Signal dots** — 10 small circles showing the last 10 verdicts for that strategy. Hover any dot to see the verdict and IST timestamp.

If a strategy has no active setup, it shows "Waiting for setup…"

Cards auto-refresh when a new signal arrives. If SSE drops, the page polls every 15 seconds as a fallback.

---

## 6. Signal Detail Page (`/signal/{id}`)

Click "→ Details" on any strategy card to reach the full breakdown for that signal.

### 6.1 Signal Header

Shows the signal ID, strategy name, verdict badge, and the IST timestamp.

### 6.2 Cluster Banner

If this signal was part of a cluster (multiple strategies agreeing on the same setup), a banner shows:

> Cluster: N strategies agree — boosted confidence XX/100

A clustered signal is more reliable — it means 2 or more strategies independently found the same trade at the same price. The confidence score receives a boost: +10 for a 2-strategy cluster, +15 for 3 or more (hard cap of +20).

### 6.3 Trade Plan

| Field | Description |
|-------|-------------|
| Direction | BUY or SELL |
| Entry | Price level to enter the trade |
| Stop Loss | Level at which the thesis is invalidated |
| TP1 | First target — minimum RR 2.0 |
| TP2 | Second target (where available) |
| TP3 | Third target (OTE strategy only) |
| R:R | Risk-to-reward ratio (e.g. "1:2.50") |
| Confidence | Engine's confidence in the setup (0–100) |
| Probability | Estimated win probability, scaled by cluster size |

Click **"Open in TradingView"** to jump directly to the EURUSD M1 chart.

### 6.4 Strategy-Specific Evidence Panels

For Phase 2 strategies, additional context panels appear:

**OTE + FVG (07):**  
Shows the H4 impulse size, Fibonacci levels, the OTE zone (0.618–0.786), and how many pips the M15 FVG overlaps with that zone. Entry is at the 0.705 fib level.

**Rejection Block (08):**  
Shows wick-to-body ratio (must be ≥ 2×), the Fibonacci retracement percentage (must be 80–90%), whether the candle is within 10 pips of an HTF key level, and whether the 50%-body-penetration hard rule passed or failed.

**Market Maker Model (09):**  
Shows the current MMM phase number and name. Only Phase 3 ("Smart Money Reversal") produces signals. Phases 1, 2, and 4 show as NO_TRADE with the phase name displayed for context.

**Power of 3 / AMD (10):**  
Shows the active AMD phase, the Asian session range, and where the manipulation sweep event was detected.

**Vacuum Block (12):**  
Shows the gap type (Weekend / News / Session), the gap price zone, the 50% CE target, and the current fill status (unfilled / partially filled / fully filled). Fully filled = hard veto.

**Reclaimed FVG (13):**  
Shows the FVG zone, how many times price respected the CE (minimum 2 required), the timestamps of each test, and the respected/failed status of each test. A single failure permanently disqualifies the FVG.

**BPR in OB (15):**  
Shows the H4 OB boundary, the overlapping bull/bear FVG zones on M15, and the BPR overlap size (minimum 3 pips required).

### 6.5 Agent Debate Panel

Every signal is produced by 4 agents debating the setup. Each agent card shows a score (0–100), a verdict (SUPPORT / NEUTRAL / OPPOSE), and a list of reasons.

| Agent | Role |
|-------|------|
| OPP1 | Strict rules — checks every mandatory condition. Failure here = NO_TRADE |
| OPP2 | Setup quality — confluences, bonuses, session alignment |
| RISK1 | Technical risk — hard invalidation conditions, structural vetoes |
| RISK2 | Contextual risk — session timing, spread, time-of-day factors |

Click "Evidence" under any agent to see the raw data it used to reach its score.

### 6.6 Gate Result

Shows which gate rule passed or rejected the signal. If rejected, the specific veto reason is displayed (e.g. `vetoed:monday`, `vetoed:spread_2.1_pips`, `vetoed:news_blackout`).

### 6.7 AI Narrative

An 80–150 word Gemini-generated explanation of the setup in plain language — what price did, what the strategy detected, and why the engine issued this verdict. This is generated after the verdict is produced and does not influence it.

---

## 7. Recording Trade Outcomes

At the bottom of every Signal Detail page (for signals with a trade plan), you will find the **Record Outcome** section.

**First, declare whether you took the trade:**
- **"I Took It"** — You entered the trade
- **"I Skipped"** — You saw it but chose not to enter

**Then, once the trade is closed:**
- **"TP1 Hit"** — Price reached your first target
- **"TP2 Hit"** — Price reached your second target
- **"SL Hit"** — Trade was stopped out

These buttons update the database immediately and feed the performance stats on the Performance page. Recording outcomes accurately is what makes the leaderboard meaningful over time.

The current outcome and realised R (calculated automatically from your entry/SL/TP levels) are shown above the buttons once recorded.

---

## 8. Strategy Settings Modal

Click **"Strategy Settings"** on the Performance page to open the settings panel.

### 8.1 Enabling and Disabling Strategies

Toggle the **Enabled** switch for any strategy to turn it on or off. A disabled strategy is fully vetoed at the gate — its signals are computed but never published to the dashboard.

Use this to:
- Disable strategies you don't personally trade (keeps the dashboard focused)
- Turn off a flagged strategy while you review its performance
- Temporarily disable a strategy during unusual market conditions (e.g. high-volatility week)

### 8.2 Per-Strategy Confidence Thresholds

Each strategy defaults to the global thresholds (VALID ≥ 75, WAIT ≥ 65). You can override per strategy using the **Min Confidence** field.

- Enter `80` to require higher conviction for a strategy you want extra certainty on
- Enter `60` to lower the bar for a strategy you want to observe more frequently
- Leave blank to use the global default

### 8.3 Saving

Click **"Save Settings"** — the status message confirms "Saved". Settings persist across engine restarts in the `settings` database table.

---

## 9. The Decision Gate — Why Signals Get Vetoed

Every signal passes through 9 veto checks in order, fastest-to-reject first. The gate stops at the first veto it hits.

| # | Veto Rule | Condition | Threshold |
|---|-----------|-----------|-----------|
| 0 | Strategy disabled | Strategy manually turned off | — |
| 1 | Monday | IST weekday is Monday | — |
| 2 | News blackout | Within 30 minutes of a high-impact EUR/USD event | ±30 min |
| 3 | Daily loss cap | ≥ 2 stop-loss hits today (IST calendar day) | 2 SL hits/day |
| 4 | Monthly trade cap | ≥ 15 VALID signals published this IST month | 15/month |
| 5 | Post-SL cooling | Within 20 minutes of any stop-loss hit | 20 min |
| 6 | Spread too wide | Current live spread exceeds maximum | > 1.5 pips |
| 7 | Confidence floor | Signal confidence below threshold | < 75 (VALID) / < 65 (WAIT) |
| 8 | RR floor | Risk-to-reward below minimum (VALID only) | RR < 2.0 |

**Monday veto:** Smart money typically conducts price discovery on Mondays before establishing directional bias for the week. No signals are published on Mondays.

**Daily loss cap:** After 2 stop-outs in one IST calendar day, the engine stops publishing for the rest of that day. This protects against choppy or invalidated market conditions.

**Monthly cap:** Limits to 15 published VALID signals per IST month. SMC setups should be selective — this ceiling enforces that discipline automatically.

**Post-SL cooling:** After any stop-loss hit, the engine waits 20 minutes before publishing the next signal. This prevents immediately re-entering a market that just invalidated a thesis.

**Counter persistence:** Daily and monthly counters are stored in the `settings` database table and survive engine restarts. Restarting the engine does not reset your daily loss count.

---

## 10. Kill Zones

Kill zones are session windows where institutional order flow is historically concentrated. The engine is fully aware of the current session. Strategies that have session preferences weight their agent scores accordingly — kill zone alignment is a bonus, not a hard requirement (except Silver Bullet, where the window is a hard gate).

| Kill Zone | IST Window | Notes |
|-----------|-----------|-------|
| Asian Session | 5:30 AM – 12:30 PM | Low EURUSD volume; consolidation phase |
| London Kill Zone | 12:30 PM – 3:30 PM | London open; high-probability for London setups |
| Silver Bullet (London) | 1:30 PM – 2:30 PM | Hard requirement for Strategy 04 |
| New York Kill Zone | 5:30 PM – 8:30 PM | Primary high-probability window for EURUSD |
| Silver Bullet (NY AM) | 8:30 PM – 9:30 PM | Hard requirement for Strategy 04 |
| Silver Bullet (NY PM) | 12:30 AM – 1:30 AM | Hard requirement for Strategy 04 |

Kill zone alignment adds bonus points to OPP2 (quality agent) scores. Being outside all windows doesn't prevent a signal — it reduces quality scoring.

---

## 11. The 15 Strategies

### Phase 1 Strategies (Core SMC)

---

**01 — Unicorn Model**

The highest-conviction setup in the engine. An FVG must physically overlap a Breaker Block by at least 10% of the FVG's range. The overlap creates a Confluence Equilibrium (CE) zone — entry is at its midpoint. Requires HTF bias (non-neutral), a prior sweep, and a confirmed MSS before entry.

SL: beyond the Breaker Block extreme + max(10 pips, 0.5×ATR).  
Best window: NY AM Silver Bullet (IST 8:30–9:30 PM).  
Cluster family: Confirmation (highest priority — always the representative).

---

**02 — Judas Swing**

Identifies the false break of the Asian session range (IST 5:30–12:30 AM) engineered to hunt retail stops before the real directional move. A bearish day's high gets swept (not the low); a bullish day's low gets swept. Entry on the first FVG or OB after the reversal MSS.

SL: beyond the sweep wick + 15 pips.  
TP1: opposite side of Asian range. TP2: prior day high/low.  
Hard requirement: London Kill Zone must be active.  
Cluster family: Judas (always the representative).

---

**03 — Confirmation Model**

Five-condition setup — all five must be present simultaneously:
1. Liquidity sweep
2. MSS after the sweep
3. FVG in the displacement move
4. HTF bias non-neutral
5. Price inside the aligned Premium or Discount zone

All five = 90% base confidence. Each missing condition proportionally reduces confidence. SL = sweep wick extreme ± 0.75×ATR. TP1 = 2×risk; TP2 = opposing H4 liquidity pool.  
Cluster family: Confirmation (lowest priority in family).

---

**04 — Silver Bullet**

ICT Silver Bullet: time-window constrained, with both the setup formation AND the entry tick required inside one of three one-hour windows. Outside the window = hard NO_TRADE regardless of confluence quality.

Windows (IST): 1:30–2:30 PM (London), 8:30–9:30 PM (NY AM), 12:30–1:30 AM (NY PM).  
Entry must be ≥15 pips from the nearest opposing level.  
Cluster family: Confirmation (second priority after Unicorn).

---

**05 — Nested FVG Stack**

A displacement leg of ≥5 consecutive same-direction M15 candles containing ≥3 FVGs. The first FVG is the breakaway gap; remaining FVGs are measuring/runaway gaps. Hard rule: if the breakaway gap is subsequently fully filled (candle body closes through it), the thesis is immediately and permanently invalidated — the strategy returns NO_TRADE.

Entry: CE of the last FVG in the stack.  
SL: beyond the entry FVG extreme ± 5 pips (trails dynamically).  
Never clusters (independent root).

---

**06 — Inverse FVG (iFVG)**

An FVG where a subsequent candle's *body* (not just wick) closes completely through the entire gap range, inverting its polarity. The inverted zone becomes a high-probability entry area from the opposite direction. Prior sweep required. SMT divergence (EURUSD vs GBPUSD) is strongly weighted as confluence.

Entry: iFVG midpoint.  
SL: wider of (iFVG zone ± 10 pips) or (beyond the sweep wick).  
Best session: NY onward (IST 5:30 PM+).  
Never clusters (independent root).

---

### Phase 2 Strategies (Advanced SMC)

---

**07 — OTE + FVG Confluence**

A qualifying H4 impulse (minimum 3×ATR) generates Fibonacci retracement levels. A M15 FVG must physically overlap the Optimal Trade Entry band (0.618–0.786 retracement). If the FVG exists but doesn't overlap the OTE zone, a hard veto fires.

Entry: 0.705 fib.  
SL: 100% retracement ± 15 pips.  
TP1: 0.0 (swing origin), TP2: −0.27 extension, TP3: −0.62 extension.  
An order block within the OTE zone adds confluence.  
Never clusters (independent root).

---

**08 — Rejection Block**

A long-wick rejection candle at an HTF key level (PDH/PDL, swing extreme, or OB boundary). Requirements: wick ≥ 2× candle body, Fibonacci retracement of 80–90%, within 10 pips of the key level, MSS/CHoCH confirmed.

Hard rule: if any subsequent candle closes through more than 50% of the rejection wick, `strict_rules_met` is set permanently False and the signal becomes NO_TRADE — the rejection has been negated.

Target: RR ≥ 3.0.  
SL: 10 pips beyond wick extreme.  
Never clusters (independent root).

---

**09 — Market Maker Model (MMM)**

Tracks the four-phase Market Maker cycle on H4/Daily candles:

| Phase | Name | Engine Action |
|-------|------|---------------|
| 1 | Consolidation | NO_TRADE |
| 2 | Sell Program | NO_TRADE |
| 3 | Smart Money Reversal | Signal generated if MSS + FVG present |
| 4 | Buy Program | NO_TRADE |

Only Phase 3 produces signals. Phases 1, 2, and 4 cause opposition agents to score 0, guaranteeing NO_TRADE.  
Cluster family: Confirmation.

---

**10 — Power of 3 / AMD Intraday**

Tracks the intraday AMD (Accumulation–Manipulation–Distribution) cycle:

| Phase | IST Window | Engine Action |
|-------|-----------|---------------|
| Accumulation | 5:30 AM – 12:30 PM | NO_TRADE |
| Manipulation | 12:30 PM – 3:30 PM | Maximum WAIT — detects false Asian range breakout |
| Distribution | 3:30 PM – 9:30 PM | VALID possible — entry after reversal MSS |

The manipulation event is detected when price breaks the Asian range *against* the HTF daily bias — the engineered false breakout. Entry is after the reversal MSS post-manipulation.

Cluster family: Judas. When both Judas Swing (02) and Power of 3 (10) fire in the same cluster, Judas is always the representative.

---

**11 — Propulsion Block**

An Order Block with a propulsion candle (body/range ratio ≥ 0.6 — strong, full candle showing institutional conviction) inside it. A new FVG must form in the three candles immediately after the propulsion candle. The OB must not be retouched after the propulsion — any subsequent touch invalidates the setup.

H1 accumulated liquidity (swing level touched ≥2 times in 50 candles) provides additional context.

Entry: OB midpoint on retest.  
SL: beyond OB extreme ± 10 pips.  
Never clusters (independent root).

---

**12 — Vacuum Block**

Trades into an open price gap on H1 candles. A gap forms when `current_candle.low > previous_candle.high` (bullish gap) or `current_candle.high < previous_candle.low` (bearish gap). Fill is defined strictly: a candle *body* closing inside the gap counts as filled.

Hard rule: a fully filled gap = `strict_rules_met` False → NO_TRADE.

Gap types (highest confidence first): Weekend gap > News gap > Session gap.  
Entry: gap CE (50% midpoint).  
SL: 5 pips beyond the gap boundary.  
Requires LTF MSS within 10 pips of the CE.  
Never clusters (independent root).

---

**13 — Reclaimed FVG**

An FVG that has been entered (price touched the zone) at least twice and the CE was respected on every visit (candle closed back above/below the midpoint). A single CE failure — where price closes beyond the midpoint — permanently disqualifies this FVG for this strategy.

Scoring:
- 2 respected tests = base confidence
- 3+ respected tests = +10 bonus
- FVG gap size ≤ 1 pip = "perfect FVG" bonus

Entry: FVG CE.  
SL: FVG extreme ± 5 pips.  
Never clusters (independent root).

---

**14 — CISD (Change in State of Delivery)**

Detects a bearish delivery sequence (≥3 consecutive bearish M5 candles) followed by a CISD candle that closes above the open of the first candle in the sequence — breaking the state of delivery. Must occur within 15 pips of an HTF key level. Prior sweep required.

By design, OPP1 is capped at a maximum score of 65, which prevents CISD from ever reaching VALID on its own. It must cluster with another Confirmation family strategy to receive the confluence boost needed to cross the VALID threshold.

Cluster family: Confirmation (lowest priority — never the representative).

---

**15 — BPR in Order Block**

An H4 Order Block that contains both a bullish M15 FVG and a bearish M15 FVG overlapping each other by ≥3 pips inside the OB. This overlap is the Balanced Price Range (BPR) — a zone where both buy-side and sell-side imbalances coexist, indicating high institutional interest.

Entry: BPR midpoint.  
SL: beyond the full OB extreme ± 10 pips.  
HTF bias must align with OB direction. LTF MSS required.  
Never clusters with any strategy (always an independent root).

---

## 12. How Clustering Works

When two or more strategies detect the same setup at the same price level within five minutes, the engine merges them into a **cluster** rather than publishing separate alerts. A cluster is a stronger signal — multiple independent frameworks agree.

### Matching Logic

Two signals are considered the same setup if all of the following match:
- Same direction (buy/sell)
- Same sweep level (rounded to 5-pip buckets)
- Same MSS level (rounded to 5-pip buckets)
- Same entry midpoint (rounded to 5-pip buckets)
- Within the same 5-minute time bucket

### Strategy Families and Clustering Rules

**Confirmation Family** — members can cluster only with each other:

| Priority | Strategy |
|----------|----------|
| 1 (representative) | 01 Unicorn |
| 2 | 04 Silver Bullet |
| 3 | 09 MMM |
| 4 | 14 CISD |
| 5 | 03 Confirmation |

The highest-priority strategy that fires becomes the cluster representative (its signal is what you see in the dashboard).

**Judas Family** — cluster only with each other:

| Priority | Strategy |
|----------|----------|
| 1 (representative) | 02 Judas Swing |
| 2 | 10 Power of 3 |

**Independent Roots** — never cluster with anything:
05, 06, 07, 08, 11, 12, 13, 15

### Confidence Boost

| Cluster Size | Boost |
|-------------|-------|
| 1 strategy | +0 |
| 2 strategies | +10 |
| 3+ strategies | +15 |
| Hard cap | +20 |

---

## 13. Reading the Agent Debate

Every strategy uses a 4-agent debate to reach its verdict. The four agents argue from different perspectives; their scores are combined into the final confidence.

### The Four Agents

**OPP1 — Strict Rules (weight: 1.5×)**  
Checks every mandatory condition for the strategy. This is the binary gatekeeper. If OPP1 fails a hard condition, `strict_rules_met` is False and the signal cannot reach VALID regardless of other agents.

**OPP2 — Setup Quality (weight: 1.0×)**  
Assesses quality beyond strict rules: confluence count, kill zone alignment, structure clarity, bonus conditions. A high OPP2 score means a premium-quality setup.

**RISK1 — Technical Risk (weight: 1.2×)**  
Checks hard invalidation conditions embedded in the strategy — e.g. the 50%-body-penetration check in Rejection Block, the breakaway gap fill in Nested FVG. A high RISK1 score is a serious warning.

**RISK2 — Contextual Risk (weight: 0.8×)**  
Checks soft contextual risks: spread, session timing, time-of-day factors, conflicting signals. Lower weight — contextual concerns are softer than technical ones.

### How Confidence Is Calculated

The debate produces two weighted components:

```
opportunity_score = (OPP1 × 1.5 + OPP2 × 1.0) / 2.5
risk_score        = (RISK1 × 1.2 + RISK2 × 0.8) / 2.0

confidence = opportunity_score − risk_score   → mapped to 0–100
```

High OPP scores minus low RISK scores = high confidence.

### Hard Veto

If either risk agent scores ≥ 70 and returns a verdict of "oppose", the signal is immediately set to NO_TRADE regardless of confidence or strict_rules_met. This is a hard veto — no weighted average can override it.

### Green Flags

- OPP1 ≥ 75 with checkmarks across all mandatory conditions
- OPP2 ≥ 70 with kill zone and confluence bonuses
- RISK1 ≤ 30 (no hard vetoes)
- RISK2 ≤ 30 (tight spread, active session)

### Red Flags

- OPP1 showing "hard veto" or "no sweep", "no MSS/CHoCH"
- RISK1 ≥ 70 (technical invalidation)
- Any agent returning "OPPOSE" verdict

---

## 14. Understanding Verdicts and Confidence

### Verdict Definitions

| Verdict | Meaning | Confidence Required | Additional Requirements |
|---------|---------|---------------------|------------------------|
| **VALID** | Full setup — trade when price reaches entry | ≥ 75 | strict_rules_met, RR ≥ 2.0, price near entry, no hard veto |
| **WAIT** | Setup forming — watch but don't enter yet | ≥ 65 | strict_rules_met, no hard veto |
| **NO_TRADE** | Conditions not met or hard veto fired | Any | — |

### What "Price at Entry" Means for VALID

The engine checks that the current price is within the trade's risk range of the entry level (within 50% of the entry-to-SL distance). This prevents flagging setups that have already moved past the entry. A setup that was VALID may downgrade to WAIT if price moves away.

### Confidence Guidance

| Confidence | Interpretation |
|-----------|---------------|
| 90–100 | Premium setup — all agents aligned, strong confluence |
| 80–89 | High-quality setup — most conditions met cleanly |
| 75–79 | Valid but marginal — review agent debate carefully before acting |
| 65–74 | WAIT — setup forming, not ready to enter |
| < 65 | NO_TRADE |

### Probability vs Confidence

- **Confidence (0–100):** weighted score across the 4 agents
- **Probability (%):** estimated win probability, scaled further by cluster size — a 2-strategy cluster multiplies by 1.10×, a 3+ cluster by 1.15×

---

## 15. Economic Calendar & News Blackout

The engine connects to Finnhub to fetch upcoming high-impact EUR and USD economic events. The calendar refreshes every 15 minutes.

### Blackout Window

**30 minutes before and 30 minutes after** any high-impact event, the gate rejects all signals with `vetoed:news_blackout`. This window cannot be overridden by strategy settings.

The Strategies page shows the next upcoming event in the calendar ticker. When a blackout is active, a badge appears at the top of the page.

### What Counts as High-Impact

Finnhub flags events by impact level. The engine monitors events labelled high-impact for EUR or USD, including: Non-Farm Payrolls, CPI, FOMC decisions, ECB rate decisions, GDP releases, unemployment reports.

---

## 16. Performance Metrics Explained

### Expectancy

```
Expectancy = (Win Rate × Avg Win R) − ((1 − Win Rate) × 1)
```

Expectancy tells you how much you expect to earn per trade in R units. An expectancy of +0.5 means each trade earns +0.5R on average over a large sample. Negative expectancy over 50+ trades is a statistically meaningful signal to disable the strategy.

### Realised R

Each trade outcome is automatically converted to R units:

| Outcome | Realised R |
|---------|-----------|
| TP1 hit | (TP1 − Entry) / (Entry − SL) for buys |
| TP2 hit | (TP2 − Entry) / (Entry − SL) for buys |
| SL hit | −1.0 always |

You must record the outcome on the Signal Detail page. Trades with no outcome recorded show "—" in the R column and are excluded from expectancy calculations.

### 30-Day vs All-Time

The leaderboard shows both 30-day rolling stats (current strategy health) and all-time trade counts (statistical significance). A strategy with 5 trades in 30 days at 100% win rate is not meaningful. Look for ≥ 20 trades before drawing conclusions.

---

## 17. Data Management

### Database Location

All data lives in `data/smc.db` — a single SQLite file. In normal operation (with the event deduplication fixes applied), this should stay under 500 MB even after months of running.

### Automatic Event Pruning

On every startup, the engine automatically deletes events older than 90 days from the `events` table. This runs silently in the background and is logged as `pruned old events: N rows deleted`. A daily scheduled prune also runs at 02:00 UTC.

The `events` table stores raw detector outputs (FVGs, sweeps, MSS, gaps, etc.). This is the table that can grow large — historical signals, trades, and performance data are in separate tables and are kept indefinitely.

### Manual Cleanup

If the database grows unexpectedly large, you can check its size and table counts:

```bash
ls -lh data/smc.db
```

To reclaim disk space after large deletes (compacts the file on disk):
```bash
sqlite3 data/smc.db "VACUUM;"
```

This may take a few minutes on a large file.

### Full Reset

To start completely fresh (deletes all signals, trades, and history):

```bash
rm data/smc.db
python3 scripts/backfill_history.py   # rebuilds candles only
python3 -m app.main                    # bootstraps schema, starts engine
```

---

## 18. Troubleshooting

### Dashboard not updating

The SSE connection may have dropped. The page polls every 15 seconds as a fallback, so updates resume automatically. If the health indicator shows disconnected, check the engine terminal for OANDA stream errors.

### Modal won't close

Hard-refresh the page with `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows/Linux).

### "No high-impact events in next 7 days"

Either the Finnhub calendar hasn't refreshed yet (wait up to 15 minutes) or there genuinely are no events scheduled. This is normal on quiet weeks.

### Missing candles or gaps in history

Re-run backfill — it is fully idempotent and won't duplicate data:
```bash
python3 scripts/backfill_history.py
```

### Replay a past day for debugging

Feed any past date through all 15 strategies for testing or regression:
```bash
python3 scripts/replay_day.py 2026-04-17
```
The date must have M1 data in the database. Results are printed to console.

### Engine crashes mid-run

Check the console output or `logs/smc.log`. Strategy failures are isolated — one broken strategy never kills the engine; it logs the error and continues to the next strategy. If the CED pipeline crashes, restart the engine.

### Database grows very large

This was a known bug that has been fixed. If you're on an older version, see [Data Management](#17-data-management) for the cleanup steps. With the current version, normal growth is ~1–5 MB per day.

### Counter resets after restart

It shouldn't — counters live in the `settings` KV table. If it does, check that `data/smc.db` exists and wasn't deleted. A missing DB file causes the engine to bootstrap a fresh schema with zero counters.

---

## 19. Quick Reference Card

### Dashboard URLs

| Page | URL |
|------|-----|
| Performance | http://127.0.0.1:8010/ |
| Strategies | http://127.0.0.1:8010/strategies |
| Signal detail | http://127.0.0.1:8010/signal/{id} |

### Gate Thresholds

| Rule | Value |
|------|-------|
| VALID confidence minimum | 75 |
| WAIT confidence minimum | 65 |
| Minimum RR for VALID | 2.0 |
| Max spread | 1.5 pips |
| Max daily SL hits | 2 |
| Monthly VALID cap | 15 |
| Post-SL cooldown | 20 minutes |
| News blackout window | ±30 minutes |

### Cluster Boosts

| Strategies agreeing | Confidence boost |
|--------------------|-----------------|
| 2 | +10 |
| 3+ | +15 |
| Hard cap | +20 |

### Kill Zone Windows (IST)

| Session | Window |
|---------|--------|
| Asian | 5:30 AM – 12:30 PM |
| London KZ | 12:30 PM – 3:30 PM |
| Silver Bullet (London) | 1:30 PM – 2:30 PM |
| NY KZ | 5:30 PM – 8:30 PM |
| Silver Bullet (NY AM) | 8:30 PM – 9:30 PM |
| Silver Bullet (NY PM) | 12:30 AM – 1:30 AM |

### Strategy Families

| Family | Members | Representative |
|--------|---------|---------------|
| Confirmation | 01, 04, 09, 14, 03 | 01 Unicorn (highest priority) |
| Judas | 02, 10 | 02 Judas (always representative) |
| Independent | 05, 06, 07, 08, 11, 12, 13, 15 | Never clusters |

### Agent Weights

| Agent | Weight | Role |
|-------|--------|------|
| OPP1 | 1.5× | Strict rules |
| RISK1 | 1.2× | Technical risk |
| OPP2 | 1.0× | Setup quality |
| RISK2 | 0.8× | Contextual risk |

### Commands

```bash
# Start engine
python3 -m app.main

# Seed historical candles
python3 scripts/backfill_history.py

# Replay a past day (debug)
python3 scripts/replay_day.py 2026-04-17

# Run all tests
python3 -m pytest tests/

# Run tests with coverage
python3 -m pytest tests/ --cov=app/detector --cov=app/strategies --cov=app/clustering --cov=app/gate

# Lint
python3 -m ruff check .

# Compact database (after large deletes)
sqlite3 data/smc.db "VACUUM;"
```
