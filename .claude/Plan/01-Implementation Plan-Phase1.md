# Phase 1 Implementation Plan — SMC-TradeAgents

**Version:** 1.0 (plan only; no code)
**Date:** 2026-04-16
**Parents:**
- Architecture: `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/.claude/Documents/system_architecture.md` (v1.1)
- Spec: `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/.claude/Specs/01-Spec Document-Phase1.md` (v1.0)

**Destination after approval:** Upon approval of this plan, it should be copied to the project's canonical location at `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/.claude/Plan/01-Implementation Plan-Phase1.md` (plan mode restricts writes to this koala file only).

---

## Context

SMC-TradeAgents is a zero-cost (TradingView Premium aside) EURUSD trade intelligence engine being built greenfield on the user's Mac. The user is a discretionary trader who needs algorithmic confirmation and discipline, not auto-execution.

The architecture (v1.1) and Phase 1 spec (v1.0) are both approved and locked. This plan translates spec requirements FR-*/NFR-* into an executable task sequence, with dependency ordering, milestones, tests, and risk callouts. Phase 1 delivers the full pipeline — data ingestion, Canonical Event Detector (CED), 5 strategies × 4 agents each, clustering, decision gate, 3-segment Flask dashboard, Gemini-generated narratives, and performance tracking — for strategies #3, #4, #2, #1, and #6. Phases 2 and 3 add the remaining 10 strategies on top of the same foundation.

**Why this plan exists:** the spec defines *what* to build; this plan defines *order, dependencies, tests, and proof-of-done* so implementation is unambiguous when plan mode exits.

---

## Sequencing Rationale

Build **bottom-up to first-signal**, then broaden horizontally:

1. **Data + storage first** — every downstream module replays candles from SQLite
2. **CED before strategies** — all 5 strategies share primitives; building detectors against one strategy first forces rework
3. **Thin vertical slice (Strategy #3) early** to de-risk the full pipeline (ingest → detect → agents → debate → signal row) before fanning out to 5
4. **Clustering + Gate before dashboard** — Segment 2 cards render clustered, gated output; without them the UI has nothing meaningful
5. **Dashboard third-to-last** so we don't paint over a moving API
6. **Narrative + performance + launchd last** — value-additive, not load-bearing

Fastest-value-first: a single strategy producing NO TRADE verdicts from live OANDA data is more valuable at end-of-Week-1 than a half-built dashboard.

---

## Prerequisite User Actions (before Epic A starts)

| Item | Owner | Blocker? |
|------|-------|----------|
| OANDA v20 demo account + API token | Maddy | Yes — blocks B3 onward |
| Finnhub free API key | Maddy | Blocks B7 |
| Google AI Studio account + Gemini API key | Maddy | Blocks F1 |

These can be obtained while Epic A (scaffolding) proceeds.

---

## Task Breakdown (execution order, ≤4h per task)

### Epic A — Bootstrap & Scaffolding

| # | Task | Deps | Est |
|---|------|------|-----|
| A1 | Create directory skeleton per arch §12; `pyproject.toml`, `requirements.txt`, `ruff.toml` | — | 1h |
| A2 | `.env.example`, `.gitignore`, `README.md` stub; `config/settings.py` with `python-dotenv` loader | A1 | 1h |
| A3 | `config/settings.py` constants: thresholds (75/65), RR floor 2.0, confluence boost table, pip size, timeframe list, kill-zone windows in IST+UTC | A1 | 2h |
| A4 | `config/instruments.py`: EUR_USD/GBP_USD pip value, digits, tick size | A1 | 0.5h |
| A5 | Rotating logger (NFR-O-01/02): `logs/smc.log`, 10 MB × 5, key=value formatter | A2 | 1h |
| A6 | `tests/` layout, `conftest.py`, fixtures dir, local `ruff check` pre-commit | A1 | 1h |

### Epic B — Data Layer

| # | Task | Deps | Est |
|---|------|------|-----|
| B1 | SQLAlchemy core schema in `app/storage/db.py` for all 9 tables (spec §5); WAL mode (NFR-R-03); migration bootstrap | A3 | 3h |
| B2 | `app/storage/repositories.py`: typed upsert/read helpers per table | B1 | 3h |
| B3 | `app/ingestion/oanda_client.py` — REST candle polling M1/M5/M15/H1/H4/D × EUR_USD+GBP_USD (FR-D-03) | A3, B2 | 3h |
| B4 | OANDA pricing stream consumer (async), exponential backoff 1→30s, 5-retry alert (FR-D-06, NFR-R-01) | B3 | 4h |
| B5 | Gap-detection + backfill-on-reconnect (FR-D-07); idempotent insert (FR-D-04) | B3, B4 | 2h |
| B6 | `scripts/backfill_history.py` — 30d M1/M5/M15 + 1y H1/H4/D (FR-D-05) | B3 | 2h |
| B7 | `app/ingestion/finnhub_client.py`; APScheduler 15-min job; USD+EUR filter; persist to `calendar` (FR-D-08) | A3, B2 | 2h |
| B8 | Health snapshot aggregator (last candle/TF, stream status, calendar last sync) for `/health` (NFR-O-03, FR-D-09) | B4, B7 | 1h |

### Epic C — Canonical Event Detector

Pure functions over candle lists (NFR-M-03). Built against fixture candles, not live.

| # | Task | Deps | Est |
|---|------|------|-----|
| C1 | `app/detector/swings.py` — rolling swing H/L with lookback | B2 | 2h |
| C2 | `app/detector/atr.py` — ATR per timeframe | B2 | 1h |
| C3 | `app/detector/fvg.py` — 3-candle detection, ≥5 pips, state machine `formed/retested/partially_filled/fully_filled/inverted` (FR-C-02/03) | C1 | 4h |
| C4 | `app/detector/order_block.py` — last-opposite-color + 2×ATR (FR-C-04); Breaker flag on post-sweep invalidation (FR-C-05) | C1, C2, C3 | 4h |
| C5 | `app/detector/mss.py` — swing break + displacement (FR-C-07) | C1, C2 | 2h |
| C6 | `app/detector/sweep.py` — PDH/PDL, EQH/EQL 5-pip tolerance, Asian range, swing H/L (FR-C-06) | C1 | 3h |
| C7 | `app/detector/pd_zone.py` — premium/discount from H4/D dealing range (FR-C-08) | C1 | 2h |
| C8 | `app/detector/kill_zone.py` — IST window enum (FR-C-09) | A3 | 1h |
| C9 | `app/detector/htf_bias.py` — D1/H4 BOS sequence → bullish/bearish/neutral (FR-C-10) | C5 | 2h |
| C10 | `app/detector/smt_divergence.py` — EURUSD vs GBPUSD swing comparison, 50-M5 window (FR-C-11) | C1 | 3h |
| C11 | `app/detector/pipeline.py` — orchestrator: on M1 close run all modules, persist `events` (FR-C-12), emit to `asyncio.Queue` (FR-C-13); <500 ms budget (NFR-P-01) | C3–C10 | 3h |
| C12 | `CanonicalContext` dataclass — events + bias + zone + kill zone + ATR + SMT snapshot consumed by agents | C11 | 1h |

### Epic D — Strategies & Agents

| # | Task | Deps | Est |
|---|------|------|-----|
| D1 | `app/strategies/base.py` — `Agent`, `AgentOpinion`, `Strategy` interfaces (FR-S-03) | C12 | 2h |
| D2 | `app/strategies/debate.py` — aggregator: weighted_mean(opp)−weighted_mean(risk_oppose); verdict per FR-S-09; probability = agreement × confluence × clarity | D1 | 3h |
| D3 | `app/strategies/scoring.py` — shared helpers: displacement strength, wick quality, structure clarity, RR math | D1 | 2h |
| D4 | **Strategy #3 Confirmation Model** + 4 agents (FR-SP-03-*) | D1–D3 | 4h |
| D5 | **Strategy #4 Silver Bullet** + 4 agents, IST window gate (FR-SP-04-*) | D1–D3, C8 | 4h |
| D6 | **Strategy #2 Judas Swing** + 4 agents, Asian range logic (FR-SP-02-*) | D1–D3, C6 | 4h |
| D7 | **Strategy #1 Unicorn Model** + 4 agents, FVG∩Breaker ≥10% overlap (FR-SP-01-*) | D1–D3, C3, C4 | 4h |
| D8 | **Strategy #6 iFVG** + 4 agents, body-close breach + SMT weighting (FR-SP-06-*) | D1–D3, C3, C10 | 4h |
| D9 | Strategy registry + orchestrator: subscribes to CED queue, dispatches to enabled strategies, writes `signals` + `agent_scores` (FR-S-10) | D4–D8 | 2h |

Opportunity/Risk agent 2-flavor distinction (Opp1 strict, Opp2 quality; Risk1 technical, Risk2 contextual) implemented via shared mixins extracted during D4–D8 (FR-S-04 to FR-S-07).

### Epic E — Clustering & Decision Gate

| # | Task | Deps | Est |
|---|------|------|-----|
| E1 | `app/clustering/signature.py` — canonical signature tuple, rounding helpers (FR-CL-01) | D9 | 1h |
| E2 | `app/clustering/ancestry.py` — Phase 1 ancestry tree (Unicorn > Silver Bullet > Confirmation; Judas parent; iFVG independent) | — | 0.5h |
| E3 | `app/clustering/cluster_engine.py` — 5-min bucket group, representative selection, confluence boost, `clusters` row (FR-CL-02 to CL-05) | E1, E2 | 3h |
| E4 | `app/gate/decision_gate.py` — 9 vetoes in order most-likely-to-reject-first: Monday → news → daily losses → monthly cap → confidence floor → RR → spread → cooling (FR-G-01 to FR-G-09) | E3, B7 | 4h |
| E5 | Counter state management — daily loss (reset 00:00 IST), monthly trades (1st IST), cooling (20m post sl_hit); persist so restart doesn't wipe | E4 | 2h |
| E6 | Publish fanout — on post-gate VALID/WAIT: insert `trades`, trigger narrative, push SSE (FR-G-10) | E4 | 2h |

### Epic F — Narrative (Gemini)

| # | Task | Deps | Est |
|---|------|------|-----|
| F1 | `app/narrative/gemini_client.py` — `google-generativeai` wrapper, 5s timeout, fallback text (FR-N-01/04, NFR-P-05) | A3 | 2h |
| F2 | Prompt template — strategy, rules, evidence, agent scores, trade params, IST stamps (FR-N-02/03) | F1 | 1h |
| F3 | Async invocation from publish fanout; persist to `trades.narrative`; never regenerate (FR-N-05) | F1, F2, E6 | 1h |

### Epic G — Dashboard (Flask + SSE + Plotly)

| # | Task | Deps | Est |
|---|------|------|-----|
| G1 | `app/dashboard/flask_app.py` — app factory, 127.0.0.1 bind, dark theme base, IST Jinja filter (FR-UI-01/05/08) | B2 | 2h |
| G2 | `base.html` + static CSS (dark, monospaced numerics, mobile-responsive) | G1 | 3h |
| G3 | SSE broadcaster: plain Flask `stream_with_context`; 15s polling fallback flag (NFR-P-04) | G1, E6 | 3h |
| G4 | **Segment 1** `/` — equity curve, leaderboard, day×session heatmap, daily summary, filters (FR-UI-02) | G1, H2 | 4h |
| G5 | **Segment 2** `/strategies` — one card per strategy, status badge, cluster badge, last-10 dots, 30d WR chip, settings modal (FR-UI-03/07) | G1, G3 | 4h |
| G6 | Segment 2 calendar ticker + countdown + BLACKOUT ACTIVE badge (FR-UI-06) | G5, B7 | 2h |
| G7 | **Segment 3** `/signal/<id>` — trade card, 4-agent debate panel, evidence panel + raw JSON, Plotly candlestick with FVG/OB/MSS annotations, Gemini narrative, outcome buttons (FR-UI-04) | G5, F3 | 4h |
| G8 | Copy-to-clipboard on every price level (FR-UI-10); TradingView deep-link builder (FR-UI-11) | G7 | 1h |
| G9 | `/health` JSON endpoint (NFR-O-03) | B8 | 0.5h |

### Epic H — Performance Monitor

| # | Task | Deps | Est |
|---|------|------|-----|
| H1 | `app/performance/tracker.py` — price poller, marks TP1/TP2/SL/manual_close (FR-P-02) | B4, E6 | 3h |
| H2 | `app/performance/stats.py` — rolling 30d/all-time WR, avg RR, expectancy, per-day×session (FR-P-05/06) | H1 | 3h |
| H3 | Auto-flag negative-expectancy strategies ≥50 trades (FR-P-07) | H2 | 1h |
| H4 | Outcome override actions from Segment 3 write back to `trades` (FR-P-03); taken-vs-theoretical separation (FR-P-06) | G7, H1 | 1h |

### Epic I — Ops & Orchestration

| # | Task | Deps | Est |
|---|------|------|-----|
| I1 | `app/main.py` — asyncio entrypoint wiring Ingestion → CED → Strategies → Cluster → Gate → Publish → Narrative + Flask; APScheduler for Finnhub + counter resets | All above | 3h |
| I2 | Per-strategy try/except isolation so one bad agent doesn't kill engine (NFR-R-04) | I1 | 1h |
| I3 | `scripts/com.maddy.smc-tradeagents.plist` — launchd auto-start at login, working dir, log redirect | I1 | 1h |
| I4 | `scripts/replay_day.py` — replay past UTC day through full pipeline | B2, D9 | 2h |

### Epic J — Testing

| # | Task | Deps | Est |
|---|------|------|-----|
| J1 | Fixture capture — 10 curated EURUSD scenarios (Unicorn, Judas false-break, iFVG post-sweep, NO TRADE, news window, Monday) to `tests/fixtures/` | B6 | 3h |
| J2 | Unit tests: every CED primitive with hand-crafted candles; boundary cases (5-pip floor, EQH tolerance, FVG inversion) (NFR-M-04) | C3–C10 | 1h ea |
| J3 | Strategy detection tests against fixtures | D4–D8, J1 | 1h ea |
| J4 | Clustering test: triple-hit (Confirm+SB+Unicorn) → single cluster, Unicorn representative, +15% boost (spec §9.1) | E3 | 1h |
| J5 | Gate tests — one per veto (Monday, conf<75, RR<2, news, 3rd loss, monthly cap, spread, cooling) | E4 | 2h |
| J6 | Integration slice via `replay_day.py` on fixture day | I4 | 2h |

---

## Dependency Graph (Critical Path)

```
A1 → A3 ─┬─→ B1 → B2 ─┬─→ B3 → B4 → B5
         │            └─→ B7 → E4
         └─→ C8
B2 → C1 → C2/C3/C5/C6/C7/C9/C10 → C11 → C12 → D1 → D2/D3
                                                       ↓
                                              D4..D8 → D9
                                                       ↓
                                               E1/E2 → E3 → E4 → E6 → F3
                                                                       ↓
                                                      G1 → G2 → G3 → G5/G7
                                                                       ↓
                                                                 H1 → H2 → G4
                                                                       ↓
                                                                      I1 → I3
```

**Parallelizable once B2 lands:**
- C1–C10 detectors (after C1 for swings)
- D4–D8 strategies (after D3)
- G1/G2 dashboard shell (in parallel with Epic D)
- F1/F2 narrative (fully parallel after A3)

**Serial chokepoints:** A3 → B2 → C11 → D9 → E3 → E4 → E6 → G7 → I1.

---

## Milestones

| M | Name | Proves | Maps to |
|---|------|--------|---------|
| M1 | Candles flowing | Epic A, B done. OANDA auth OK, stream live, candles persisted, reconnect survives manual disconnect, `/health` available | FR-D-*, NFR-R-01 |
| M2 | First FVG from live feed | CED pipeline runs on live M1 closes; real FVG event in `events` table with correct top/bottom/state | FR-C-*, NFR-P-01 |
| M3 | First NO TRADE from Strategy #3 | Confirmation Model writes a NO TRADE row with 4 agent scores and reasons | FR-S-*, FR-SP-03-* |
| M4 | 5 strategies + clustering + gate | D4–D8 + E1–E6 done; fabricated triple-hit yields 1 cluster (Unicorn rep +15%); fabricated Monday vetoed | FR-CL-*, FR-G-*, spec §9.1 |
| M5 | Dashboard end-to-end | Segments 1/2/3 load; published signal appears on Segment 2 within 15s; Segment 3 shows 4 agents + narrative + chart; outcome buttons work | FR-UI-*, FR-N-* |
| M6 | Phase 1 done-done | Epic H + I done; launchd auto-start works; 24h continuous run; spec §9 checklist green | spec §9 full |

---

## Testing Approach (summary)

| Epic | Unit | Fixtures | Integration |
|------|------|----------|-------------|
| A | Settings env round-trip | — | — |
| B | Repo upsert idempotency; gap fill | OANDA candle JSON batches | 1-day stream replay → row count matches |
| C | Per-primitive hand-crafted candles; boundary cases (5-pip floor, EQH tolerance, FVG inversion) | 3 positive / 3 negative per primitive | CED pipeline on fixture day → expected event count |
| D | Agents in isolation; debate threshold transitions (74→75, 64→65, RR 1.99 vs 2.0) | 3 real reference setups per strategy | Orchestrator replay |
| E | Signature bucketing; ancestry tie-break; each veto in isolation | Triple-hit; Monday; news-window | End-to-end publish on fabricated cluster |
| F | Prompt builder snapshot; API-failure fallback | Mocked Gemini response | On-publish hook test |
| G | Template render smoke; IST filter; copy-to-clip handler | — | `requests.get` all 3 routes, assert key strings |
| H | Expectancy math; realized-R calc | Synthetic trades | Stats recompute on outcome update |
| I | — | — | `replay_day.py` idempotent across 2 runs |

Coverage target per spec §9.2: ≥70 % on `app/detector/`, `app/strategies/`, `app/clustering/`, `app/gate/`.

---

## Risk Callouts

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | **FVG state machine complexity** cascades into every strategy | State-transition table before code; dedicated tests; visually verify fixtures in TradingView first |
| R2 | OANDA stream **silent stalls** / duplicate candles / clock drift | Heartbeat timeout (no price > 30s = force reconnect); (instrument, t) PK dedupes; trust OANDA server time |
| R3 | **SMT Divergence semantics** under-specified | Document decision in module docstring: compare last N swing highs/lows between EURUSD+GBPUSD; divergence when one makes HH while other makes LH (and vice versa) |
| R4 | **Ancestry tree** must not merge iFVG or Judas with Confirmation family | Explicit no-parent roots; clustering only merges within same root |
| R5 | **SSE fragility** on Flask dev server | Plain `stream_with_context`; feature-flag fallback to polling; accept degraded UX if SSE slips |
| R6 | Gemini rate limit or API shape change | Single retry + backoff; fallback text; never block publish on narrative |
| R7 | **Counter state across restarts** — IST boundary, not UTC | Persist to SQLite; rehydrate from trades-today + last-stopout on startup; `ZoneInfo("Asia/Kolkata")` for boundary |
| R8 | **Monday veto timezone bug** (signal at 19:30 UTC Sunday = 01:00 IST Monday) | Gate computes day via Asia/Kolkata; explicit test for cross-midnight case |
| R9 | Mac sleeps mid-session — signals lost | launchd `KeepAlive`; document `caffeinate`; `/health` surfaces "stale: last candle > 2 min" |
| R10 | Agent score calibration unknown until data arrives | Tunable weights in `config/settings.py`; log every agent score including NO TRADE for tuning data |
| R11 | Clustering false-merges | Manual review of first 20 live clusters; log full cluster decisions |
| R12 | Unicorn overlap check on moving zones | Snapshot Breaker + FVG zones at MSS candle close time; recompute only on invalidation |

---

## Spec Ambiguities — Baked-In Defaults (override at approval time)

| # | Spec item | Default chosen | Rationale |
|---|-----------|----------------|-----------|
| 1 | Probability formula factors | `agreement ∈ [0.6..1.0]` from score-variance; `confluence ∈ {1.0, 1.10, 1.15, 1.20}` from cluster size; `clarity ∈ [0..1]` from Opp2 quality / 100 | Aligns with spec §5.6 confidence decomposition |
| 2 | Option-C "Conditions to meet" format | Structured list of rule-IDs with `✓/✗` | Machine-checkable, auditable |
| 3 | iFVG SMT weighting (FR-SP-06-03) | SMT-aligned: Opp2 +10; SMT-opposed: Risk1 +15 | Reflects "strongly weighted but not hard" |
| 4 | TP3 population on Confirm/SB | Populate only when extended liquidity exists beyond TP2 | Avoids phantom targets |
| 5 | Settings modal persistence | DB-backed (new `settings` KV table) | Survives restarts; simpler than env hot-reload |
| 6 | Cooling-period source (FR-G-09) | Only `trades.outcome='sl_hit'` | Manual close ambiguity; strict interpretation |
| 7 | Monthly cap (FR-G-06) counts | VALID publishes (not "taken") | Consistent with FR-G-06 signal language |

**None of these are blocking** — all can be flipped via settings module after implementation.

---

## Critical Files to Create

Top-tier (load-bearing — any bug here breaks the pipeline):

- `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/app/storage/db.py` — schema, WAL, migrations
- `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/app/detector/pipeline.py` — CED orchestrator; tick-to-events contract (FR-C-01, NFR-P-01)
- `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/app/strategies/base.py` — Agent/Strategy interfaces (FR-S-03)
- `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/app/gate/decision_gate.py` — codified risk controls (FR-G-*, arch §15)
- `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/app/main.py` — asyncio entrypoint wiring everything (I1)

Second tier: `app/clustering/cluster_engine.py`, `app/detector/fvg.py`, `app/dashboard/flask_app.py`.

Full module tree listed in architecture §12.

---

## Reusable Utilities (none from existing codebase)

The Gold Strategy project was inaccessible to exploration (permissions). No patterns are being reused. All files are greenfield. If the user later grants access, the plan allows opportunistic reuse of Flask templates or agent mixins, but Phase 1 assumes zero borrow.

---

## End-to-End Verification Recipe

Run in order; all must pass for Phase 1 done-done. Maps to spec §9.

1. **24h continuous run** (§9.1#1, §9.3#1) — launch via launchd, verify at 24h via `/health` + candle-count delta
2. **Calendar populated** (§9.1#2) — Segment 2 ticker shows ≥1 USD high-impact event
3. **CED primitives on fixtures** (§9.1#3) — `pytest tests/detector/ -v` all green
4. **3 historical setups per strategy** (§9.1#4) — `scripts/replay_day.py` on 5 pre-selected days; each strategy detects ≥1 setup/day, visually TV-confirmed
5. **Agent distinctness** (§9.1#5) — Segment 3 of any published signal: 4 agents have distinct scores + reasons
6. **Triple-hit cluster** (§9.1#6) — replay fabricated day; `clusters` row has 3 members, representative = Unicorn, boost = +15 %
7. **Gate vetoes** (§9.1#7) — 5 synthetic inserts (Monday, conf=74, RR=1.9, news window, 3rd daily loss) all marked `gate_result='vetoed:<reason>'`, none on Segment 2
8. **Dashboard wiring** (§9.1#8) — Segments 1→2→3 all render, auto-refresh observed, card click opens correct Segment 3
9. **Narrative + fallback** (§9.1#9) — one real publish with Gemini OK; one synthetic with wrong key shows fallback text
10. **Performance monitor** (§9.1#10) — after 5 synthetic outcomes, Segment 1 shows correct WR/avg RR/expectancy
11. **launchd** (§9.1#11) — `launchctl list | grep smc` shows plist loaded; kill PID, restart within 60s
12. **NFR sweep** (§9.2) — `ruff check .` clean; `pytest --cov` ≥70 % on 4 target dirs; `/health` 200 OK with expected keys; no API keys in logs; no `.env` in git log
13. **2-week operation** (§9.3) — ≥10 signals recorded, ≥5 Segment 3 outcome marks, tracked in `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/journal.md`

---

## Estimated Effort

- **Total tasks:** 62
- **Total estimated hours:** ~135h of focused build time (excluding testing-in-parallel)
- **If worked ~4h/day:** 5–7 weeks to M6
- **First live signal (M3) reachable:** 2–3 weeks from Epic A start
- **Minimum runnable slice (M4 without dashboard):** 3–4 weeks

Unknowns that could expand this: OANDA stream quirks (R2), FVG state machine edge cases (R1), agent calibration iterations after first-signal data (R10).

---

## Post-Approval Actions (once ExitPlanMode clears)

1. Copy this plan to `/Users/maddy/Documents/Claude Project/SMC-TradeAgents/.claude/Plan/01-Implementation Plan-Phase1.md`
2. Confirm the 7 baked-in defaults (section above) — apply overrides to `config/settings.py` before Epic D
3. Prompt the user to provision OANDA demo, Finnhub, and Gemini keys (if not already)
4. Begin Epic A: scaffolding.

No code, configuration, or directory structure is created until the plan is approved.
