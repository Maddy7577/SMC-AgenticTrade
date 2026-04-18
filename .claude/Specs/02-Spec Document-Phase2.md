# Phase 2 — Specification Document

**Project:** SMC-TradeAgents
**Phase:** 2 (Full Strategy Expansion)
**Version:** 1.0
**Date:** 2026-04-17
**Status:** Draft — awaiting approval

**Author:** Architecture designer
**Parent documents:**
- Architecture: `.claude/Documents/system_architecture.md` (v1.1)
- Phase 1 spec: `.claude/Specs/01-Spec Document-Phase1.md` (v1.0, locked)

---

## 1. Purpose & Scope

### 1.1 Purpose
Expand the Phase 1 engine to include all 10 remaining SMC strategies (#5, #7, #8, #9, #10, #11, #12, #13, #14, #15), bringing the total to 15 strategies and completing the full strategy set defined in the system architecture. No infrastructure changes are required to the CED, gate, clustering, dashboard framework, or data layer — the Phase 1 foundation is extended, not replaced.

### 1.2 In-scope for Phase 2

| Area | Inclusion |
|------|-----------|
| New CED detector modules | Fibonacci calculator, FVG CE-test tracker, long-wick classifier, gap detector, AMD phase tracker, MMM consolidation detector |
| Strategies (10) | #5 Nested FVGs, #7 OTE+FVG, #8 Rejection Block, #9 Market Maker Model, #10 Power of 3, #11 Propulsion Block, #12 Vacuum Block, #13 Reclaimed FVG, #14 CISD, #15 BPR in OB |
| Agent framework | 4 agents per strategy — same 2-Opp + 2-Risk structure as Phase 1 |
| Clustering ancestry update | Expand ancestry tree to include all 15 strategies |
| Dashboard scaling | Segment 2 grows from 5 to 15 cards; settings modal lists all 15 strategies |
| Testing | Unit tests for new CED primitives and all 10 strategies; updated gate/clustering tests |
| Oracle Cloud migration (optional) | Migrate from Mac launchd to Oracle Cloud Always Free VM for 24/7 uptime |

### 1.3 Out-of-scope for Phase 2

| Area | Reason |
|------|--------|
| Telegram / email / push alerts | Dashboard remains sole output surface; deferred to user decision post-Phase 2 |
| Backtesting engine with equity reports | Replay harness from Phase 1 sufficient; formal backtest is a separate project |
| Additional instruments beyond EURUSD | GBPUSD retained for SMT Divergence only |
| Auto-execution | Not a goal of this project |
| New gate veto rules | Existing 9 vetoes sufficient; tuning thresholds is a config change, not a spec change |
| Pine Script alert inbound webhook | Optional; not needed for Phase 2 signal production |

---

## 2. User Stories

### 2.1 Existing stories inherited
All user stories from Phase 1 (US-01 through US-10) remain in effect with the same acceptance criteria, now applying to all 15 strategies.

### 2.2 New stories for Phase 2

**US-11: Full 15-strategy board**
> As Maddy, I want all 15 strategies visible in Segment 2, so I can assess the complete SMC picture without toggling pages.
> **Acceptance:** Segment 2 shows 15 strategy cards in a responsive grid (3–5 per row desktop, 1 mobile). Performance on 15 cards is not visibly worse than 5.

**US-12: HTF framework awareness**
> As Maddy, when a Market Maker Model (Phase 3–4) or Power of 3 (Distribution phase) setup is forming, I want to know which cycle phase we're in before deciding to enter.
> **Acceptance:** Segment 3 evidence panel shows current MMM phase (1/2/3/4) and PO3 cycle state (Accumulation/Manipulation/Distribution) for signals from those strategies.

**US-13: Fibonacci precision**
> As Maddy, when an OTE+FVG setup fires, I want to see the exact Fibonacci level the FVG overlaps with (0.618, 0.705, 0.786), so I can verify it on TradingView before entering.
> **Acceptance:** Segment 3 evidence panel for OTE+FVG shows impulse swing H/L, all key fib levels, and OTE band boundaries.

**US-14: Rejection block quality flag**
> As Maddy, I want to know if a Rejection Block passes the 50%-body-penetration validation rule before the setup is presented as valid.
> **Acceptance:** Rejection Block signals include the body-penetration check result in Segment 3 evidence panel; setup that fails this rule produces NO TRADE not VALID.

**US-15: Reclaimed FVG test count**
> As Maddy, for a Reclaimed FVG setup, I want to see how many times the CE has been tested and respected, so I can judge the strength of the zone.
> **Acceptance:** Segment 3 evidence panel shows CE test count (≥2 required for signal) and timestamps of each test.

**US-16: Gap trade awareness**
> As Maddy, when a Vacuum Block setup forms at a weekend or session gap, I want to know the gap type and 50% level before entry.
> **Acceptance:** Segment 3 evidence panel for Vacuum Block shows gap type (weekend/session/news), gap zone top/bottom, and 50% CE level.

---

## 3. Functional Requirements

### 3.1 New CED detector modules — FR-C2

| ID | Requirement |
|----|-------------|
| FR-C2-01 | `fibonacci.py` SHALL compute fib retracement levels (0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0) and extensions (−0.27, −0.62) from a given impulse swing using **body-to-body** (not wick-to-wick) measurement |
| FR-C2-02 | `fibonacci.py` SHALL accept an impulse leg dict (swing_high, swing_low, direction) and return a keyed dict of price levels |
| FR-C2-03 | `fvg.py` FVG state SHALL be enriched to track **CE test history**: each time price touches the FVG zone, record whether the candle closed beyond the CE (failed) or respected it (held); exposed as `tests: List[{t, respected: bool}]` |
| FR-C2-04 | A new helper `long_wick_classifier.py` SHALL identify candles where wick is ≥ 2× body AND wick is ≥ 2× the opposing wick; returns type (`bullish_rejection`, `bearish_rejection`) and wick/body ratio |
| FR-C2-05 | A new `gap_detector.py` SHALL find price gaps between consecutive H1 candles where `curr.low > prev.high` (gap up) or `curr.high < prev.low` (gap down); classify each as `weekend_gap`, `session_gap`, or `news_gap` based on the time delta between candles |
| FR-C2-06 | A new `amd_phase.py` module SHALL determine the current Power of 3 cycle phase (Accumulation/Manipulation/Distribution/Unknown) based on the current UTC time relative to Asian range, London open, and NY open boundaries |
| FR-C2-07 | A new `mmm_phase.py` module SHALL identify the current Market Maker Model phase (1=Consolidation, 2=Sell Program, 3=Smart Money Reversal, 4=Buy Program or inverse) from H4/Daily candles using consolidation range detection and phase sequencing logic |
| FR-C2-08 | All new detector functions SHALL be pure functions over candle lists with no DB access or side effects, consistent with the CED design contract |
| FR-C2-09 | `CanonicalContext` SHALL be extended with the following typed fields: `fib_levels: Dict[float, float]` (key = fib level e.g. 0.618, value = price); `active_gaps: List[Dict]` each entry `{gap_type: str, top: float, bottom: float, ce: float, filled_pct: float}`; `amd_phase: str` one of `Accumulation \| Manipulation \| Distribution \| Unknown`; `mmm_phase: int` one of `1 \| 2 \| 3 \| 4`; `fvg_test_history: Dict[int, List[Dict]]` keyed by FVG event ID, each entry `{t: str, respected: bool, close_price: float}` |
| FR-C2-10 | New CED outputs SHALL be persisted to `events` table with appropriate `event_type` tags: `fibonacci_impulse`, `gap_formed`, `gap_filled`, `fvg_ce_test`, `mmm_phase_change`, `amd_manipulation_detected` |

### 3.2 Strategies and agents — FR-S2

| ID | Requirement |
|----|-------------|
| FR-S2-01 | System SHALL implement 10 strategies in Phase 2: #5 Nested FVGs, #7 OTE+FVG, #8 Rejection Block, #9 Market Maker Model, #10 Power of 3, #11 Propulsion Block, #12 Vacuum Block, #13 Reclaimed FVG, #14 CISD, #15 BPR in OB |
| FR-S2-02 | Each strategy SHALL have exactly 4 agents following the same Opp1/Opp2/Risk1/Risk2 structure as Phase 1 |
| FR-S2-03 | Each strategy SHALL produce one verdict per evaluation cycle: VALID TRADE, WAIT FOR LEVELS, or NO TRADE, with the same threshold logic (VALID ≥ 75, WAIT ≥ 65) |
| FR-S2-04 | All verdicts SHALL be persisted to `signals` table with per-agent scores in `agent_scores` table, using strategy IDs `05_nested_fvg`, `07_ote_fvg`, `08_rejection_block`, `09_mmm`, `10_po3`, `11_propulsion`, `12_vacuum`, `13_reclaimed_fvg`, `14_cisd`, `15_bpr_ob` |
| FR-S2-05 | Phase 2 strategies SHALL be added to `ALL_STRATEGIES` in `app/strategies/orchestrator.py` and run in the same parallel evaluation loop as Phase 1 strategies |

### 3.3 Strategy-specific behavior — FR-SP2

#### Strategy #5 — Nested FVGs (FVG Stacking)

| ID | Requirement |
|----|-------------|
| FR-SP2-05-01 | SHALL detect a displacement leg of ≥ 5 consecutive same-direction candles with ≥ 3 FVGs formed within it |
| FR-SP2-05-02 | SHALL classify the first FVG as `breakaway_gap` and subsequent FVGs as `measuring_gap` |
| FR-SP2-05-03 | Setup is INVALIDATED immediately when the breakaway gap (first FVG) is fully filled |
| FR-SP2-05-04 | Entry at CE (50%) of most recent (last) FVG in the stack — NOT at OTE (0.618–0.786) |
| FR-SP2-05-05 | SL below the bottom of the entry FVG (bullish) or above the top of the entry FVG (bearish) + 5-pip buffer; trail behind each subsequent FVG as price advances — move SL to behind each new FVG bottom/top as price advances |
| FR-SP2-05-06 | SHALL require HTF bias alignment; London or NY Kill Zone active; Asian stacks (outside Kill Zone) score significantly lower |
| FR-SP2-05-07 | Multi-timeframe alignment: the entire M15 FVG zone (both top and bottom boundaries) must be contained within the H4 FVG zone to qualify as a strongly-weighted confluence factor in Opp2; partial overlap alone does not qualify |

#### Strategy #7 — OTE + FVG Confluence

| ID | Requirement |
|----|-------------|
| FR-SP2-07-01 | SHALL identify an impulse leg of ≥ 3× ATR on H4; calculate Fibonacci body-to-body using `fibonacci.py` |
| FR-SP2-07-02 | SHALL require an FVG that physically overlaps (not just touches) the OTE band (0.618–0.786) on M15; proximity without overlap = NO TRADE |
| FR-SP2-07-03 | SHALL require a prior liquidity sweep before the impulse leg began |
| FR-SP2-07-04 | Optimal entry point is 0.705 Fibonacci level; entry zone is the FVG boundary |
| FR-SP2-07-05 | SL SHALL be placed beyond the swing extreme (100% Fibonacci level) + 15-pip buffer |
| FR-SP2-07-06 | TP1 = previous swing extreme (0% level); TP2 = −0.27 extension; TP3 = −0.62 extension |
| FR-SP2-07-07 | Preferred session: NY Kill Zone 8:30–11:00 AM EST (IST 18:00–20:30) |
| FR-SP2-07-08 | Order Block overlap within OTE zone SHALL be flagged as additional confluence (Opp2 bonus) |

#### Strategy #8 — Rejection Block at Last-Defense Levels

| ID | Requirement |
|----|-------------|
| FR-SP2-08-01 | SHALL use `long_wick_classifier.py` to identify rejection candles with wick ≥ 2× body |
| FR-SP2-08-02 | SHALL require Fibonacci retracement of 80–90% (deep retracement zone) — standard OTE does NOT qualify |
| FR-SP2-08-03 | SHALL require rejection at a genuine HTF key level (PDH/PDL, swing H/L, equal H/L) |
| FR-SP2-08-04 | SHALL require MSS/CHoCH confirmation on M15 or M5 |
| FR-SP2-08-05 | **50%-body-penetration rule**: if a subsequent closing candle penetrates >50% of the rejection candle body, setup FAILS → NO TRADE regardless of other scores |
| FR-SP2-08-06 | HTF (H1–Daily) requires 1 rejection wick; LTF (M15 and below) requires ≥ 2 rejection wicks for setup to qualify |
| FR-SP2-08-07 | Entry trigger: price returns to the body of the rejection candle; Bullish = below body low; Bearish = above body high |
| FR-SP2-08-08 | SL: 10 pips beyond the rejection wick extreme (tightest stop of all PD arrays) |
| FR-SP2-08-09 | TP: opposing liquidity pool; target RR ≥ 3.0 given tight stops |

#### Strategy #9 — ICT Market Maker Model (MMM)

| ID | Requirement |
|----|-------------|
| FR-SP2-09-01 | SHALL use `mmm_phase.py` to determine the current market maker phase (1–4) from H4/Daily candles |
| FR-SP2-09-02 | Setup is ONLY active during Phase 3 (Smart Money Reversal); Phases 1, 2, 4 are observation-only (NO TRADE) |
| FR-SP2-09-03 | SHALL identify original consolidation zone: range with ≥ 3 boundary touches each on high and low over a 50-candle Daily lookback |
| FR-SP2-09-04 | SHALL confirm engineered liquidity above (BSL) or below (SSL) the consolidation zone |
| FR-SP2-09-05 | Phase 3 entry requires MSS at HTF Discount/Premium PD Array + FVG formation after MSS |
| FR-SP2-09-06 | Entry at FVG retracement after Phase 3 MSS |
| FR-SP2-09-07 | SL: 20 pips beyond the swing extreme that triggered the Phase 3 MSS — the swing low for a bullish MMBM entry, the swing high for a bearish MMSM entry |
| FR-SP2-09-08 | TP1 = consolidation low/high; TP2 = consolidation opposite boundary; TP3 = engineered liquidity target (full model completion) |
| FR-SP2-09-09 | Current phase SHALL be shown in Segment 3 evidence panel for all MMM signals (even NO TRADE) |

#### Strategy #10 — Power of 3 / AMD Intraday Cycle

| ID | Requirement |
|----|-------------|
| FR-SP2-10-01 | SHALL use `amd_phase.py` to identify current cycle phase (Accumulation/Manipulation/Distribution) |
| FR-SP2-10-02 | Setup SHALL only produce VALID or WAIT verdicts during Distribution phase (NY session); Manipulation phase produces WAIT at most |
| FR-SP2-10-03 | SHALL mark Asian session range (IST 05:30–12:30) from M5 candles |
| FR-SP2-10-04 | SHALL detect manipulation: false breakout of Asian range against daily bias during London KZ (IST 12:30–15:30) |
| FR-SP2-10-05 | SHALL require MSS/CHoCH reversal after manipulation to confirm Distribution phase entry |
| FR-SP2-10-06 | Entry: FVG or OB from displacement candle after MSS |
| FR-SP2-10-07 | SL: beyond manipulation extreme wick + 10-pip buffer |
| FR-SP2-10-08 | TP1 = Asian session opposite boundary; TP2 = PDH/PDL |
| FR-SP2-10-09 | Clustering: PO3 shares the Judas Swing ancestry root (both trade same manipulation event); PO3 and Judas SHALL merge in the same cluster when matching signature; Judas parent takes representative position |

#### Strategy #11 — Propulsion Block

| ID | Requirement |
|----|-------------|
| FR-SP2-11-01 | SHALL require an activated Order Block (price has returned to the OB zone) from the existing CED OB detector |
| FR-SP2-11-02 | SHALL identify a "propulsion candle" within the activated OB zone: body/total-range ratio ≥ 0.6 (body > wicks), candle direction matches trade direction |
| FR-SP2-11-03 | SHALL require FVG formation using candles in the range [propulsion+1 to propulsion+3] (the 3 candles immediately following the propulsion candle); FVGs detected on or before the propulsion candle itself do not qualify |
| FR-SP2-11-04 | SHALL verify the OB zone was NOT retouched between propulsion candle and current price |
| FR-SP2-11-05 | SHALL require accumulated liquidity on H1 before the OB was activated: defined as a swing high or swing low that has been touched ≥ 2 times within the last 50 H1 candles, indicating clustered orders at that level |
| FR-SP2-11-06 | Entry: retest of the propulsion block zone (the OB zone that contained the propulsion candle) |
| FR-SP2-11-07 | SL: beyond the propulsion block zone extreme + 10-pip buffer |
| FR-SP2-11-08 | Daily bias alignment SHALL significantly boost Opp1 score; misalignment produces NO TRADE |

#### Strategy #12 — Vacuum Block

| ID | Requirement |
|----|-------------|
| FR-SP2-12-01 | SHALL use `gap_detector.py` to identify open price gaps on H1 candles |
| FR-SP2-12-02 | SHALL classify gaps as `weekend_gap`, `session_gap`, or `news_gap` based on time delta between candles |
| FR-SP2-12-03 | The 50% CE level of the gap zone is the primary target and entry trigger; entry is on LTF MSS confirmation near the CE |
| FR-SP2-12-04 | SL: beyond the full gap extent (either side depending on direction) |
| FR-SP2-12-05 | Best application: EURUSD Sunday/Monday opens (weekend gaps) and post-ECB / post-NFP gaps |
| FR-SP2-12-06 | Gaps that have already been fully filled ARE NOT valid setups; `gap_detector.py` tracks fill status. A gap is **fully filled** when a candle's body (open/close range, not wick) closes entirely within the gap zone or beyond the opposite gap boundary. A wick that enters the gap but whose body closes outside it is NOT a full fill and does not invalidate the setup |
| FR-SP2-12-07 | Risk2 agent SHALL flag gap setups occurring outside London or NY Kill Zone as reduced-probability; contributes to lower confidence |

#### Strategy #13 — Reclaimed FVG

| ID | Requirement |
|----|-------------|
| FR-SP2-13-01 | SHALL use the FVG CE-test history from FR-C2-03 to count how many times price has entered the FVG zone but NOT closed beyond the CE |
| FR-SP2-13-02 | Minimum 2 respected CE tests required before setup qualifies |
| FR-SP2-13-03 | The moment any single candle CLOSES beyond the CE on the far side, the reclaim thesis fails: for a **bullish** reclaimed FVG, failure = candle close **above** the CE; for a **bearish** reclaimed FVG, failure = candle close **below** the CE. Setup produces NO TRADE for all subsequent evaluations after failure |
| FR-SP2-13-04 | "Perfect FVG" (Candle 3 body touches the FVG boundary with 0-pip gap — exact match to 5-decimal price) SHALL be flagged as highest-quality in Opp2; setups where the gap between Candle 3 body edge and FVG boundary is ≤ 1 pip are scored as "clean" but not "perfect" |
| FR-SP2-13-05 | Entry at FVG zone boundary (conservative) or CE (optimal); SL beyond full FVG range |
| FR-SP2-13-06 | Opp1 score scales linearly with CE test count: 2 tests = baseline, 3+ tests = bonus points |

#### Strategy #14 — CISD (Change in State of Delivery)

| ID | Requirement |
|----|-------------|
| FR-SP2-14-01 | SHALL detect a bearish sequence (consecutive bearish candles or BOS sequence moving bearish) on M5 |
| FR-SP2-14-02 | Bullish CISD fires when a candle closes ABOVE the opening price of the first candle in that bearish sequence |
| FR-SP2-14-03 | SHALL only fire within 15 pips of an HTF key level (PDH/PDL, swing H/L, OB zone boundary) |
| FR-SP2-14-04 | SHALL require a prior liquidity sweep at or near the key level |
| FR-SP2-14-05 | Requires FVG or OB retest for actual entry; CISD alone is confirmation, not an entry trigger |
| FR-SP2-14-06 | **CISD SHALL be used as confluence only** — a CISD verdict on its own SHALL require at least one other strategy to have fired a WAIT or VALID in the same cluster window; standalone CISD without cluster support caps out at WAIT, never VALID |
| FR-SP2-14-07 | Entry TF: M15/M5 identification; 1M–3M entry during Kill Zones |
| FR-SP2-14-08 | Clustering: CISD shares Confirmation Model ancestry root as an earlier-trigger sibling |

#### Strategy #15 — Balanced Price Range (BPR) in Order Block

| ID | Requirement |
|----|-------------|
| FR-SP2-15-01 | SHALL find an HTF Order Block (H4 or higher) using the existing CED OB detector |
| FR-SP2-15-02 | Within the OB zone, SHALL find overlapping bullish AND bearish FVGs on M15 |
| FR-SP2-15-03 | The BPR is defined as the overlapping region of the two opposing FVGs; minimum overlap size = 3 pips |
| FR-SP2-15-04 | Entry is at the BPR zone midpoint (equilibrium) with LTF structure shift confirmation |
| FR-SP2-15-05 | SL: beyond the full OB zone extreme (not just the BPR zone) |
| FR-SP2-15-06 | Opp1 SHALL treat BPR as one of the highest-probability entry models; initial weighting reflects the 75%+ win rate noted in the strategy specification |
| FR-SP2-15-07 | BPR is an independent root in the ancestry tree; SHALL NOT merge with Confirmation, Unicorn, or Silver Bullet clusters |

### 3.4 Signal clustering update — FR-CL2

| ID | Requirement |
|----|-------------|
| FR-CL2-01 | The clustering ancestry tree SHALL be updated to include all 15 strategies per architecture §6.2 |
| FR-CL2-02 | Extended ancestry tree: ROOT Confirmation (#3) → Silver Bullet (#4), Unicorn (#1), MMM (#9), CISD (#14) |
| FR-CL2-03 | Extended ancestry tree: ROOT Judas Swing (#2) → Power of 3 (#10) |
| FR-CL2-04 | INDEPENDENT roots (no parent): Nested FVGs (#5), iFVG (#6), OTE+FVG (#7), Rejection Block (#8), Propulsion (#11), Vacuum (#12), Reclaimed FVG (#13), BPR in OB (#15) |
| FR-CL2-05 | Within the Confirmation family, representative priority order: Unicorn > Silver Bullet > MMM > CISD > Confirmation |
| FR-CL2-06 | PO3 and Judas Swing may cluster when sharing the same manipulation event; Judas is always representative when both fire |
| FR-CL2-07 | `app/clustering/ancestry.py` SHALL be updated to add Phase 2 strategies |

### 3.5 Dashboard scaling — FR-UI2

| ID | Requirement |
|----|-------------|
| FR-UI2-01 | Segment 2 (`/strategies`) SHALL scale to 15 strategy cards without layout degradation |
| FR-UI2-02 | Grid SHALL adapt: 5 cards per row at viewport ≥ 1400px, 3 cards per row at 768px–1399px, 1 card per row at < 768px |
| FR-UI2-03 | Settings modal SHALL list all 15 strategies with enable/disable toggles; per-strategy confidence threshold override |
| FR-UI2-04 | New strategies producing VALID or WAIT SHALL immediately appear in Segment 2 via the existing SSE mechanism — no dashboard code path changes required |
| FR-UI2-05 | Segment 3 evidence panel SHALL show new evidence fields for Phase 2 strategies: fib levels (OTE+FVG), CE test history (Reclaimed FVG), gap zone details (Vacuum Block), MMM phase (MMM), AMD cycle (PO3), rejection wick ratio (Rejection Block) |
| FR-UI2-06 | Segment 1 strategy leaderboard SHALL include all 15 strategies; disabled strategies shown as greyed-out rows |

---

## 4. Non-Functional Requirements

### 4.1 Performance — NFR-P2

| ID | Requirement |
|----|-------------|
| NFR-P2-01 | CED processing including Phase 2 extensions SHALL complete in < 700 ms per M1 tick on a 2020+ Mac (budget increase from 500 ms due to Fibonacci + FVG test tracking) |
| NFR-P2-02 | Strategy agent evaluation pass (all 15 × 4 = 60 agents) SHALL complete in < 500 ms |
| NFR-P2-03 | Segment 2 with 15 cards SHALL load in < 3 seconds; per-card delta update via SSE unchanged |

### 4.2 Reliability — NFR-R2

| ID | Requirement |
|----|-------------|
| NFR-R2-01 | Phase 2 strategies SHALL be isolated in the same try/except pattern as Phase 1; no new strategy crash SHALL affect Phase 1 strategies |
| NFR-R2-02 | FVG CE-test history SHALL be rebuilt from `events` table on engine restart so it survives process restart |
| NFR-R2-03 | MMM phase state SHALL be persisted to the `settings` KV table on change so restarts maintain continuity |

### 4.3 Cost — NFR-C2

| ID | Requirement |
|----|-------------|
| NFR-C2-01 | Phase 2 additions SHALL incur zero new recurring cost |
| NFR-C2-02 | Oracle Cloud Always Free VM migration (if pursued) must use only the free tier (1 OCPU ARM, 6 GB RAM) |
| NFR-C2-03 | Gemini narrative calls scale with more VALID/WAIT signals (~15 max/day); still within Gemini free tier (15 RPM, 1M tokens/day) |

### 4.4 Security — NFR-S2

| ID | Requirement |
|----|-------------|
| NFR-S2-01 | If Oracle Cloud migration is performed, dashboard SHALL be placed behind Cloudflare Tunnel (free) with HTTP basic auth |
| NFR-S2-02 | All API keys remain in `.env`; no new external API keys required for Phase 2 strategy logic |

### 4.5 Maintainability — NFR-M2

| ID | Requirement |
|----|-------------|
| NFR-M2-01 | Each Phase 2 strategy SHALL live in its own module (`strategy_05_*.py` etc.) with no cross-strategy imports |
| NFR-M2-02 | `fibonacci.py` SHALL be a pure utility consumed by OTE+FVG and Rejection Block; not bundled into either strategy |
| NFR-M2-03 | New CED primitives SHALL have unit tests with hand-crafted candle fixtures before any strategy uses them |
| NFR-M2-04 | Total test coverage target remains ≥ 70% on `app/detector/`, `app/strategies/`, `app/clustering/`, `app/gate/` |

---

## 5. Data Specification

No new tables are required. The existing schema from Phase 1 accommodates all Phase 2 data through:
- `events` table — new `event_type` values for `fibonacci_impulse`, `gap_formed`, `gap_filled`, `fvg_ce_test`, `mmm_phase_change`, `amd_manipulation_detected`
- `signals` table — new `strategy_id` values for the 10 Phase 2 strategies
- `settings` KV table — new keys for `mmm_phase`, `amd_state`, `last_gap_check`

### 5.1 New event_type values

| event_type | Payload fields |
|------------|---------------|
| `fibonacci_impulse` | impulse_direction, swing_high, swing_low, fib_levels (JSON object of level→price) |
| `gap_formed` | gap_type (weekend/session/news), top, bottom, ce, timeframe |
| `gap_filled` | original_gap_id, fill_candle_t |
| `fvg_ce_test` | original_fvg_id, test_candle_t, respected (bool), close_price |
| `mmm_phase_change` | old_phase, new_phase, direction |
| `amd_manipulation_detected` | direction, asian_high, asian_low, manipulation_extreme |

### 5.2 Strategy ID strings (Phase 2)

| Strategy | strategy_id |
|----------|-------------|
| Nested FVGs | `05_nested_fvg` |
| OTE + FVG | `07_ote_fvg` |
| Rejection Block | `08_rejection_block` |
| Market Maker Model | `09_mmm` |
| Power of 3 | `10_po3` |
| Propulsion Block | `11_propulsion` |
| Vacuum Block | `12_vacuum` |
| Reclaimed FVG | `13_reclaimed_fvg` |
| CISD | `14_cisd` |
| BPR in OB | `15_bpr_ob` |

---

## 6. Output Format Contracts

Output formats A, B, and C from Phase 1 are unchanged. Phase 2 adds evidence-panel content for new strategy types.

### 6.1 New evidence panel fields (Segment 3)

**OTE+FVG** (appended to evidence panel):
```
Impulse Leg:      [swing_low] → [swing_high] ([size] pips, [start_time IST])
Fibonacci Levels: 0.618 = [price] | 0.705 = [price] | 0.786 = [price]
OTE Zone:         [fib_0.618] – [fib_0.786]
FVG Overlap:      [fvg_bottom] – [fvg_top] (overlaps OTE at [overlap_pips] pips)
```

**Rejection Block** (appended to evidence panel):
```
Rejection Candle: [time IST] | Wick: [pips] | Body: [pips] | Ratio: [x.x×]
Fib Retracement:  [percentage]% (zone: 80–90% required)
50%-Body Rule:    PASS / FAIL
```

**MMM** (appended to evidence panel):
```
Current Phase:    [1/2/3/4] — [phase name]
Consolidation:    [low] – [high] (identified [N] candles ago)
Target:           [consolidation_low/high] → [engineered_liquidity_level]
```

**PO3** (appended to evidence panel):
```
AMD Cycle:        [Accumulation/Manipulation/Distribution]
Asian Range:      [asian_low] – [asian_high] (IST 05:30–12:30)
Manipulation:     [type] at [extreme] ([time IST])
```

**Reclaimed FVG** (appended to evidence panel):
```
FVG Zone:         [bottom] – [top] | CE: [ce]
CE Tests:         [N] respected tests (required: ≥2)
Last Test:        [time IST] — [respected/failed]
```

**Vacuum Block** (appended to evidence panel):
```
Gap Type:         [weekend/session/news]
Gap Zone:         [bottom] – [top]
50% CE Level:     [ce_price]
Gap Status:       [open / partially filled]
```

---

## 7. Assumptions

1. Phase 1 engine is running stably with all 5 strategies producing signals before Phase 2 development begins.
2. The existing CED CanonicalContext can be extended with new fields without breaking Phase 1 strategy agents (agents read only the fields they care about).
3. Fibonacci calculations are body-to-body; wick measurements are only used for Rejection Block wick classifier.
4. MMM detection operates on Daily + H4 candles only; M1/M5 are not used for phase identification to avoid noise.
5. CISD signals are counted as WAIT at best when standalone; this constraint is enforced in the debate aggregator by Opp1 applying a hard score cap for standalone CISD.
6. Weekend gaps (Vacuum Block) will only appear at Sunday open; the engine must be running at IST 05:30 Sunday for the first candle of the week to be captured.
7. Oracle Cloud migration is OPTIONAL for Phase 2; it's included in scope as a deliverable the user may choose to enable, but Phase 2 strategies are fully functional without it.
8. The 15 RPM / 1M tokens/day Gemini free tier is sufficient for up to 15 published signals/day.

---

## 8. Dependencies & Pre-requisites

### 8.1 Phase 1 completion gate
Phase 2 begins only when Phase 1 is confirmed complete (all §9 acceptance criteria met in Phase 1 spec). The engine must have ≥ 2 weeks of live operation with confirmed signal production.

### 8.2 No new external accounts needed
All Phase 2 work uses the same OANDA, Finnhub, and Gemini API keys from Phase 1.

### 8.3 Oracle Cloud (optional migration)
| Item | Owner | Status |
|------|-------|--------|
| Oracle Cloud Always Free account | Maddy | Not yet created |
| Cloudflare Tunnel (free) | Maddy | Not yet set up |

---

## 9. Acceptance Criteria (Phase 2 done-done)

### 9.1 Functional acceptance

- [ ] All 10 Phase 2 strategies produce correct verdicts on at least 3 historical reference setups each (visual-confirmed on TradingView)
- [ ] New CED modules (fibonacci, long-wick, gap, AMD phase, MMM phase) produce correct outputs on curated fixture datasets
- [ ] Fibonacci levels computed body-to-body match Maddy's manual TradingView measurement within 1 pip
- [ ] OTE+FVG correctly rejects cases where FVG is near but NOT overlapping the OTE band
- [ ] Rejection Block 50%-body-penetration hard veto fires correctly in tests
- [ ] MMM produces NO TRADE for Phases 1, 2, and 4; VALID or WAIT only in Phase 3
- [ ] CISD standalone produces at most WAIT (never VALID without cluster companion)
- [ ] Reclaimed FVG requires ≥ 2 CE tests; FVG that has been breached produces NO TRADE
- [ ] Vacuum Block correctly classifies weekend vs. session vs. news gaps
- [ ] PO3 and Judas Swing correctly cluster on the same manipulation event; Judas is representative
- [ ] Clustering ancestry tree correctly prevents BPR, OTE+FVG, Rejection Block from merging with Confirmation family
- [ ] Segment 2 shows all 15 cards; no visual degradation at 15-card load
- [ ] Segment 3 evidence panels show Phase 2–specific fields (fib levels, CE tests, gap details, MMM phase, AMD cycle)
- [ ] All 15 strategies listed in settings modal with enable/disable working

### 9.2 Non-functional acceptance

- [ ] All API keys in `.env`; never committed
- [ ] `ruff` clean; all public functions type-hinted including Phase 2 modules
- [ ] `pytest` suite green; ≥ 70% coverage maintained on `app/detector/`, `app/strategies/`, `app/clustering/`, `app/gate/`
- [ ] CED tick time ≤ 700 ms with 15-strategy load (measured on Maddy's Mac)
- [ ] Strategy agent pass ≤ 500 ms for 60 agents
- [ ] Zero recurring cost

### 9.3 Operational acceptance

- [ ] System runs continuously with 15 strategies for 2 weeks with < 10 minutes cumulative downtime
- [ ] At least 25 signals (VALID + WAIT + vetoed) recorded across the 15 strategies over 2 weeks
- [ ] At least one signal from each of the 10 Phase 2 strategies observed (VALID, WAIT, or vetoed — any outcome)
- [ ] Maddy has reviewed ≥ 5 Phase 2 setup Segment 3 pages and marked outcomes

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| MMM phase detection is ambiguous on noisy H4 data | Strategy produces excessive false Phase 3 signals | Conservative consolidation threshold (3+ boundary touches each side); expose raw phase data in Segment 3 for manual audit |
| Fibonacci precision mismatch vs TradingView (body vs wick) | OTE+FVG fires on invalid setups | Always use body-to-body; expose impulse swing points in Segment 3 for visual verification |
| Rejection Block 50%-body rule false positives | Hard veto triggers on valid setups | Rule is binary; test explicitly; log the body-penetration measurement in evidence panel |
| Vacuum Block misses Sunday open (engine not running) | Weekend gap setups never detected | launchd / Oracle Cloud KeepAlive ensures 24/7 uptime; backfill on reconnect captures the gap candle |
| CISD over-clustering with Confirmation family | Phantom confidence boosts | Explicit ancestry rule: CISD is a sibling, not a child — same root, but CISD + Confirmation = cluster boost valid; CISD + Unicorn = valid; CISD + random independent = no cluster |
| PO3 and Judas fire on same event but produce conflicting confidence | Cluster representative inconsistency | Judas always representative in PO3/Judas cluster; PO3 confidence contributes only as confluence boost |
| 60-agent evaluation exceeds 500 ms NFR on Mac | Late signals | Profile after first Phase 2 run; parallelize remaining bottlenecks in orchestrator; cache slow CED calls |
| Reclaimed FVG CE-test history lost on restart | Strategy misses prior tests | Rebuild from `events` table (fvg_ce_test rows) on startup; log rebuild count |
| Oracle Cloud migration introduces new failure modes | 24/7 uptime degrades | Migrate only after 15-strategy engine is stable on Mac; keep Mac as fallback during Oracle testing period |
| Phase 2 expansion makes config unwieldy | Hard to tune individual strategy thresholds | Settings modal per-strategy overrides already built in Phase 1; ensure Phase 2 strategies appear in modal |

---

## 11. Glossary Additions

| Term | Meaning |
|------|---------|
| OTE | Optimal Trade Entry — 0.618–0.786 Fibonacci retracement zone |
| BPR | Balanced Price Range — overlapping opposing FVGs forming equilibrium zone |
| CISD | Change in State of Delivery — candle closes above/below opening price of prior opposing sequence |
| AMD | Accumulation-Manipulation-Distribution — intraday PO3 cycle |
| MMM | Market Maker Model — 4-phase institutional price delivery cycle |
| Propulsion Block | Candle inside an activated OB that drives price forcefully away; re-enter on PB retest |
| Vacuum Block | Price gap (no orders executed) at session/weekend/news; 50% CE is primary target |
| Reclaimed FVG | FVG whose CE has been tested ≥2× and respected each time; zone strengthens with tests |
| Rejection Block | Long-wick candle at swing extremes and 80–90% Fib; tightest stops of all PD arrays |
| Breakaway Gap | First FVG in a Nested FVG stack; invalidation point for the whole stack |
| Measuring Gap | Subsequent FVGs in a Nested FVG stack; trail stops behind each as price advances |
| body-to-body Fibonacci | Fib measurement using candle bodies (open/close) not wicks; more accurate than wick-to-wick |

---

## 12. Approval

This specification is a design-time contract for Phase 2. No code will be written until:
- Maddy explicitly approves this document, OR
- Maddy provides corrections to be applied to version 1.1

**On approval**, the next artifact produced will be `.claude/Plan/02-Implementation Plan-Phase2.md` — task breakdown, sequencing, and test approach derived from this spec.

No Phase 1 code is modified or removed during Phase 2. All changes are additive.
