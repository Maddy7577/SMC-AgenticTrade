# Phase 2 Implementation Plan — SMC-TradeAgents

**Project:** SMC-TradeAgents
**Phase:** 2 (Full Strategy Expansion)
**Version:** 1.0
**Date:** 2026-04-18
**Status:** Approved — ready for implementation
**Parent spec:** `.claude/Specs/02-Spec Document-Phase2.md` (v1.0)

---

## Context

Phase 1 delivered a 5-strategy engine (Unicorn, Judas Swing, Confirmation, Silver Bullet, iFVG) with a complete signal pipeline: OANDA polling → CED → debate → gate → clustering → dashboard. Phase 2 extends this by adding 10 new SMC strategies (#5, #7–#15), 5 new CED detector modules, updated clustering ancestry, and a scaled dashboard. All changes are strictly additive — no Phase 1 code is modified or removed.

**Pre-condition:** Phase 1 engine must be confirmed stable (≥2 weeks live) before Phase 2 code lands in production. Development and testing can proceed in parallel.

---

## Critical Files

| File | Action |
|------|--------|
| `app/detector/context.py` | Add 5 new CanonicalContext fields |
| `app/detector/pipeline.py` | Wire new detectors into CED tick |
| `app/detector/fvg.py` | Add CE-test history tracking |
| `app/clustering/ancestry.py` | Expand ancestry tree to 15 strategies |
| `app/strategies/orchestrator.py` | Add 10 strategies to ALL_STRATEGIES |
| `app/dashboard/templates/segment_2.html` | 15-card responsive grid CSS |
| `app/dashboard/templates/segment_3.html` | New evidence panel fields |

---

## Stage 1 — CED Extensions (Foundation)

All new detector modules must be complete and unit-tested before any Phase 2 strategy code is written (NFR-M2-03).

### 1A. New detector modules (pure functions, no DB)

**`app/detector/fibonacci.py`** (new file)
- Function: `compute_fib_levels(swing_high: float, swing_low: float, direction: str) -> dict[float, float]`
- Levels: 0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0, -0.27, -0.62
- Measurement: body-to-body (use open/close, not high/low wicks)
- Returns dict keyed by level float, value = price at that level
- Bullish: 0.0 = swing_low, 1.0 = swing_high; Bearish: 0.0 = swing_high, 1.0 = swing_low

**`app/detector/long_wick_classifier.py`** (new file)
- Function: `classify_wick(candle: dict) -> dict | None`
- Returns `{type: "bullish_rejection"|"bearish_rejection", wick_pips: float, body_pips: float, ratio: float}` or None
- Qualifying condition: dominant wick ≥ 2× body AND dominant wick ≥ 2× opposing wick
- Bullish rejection = long lower wick; Bearish rejection = long upper wick

**`app/detector/gap_detector.py`** (new file)
- Function: `detect_gaps(h1_candles: list[dict]) -> list[dict]`
- Gap up: `curr.l > prev.h`; Gap down: `curr.h < prev.l`
- Gap dict: `{gap_type, top, bottom, ce, filled_pct, formed_t}`
- Classification by time delta: `weekend_gap` (>24h), `news_gap` (1h–24h), `session_gap` (<1h)
- Full-fill: candle **body** closes inside/beyond gap zone — wick-only entry is NOT a fill
- Function: `update_gap_fill_status(gaps: list[dict], new_candle: dict) -> list[dict]`

**`app/detector/amd_phase.py`** (new file)
- Function: `get_amd_phase(tick_t, asian_high, asian_low, m5_candles) -> str`
- Returns: `"Accumulation" | "Manipulation" | "Distribution" | "Unknown"`
- Boundaries (IST/UTC+5:30): Accumulation 05:30–12:30 | Manipulation 12:30–15:30 | Distribution 15:30–21:30
- Manipulation detection: false breakout of Asian range against HTF bias during London window

**`app/detector/mmm_phase.py`** (new file)
- Function: `detect_mmm_phase(h4_candles, d_candles) -> dict`
- Returns: `{phase: int, consolidation_low, consolidation_high, direction}`
- Phase 1=Consolidation (≥3 touches each boundary over 50-candle Daily lookback), 2=Sell Program (expansion away from consolidation), 3=Smart Money Reversal, 4=Buy Program or inverse
- Persist phase changes to `settings` KV table on change (NFR-R2-03)

### 1B. FVG CE-test history enrichment

**`app/detector/fvg.py`** (modify existing)
- Add `tests: list[dict]` field to FVG state object (initially `[]`)
- Add function: `update_fvg_ce_tests(fvgs, new_candle) -> list[FVG]`
- Record per-test: `{t: str, respected: bool, close_price: float}`
- `respected = True` if candle closes back inside zone (did NOT close beyond CE)
- Bullish failure: close < CE; Bearish failure: close > CE
- Persist `fvg_ce_test` events to `events` table
- Rebuild test history from `events` table on engine startup (NFR-R2-02)

### 1C. CanonicalContext extension

**`app/detector/context.py`** — add 5 fields with defaults (preserves Phase 1 compatibility):
```python
fib_levels: dict[float, float] = field(default_factory=dict)
active_gaps: list[dict] = field(default_factory=list)
amd_phase: str = "Unknown"
mmm_phase: int = 0
fvg_test_history: dict[int, list[dict]] = field(default_factory=dict)
```

### 1D. Pipeline integration

**`app/detector/pipeline.py`** — import and call each new detector per tick:
- Wire all outputs into CanonicalContext construction
- Persist new event types: `fibonacci_impulse`, `gap_formed`, `gap_filled`, `fvg_ce_test`, `mmm_phase_change`, `amd_manipulation_detected`
- MMM phase: call `detect_mmm_phase()` on H4+Daily; write to `settings` KV on change
- FVG CE-tests: call `update_fvg_ce_tests()` after FVG detection pass

### 1E. Tests for Stage 1

New files in `tests/detector/`:
- `test_fibonacci.py` — levels at known swings; body-to-body measurement verified
- `test_long_wick.py` — qualifying wicks pass; mixed wicks fail; doji → None
- `test_gap_detector.py` — all 3 gap types; fill detection (body rule vs wick rule)
- `test_amd_phase.py` — phase at each session boundary; manipulation detection
- `test_mmm_phase.py` — consolidation with 3+ touches; phase sequencing
- Extend `test_fvg.py` — CE-test recording; respected vs failed; rebuild from events

---

## Stage 2 — Phase 2 Strategies

Each strategy follows the identical file structure as Phase 1:
- 4 inner agent classes: `_Opp1Agent`, `_Opp2Agent`, `_Risk1Agent`, `_Risk2Agent`
- Top-level strategy class: `evaluate(ctx) -> StrategyResult`, `build_trade_parameters()`, `build_signature()`, `build_evidence()`
- Call `compute_verdict()` from `app/strategies/debate.py` (unchanged)
- Signature format: `"{strategy_id}:{direction}:{level1}:{level2}:{entry_midpoint}"`

Implement in this order (simpler → complex):

### 2A — Group A: Build on existing CED data

**`app/strategies/strategy_05_nested_fvg.py`** — Nested FVGs
- Opp1: displacement leg ≥5 consecutive same-direction M15 candles with ≥3 FVGs; classify first as `breakaway_gap`, rest `measuring_gap`; breakaway NOT fully filled
- Opp2: entire M15 FVG zone contained within H4 FVG zone (both boundaries); Kill Zone active
- Risk1: breakaway gap filled → invalidate (`strict_rules_met = False`); HTF bias check
- Risk2: Asian stack outside Kill Zone = score penalty; spread
- Entry: CE of last FVG in stack
- SL: beyond entry FVG extreme + 5-pip buffer at entry; **trail SL dynamically** — as price advances through each subsequent FVG, move SL to behind that FVG's bottom (bullish) or top (bearish) + 5-pip buffer (FR-SP2-05-05)
- Evidence: displacement leg candle count, FVG stack list (breakaway + measuring), breakaway fill status
- Signature: `"05_nested_fvg:{direction}:{breakaway_ce}:{last_fvg_ce}:{entry}"`

**`app/strategies/strategy_11_propulsion.py`** — Propulsion Block
- Opp1: activated OB from `ctx.order_blocks`; propulsion candle inside OB (body/range ≥ 0.6); FVG in candles [propulsion+1 to propulsion+3]; OB NOT retouched since propulsion
- Opp2: accumulated H1 liquidity (swing H/L touched ≥2× in last 50 H1 candles); daily bias alignment
- Risk1: daily bias misalignment = NO_TRADE; OB retouched = veto
- Risk2: outside Kill Zone; spread
- Entry: retest of propulsion block zone | SL: beyond OB extreme + 10-pip buffer
- Evidence: activated OB zone, propulsion candle details (body/range ratio), FVG formed after propulsion, H1 liquidity touches
- Signature: `"11_propulsion:{direction}:{ob_low}:{ob_high}:{entry}"`

**`app/strategies/strategy_15_bpr_ob.py`** — BPR in OB
- Opp1: HTF OB (H4+); overlapping bullish AND bearish M15 FVG within OB zone; overlap ≥ 3 pips = BPR; LTF structure shift; **BPR treated as highest-probability entry model — initial Opp1 base score reflects 75%+ win rate** (FR-SP2-15-06)
- Opp2: H4+ OB scores max; H1 OB scores reduced; confluence bonus if OB aligns with HTF PD zone
- Risk1: overlap < 3 pips → NO_TRADE; OB already mitigated → NO_TRADE
- Risk2: outside Kill Zone; spread
- Entry: BPR midpoint | SL: beyond full OB extreme (not BPR boundary)
- Evidence: OB zone, bullish FVG details, bearish FVG details, BPR overlap size (pips), BPR midpoint
- Signature: `"15_bpr_ob:{direction}:{ob_low}:{ob_high}:{bpr_mid}"`
- **Independent ancestry root** — never merges with any family

**`app/strategies/strategy_14_cisd.py`** — CISD
- Opp1: bearish M5 sequence (≥3 consecutive bearish candles); CISD = close above first candle open; within 15 pips of HTF key level; prior sweep; **hard Opp1 score cap of 65** (prevents standalone VALID)
- Opp2: FVG or OB available for entry; Kill Zone active
- Risk1: >15 pips from key level → hard oppose; no sweep → oppose
- Risk2: no cluster companion in window = score capped; spread
- Entry TF: **M15/M5 for setup identification; 1M–3M for precise entry during Kill Zones** (FR-SP2-14-07)
- Entry: FVG or OB retest after CISD trigger | SL: beyond key level sweep extreme
- Signature: `"14_cisd:{direction}:{key_level}:{sequence_open}:{entry}"`
- Evidence: M5 sequence candles, CISD trigger candle, key level, sweep event
- **Confirmation ancestry family**

### 2B — Group B: Require new CED primitives

**`app/strategies/strategy_07_ote_fvg.py`** — OTE + FVG Confluence
- Uses: `ctx.fib_levels`
- Opp1: H4 impulse ≥3× ATR_H4; M15 FVG physically overlaps OTE band 0.618–0.786; prior sweep before impulse
- Opp2: OB within OTE zone = bonus; NY KZ session preferred (IST 18:00–20:30)
- Risk1: FVG near OTE but NOT overlapping → NO_TRADE (hard veto); no sweep → oppose
- Risk2: outside NY KZ; spread
- Entry: 0.705 fib level; zone = FVG boundary | SL: 100% fib + 15-pip buffer
- TP1 = 0% fib | TP2 = −0.27 ext | TP3 = −0.62 ext
- Signature: `"07_ote_fvg:{direction}:{impulse_low}:{impulse_high}:{fvg_ce}"`
- Evidence: impulse leg, fib levels, OTE zone, FVG overlap pips

**`app/strategies/strategy_08_rejection_block.py`** — Rejection Block
- Uses: `classify_wick()`, `ctx.fib_levels`
- Opp1: rejection candle (wick ≥2× body via classifier); Fib retracement 80–90%; rejection at HTF key level; MSS/CHoCH on M15/M5
- Opp2: H1+ = 1 wick; M15 = ≥2 wicks required; wick quality bonus
- Risk1: **50%-body-penetration → `strict_rules_met = False` → NO_TRADE**; no MSS → oppose
- Risk2: outside Kill Zone; spread
- Entry: price returns to rejection body | SL: 10 pips beyond wick extreme | TP: RR ≥ 3.0
- Signature: `"08_rejection_block:{direction}:{key_level}:{wick_extreme}:{body_ce}"`
- Evidence: wick/body ratio, fib retracement %, 50%-body rule PASS/FAIL

**`app/strategies/strategy_12_vacuum.py`** — Vacuum Block
- Uses: `ctx.active_gaps`
- Opp1: open unfilled gap present; LTF MSS near 50% CE level
- Opp2: weekend gap = max; news gap = high; session gap = moderate
- Risk1: gap fully filled → `strict_rules_met = False` → NO_TRADE; no MSS → oppose
- Risk2: outside London/NY KZ = reduced probability; spread
- Entry: LTF MSS near CE | SL: beyond full gap extent
- Signature: `"12_vacuum:{direction}:{gap_bottom}:{gap_top}:{gap_ce}"`
- Evidence: gap type, zone, 50% CE, fill status

**`app/strategies/strategy_13_reclaimed_fvg.py`** — Reclaimed FVG
- Uses: `ctx.fvg_test_history`
- Opp1: ≥2 respected CE tests; "Perfect FVG" flag (Candle 3 body touches boundary exactly); Opp1 scales: 2 tests = baseline, 3+ = bonus
- Opp2: ≤1 pip gap = "clean"; test recency bonus
- Risk1: CE breach (close beyond CE far side) → `strict_rules_met = False` → NO_TRADE forever; bullish fail = close above CE; bearish fail = close below CE
- Risk2: outside Kill Zone; spread
- Entry: FVG boundary (conservative) or CE (optimal) | SL: beyond full FVG range
- Signature: `"13_reclaimed_fvg:{direction}:{fvg_bottom}:{fvg_top}:{fvg_ce}"`
- Evidence: CE test count, test timestamps, respected/failed

### 2C — Group C: Phase-tracker strategies

**`app/strategies/strategy_09_mmm.py`** — Market Maker Model
- Uses: `ctx.mmm_phase`
- Opp1: `mmm_phase == 3` required; consolidation zone identified; BSL/SSL confirmed; MSS at HTF PD array; FVG after MSS
- Opp2: phase sequencing quality; consolidation clarity
- Risk1: `mmm_phase != 3` → immediate NO_TRADE (`strict_rules_met = False`); no consolidation → oppose
- Risk2: spread; low Daily range
- Entry: FVG retracement after Phase 3 MSS | SL: 20 pips beyond MSS swing extreme
- TP1 = consol low/high | TP2 = opposite consol boundary | TP3 = engineered liquidity
- Signature: `"09_mmm:{direction}:{consol_low}:{consol_high}:{entry}"`
- Evidence: all 4 phases shown (even NO_TRADE), consolidation zone, targets
- **Confirmation family** — priority: Unicorn > Silver Bullet > MMM > CISD > Confirmation

**`app/strategies/strategy_10_po3.py`** — Power of 3 / AMD
- Uses: `ctx.amd_phase`, `ctx.asian_high`, `ctx.asian_low`
- Opp1: `amd_phase == "Distribution"` for VALID; `"Manipulation"` caps at WAIT; Asian range set; manipulation (false breakout against HTF bias in London KZ); MSS/CHoCH reversal after
- Opp2: FVG or OB from displacement after MSS; HTF bias alignment
- Risk1: `amd_phase == "Accumulation"` → NO_TRADE; no manipulation sweep → oppose; no MSS → oppose
- Risk2: spread; time of day
- Entry: FVG or OB after MSS | SL: beyond manipulation wick + 10-pip buffer
- TP1 = Asian opposite boundary | TP2 = PDH/PDL
- Signature: `"10_po3:{direction}:{asian_high}:{asian_low}:{entry}"`
- Evidence: AMD cycle, Asian range, manipulation extreme + time
- **Judas family** — Judas always representative when both fire

### 2D. Register all strategies

**`app/strategies/orchestrator.py`** — add imports and extend ALL_STRATEGIES:
```python
# Phase 2 imports
from app.strategies.strategy_05_nested_fvg import NestedFVGStrategy
from app.strategies.strategy_07_ote_fvg import OTEFVGStrategy
from app.strategies.strategy_08_rejection_block import RejectionBlockStrategy
from app.strategies.strategy_09_mmm import MMMStrategy
from app.strategies.strategy_10_po3 import PO3Strategy
from app.strategies.strategy_11_propulsion import PropulsionBlockStrategy
from app.strategies.strategy_12_vacuum import VacuumBlockStrategy
from app.strategies.strategy_13_reclaimed_fvg import ReclaimedFVGStrategy
from app.strategies.strategy_14_cisd import CISDStrategy
from app.strategies.strategy_15_bpr_ob import BPRInOBStrategy

ALL_STRATEGIES: list[BaseStrategy] = [
    # Phase 1 (unchanged order)
    UnicornModelStrategy(), JudasSwingStrategy(), ConfirmationModelStrategy(),
    SilverBulletStrategy(), IFVGStrategy(),
    # Phase 2
    NestedFVGStrategy(), OTEFVGStrategy(), RejectionBlockStrategy(),
    MMMStrategy(), PO3Strategy(), PropulsionBlockStrategy(),
    VacuumBlockStrategy(), ReclaimedFVGStrategy(), CISDStrategy(), BPRInOBStrategy(),
]
```

### 2E. Strategy tests

New file: `tests/strategies/test_strategies_phase2.py`
- ≥3 test cases per strategy (valid setup, wait setup, no_trade boundary)
- Add new candle scenarios to `tests/fixtures/scenarios.py` as needed
- Key boundary tests:
  - OTE+FVG: proximity-only FVG → NO_TRADE; overlapping FVG → VALID/WAIT
  - Rejection Block: 50% body penetration → NO_TRADE
  - MMM: phase 1/2/4 → NO_TRADE; phase 3 → evaluates normally
  - CISD standalone: confidence cap prevents VALID (max 65 from Opp1)
  - Reclaimed FVG: 1 test → NO_TRADE; 2 respected → qualifies; CE breach → NO_TRADE
  - Vacuum Block: filled gap → NO_TRADE; wick-only gap entry → gap still open
  - PO3 + Judas: same manipulation event clusters; Judas is representative

---

## Stage 3 — Clustering Ancestry Update

**`app/clustering/ancestry.py`** — rewrite for 15 strategies:

```python
# Confirmation family — priority order (index 0 = highest priority representative)
CONFIRMATION_FAMILY = ["01_unicorn", "04_silver_bullet", "09_mmm", "14_cisd", "03_confirmation"]

# Judas family — Judas always representative (index 0)
JUDAS_FAMILY = ["02_judas", "10_po3"]

# Independent roots — never merge with any other family
INDEPENDENT_ROOTS = {
    "05_nested_fvg", "06_ifvg", "07_ote_fvg", "08_rejection_block",
    "11_propulsion", "12_vacuum", "13_reclaimed_fvg", "15_bpr_ob"
}
```

`can_cluster_together(a, b)` logic:
- Both in CONFIRMATION_FAMILY → True
- Both in JUDAS_FAMILY → True
- Either in INDEPENDENT_ROOTS → False
- Mixed families → False

`select_representative(strategy_ids)`:
- Search CONFIRMATION_FAMILY order first, then JUDAS_FAMILY, then fallback to first item

**`app/clustering/cluster_engine.py`** — no changes needed (ancestry.py drives the logic).

Update `tests/strategies/test_clustering.py`:
- CISD + Unicorn → can cluster
- BPR + Unicorn → cannot cluster
- PO3 + Judas → clusters; Judas representative
- MMM priority below Silver Bullet in representative selection

---

## Stage 4 — Dashboard Scaling

### 4A. Strategy card grid

**`app/dashboard/templates/segment_2.html`** — update CSS only, no HTML structure changes:
```css
.strategy-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);   /* ≥1400px */
}
@media (max-width: 1399px) { .strategy-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 767px)  { .strategy-grid { grid-template-columns: 1fr; } }
```

### 4B. Evidence panels (Segment 3)

**`app/dashboard/templates/segment_3.html`** — add conditional blocks per strategy:
- OTE+FVG: impulse leg, fib levels (0.618/0.705/0.786), OTE zone, FVG overlap pips
- Rejection Block: wick/body ratio, fib %, 50%-body rule PASS/FAIL
- MMM: current phase + name, consolidation zone, targets
- PO3: AMD cycle, Asian range, manipulation extreme + time IST
- Reclaimed FVG: CE test count, timestamps, respected/failed per test
- Vacuum Block: gap type, zone, 50% CE, fill status

Each Phase 2 strategy must implement `build_evidence() -> dict` to populate these fields into the signal's `evidence` JSON column.

### 4C. Settings modal and leaderboard

**`app/dashboard/templates/segment_1.html`**:
- Add all 10 Phase 2 strategy IDs to enable/disable toggle list
- Disabled strategies = greyed-out rows in leaderboard
- Per-strategy confidence threshold override inputs

---

## Stage 5 — Integration, Lint & Performance

```bash
# Smoke test through full 15-strategy pipeline
python3 scripts/replay_day.py

# Full test suite with coverage
python3 -m pytest tests/ --cov=app/detector --cov=app/strategies --cov=app/clustering --cov=app/gate

# Lint
python3 -m ruff check .
python3 -m ruff check . --fix
```

**Performance targets** (measure after first live run):
- CED tick ≤ 700 ms — log in `pipeline.py`
- Strategy agent pass ≤ 500 ms for 60 agents — log in `orchestrator.py`
- Segment 2 with 15 cards initial load ≤ 3 seconds (NFR-P2-03); per-card SSE delta unchanged
- If CED/agent budgets exceeded: cache MMM phase per H4 close (not every M1 tick); profile with `cProfile`

---

## Sequencing

```
Stage 1 (CED + tests)
    ↓
Stage 2A — Group A (#5, #11, #14, #15)
    ↓
Stage 2B — Group B (#7, #8, #12, #13)
    ↓
Stage 2C — Group C (#9, #10)
    ↓
Stage 2D — Register ALL_STRATEGIES + 2E tests
    ↓
Stage 3 (ancestry) ←→ Stage 4 (dashboard)  [parallel]
    ↓
Stage 5 (integration + lint + perf)
```

---

## Verification Checklist

- [ ] `python3 -m pytest tests/ -v` — all green, ≥70% coverage on 4 modules
- [ ] `python3 -m ruff check .` — zero errors; all new public functions type-hinted
- [ ] `python3 scripts/replay_day.py` — all 15 strategies emit verdicts, no crashes
- [ ] Dashboard Segment 2 — 15 cards, initial load ≤ 3 seconds, responsive at 1400px / 768px / mobile
- [ ] Settings modal — all 15 strategies (Phase 1 + Phase 2) listed with enable/disable toggles
- [ ] Each of the 10 Phase 2 strategies produces correct verdicts on ≥3 historical reference setups (visual-confirmed on TradingView)
- [ ] Fibonacci levels (body-to-body) match Maddy's manual TradingView measurement within 1 pip on a known impulse leg
- [ ] OTE+FVG: near-miss FVG fixture (proximity but no overlap) → NO_TRADE; overlapping FVG → VALID/WAIT
- [ ] Rejection Block: 50%-body-penetration fixture → NO_TRADE
- [ ] MMM phase 1/2/4 → NO_TRADE; phase 3 with correct setup → VALID/WAIT
- [ ] CISD standalone confidence < 75 (never VALID alone)
- [ ] Vacuum Block: correctly classifies weekend / session / news gap fixtures; filled gap → NO_TRADE
- [ ] Reclaimed FVG: 1 CE test → NO_TRADE; 2 respected tests → qualifies; CE breach → NO_TRADE on all subsequent evaluations
- [ ] PO3 + Judas cluster → Judas is representative
- [ ] BPR + Unicorn → `can_cluster_together()` returns False

### Operational acceptance (post-deployment — spec §9.3)
*Verified during live operation, not at code merge.*

- [ ] System runs continuously with all 15 strategies for 2 weeks with < 10 minutes cumulative downtime
- [ ] ≥ 25 signals (VALID + WAIT + vetoed) recorded across all 15 strategies over 2 weeks
- [ ] At least 1 signal observed from each of the 10 Phase 2 strategies (any verdict counts)
- [ ] Maddy has reviewed ≥ 5 Phase 2 setup Segment 3 evidence pages and marked outcomes
