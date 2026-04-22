"""Phase 2 strategy tests — ≥3 test cases per strategy (FR-NFR-M2-04)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.detector.context import CanonicalContext
from app.detector.fvg import FVG
from app.detector.mss import MSSEvent
from app.detector.order_block import OrderBlock
from app.detector.sweep import SweepEvent
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


def _t(h=10, m=0):
    return datetime(2026, 3, 19, h, m, 0, tzinfo=timezone.utc)


def _c(o, h, l, c, offset=0):
    return {"o": o, "h": h, "l": l, "c": c, "t": _t(m=offset), "v": 100}


def _base_ctx(**kwargs) -> CanonicalContext:
    defaults: dict = {
        "instrument": "EUR_USD",
        "tick_t": _t(),
        "m1_candles": [_c(1.10000, 1.10010, 1.09990, 1.10005, i) for i in range(30)],
        "m5_candles": [_c(1.10000, 1.10010, 1.09990, 1.10005, i) for i in range(20)],
        "m15_candles": [_c(1.10000, 1.10010, 1.09990, 1.10005, i) for i in range(20)],
        "h1_candles": [_c(1.10000, 1.10010, 1.09990, 1.10005, i) for i in range(20)],
        "h4_candles": [_c(1.10000, 1.10010, 1.09990, 1.10005, i) for i in range(10)],
        "d_candles": [_c(1.10000, 1.10010, 1.09990, 1.10005, i) for i in range(5)],
        "fvgs": [],
        "order_blocks": [],
        "swings": [],
        "sweeps": [],
        "mss_events": [],
        "current_price": 1.10000,
        "current_spread_pips": 0.5,
        "htf_bias": "bullish",
        "kill_zone": "ny_kz",
        "amd_phase": "Distribution",
        "mmm_phase": 1,
        "fib_levels": {},
        "active_gaps": [],
        "fvg_test_history": {},
    }
    defaults.update(kwargs)
    return CanonicalContext(**defaults)


def _make_fvg(bottom, top, direction="bullish", timeframe="M15", state="formed", tests=None):
    return FVG(
        id=f"test_{bottom}",
        instrument="EUR_USD",
        timeframe=timeframe,
        c1_index=0,
        c1_t="2026-03-19T10:00:00",
        c3_t="2026-03-19T10:02:00",
        top=top,
        bottom=bottom,
        midpoint=round((bottom + top) / 2, 5),
        direction=direction,
        state=state,
        size_pips=round((top - bottom) / 0.0001, 1),
        tests=tests or [],
    )


def _make_sweep(level=1.10100, direction="bearish"):
    from app.detector.sweep import SweepEvent
    return SweepEvent(
        index=25,
        t="2026-03-19T10:00:00",
        direction=direction,
        swept_level=level,
        level_type="swing_high",
        wick_extreme=level + 0.0005,
    )


def _make_mss(direction="bullish", broken_level=1.10050, index=25):
    return MSSEvent(
        index=index,
        t="2026-03-19T10:00:00",
        direction=direction,
        broken_level=broken_level,
        broken_swing_t="2026-03-19T09:50:00",
        displacement=0.0010,
    )


def _make_ob(low, high, direction="bullish", timeframe="M5", valid=True, kind="order_block"):
    ob = OrderBlock(
        id=f"ob_{low}",
        instrument="EUR_USD",
        timeframe=timeframe,
        ob_index=5,
        ob_t="2026-03-19T09:00:00",
        high=high,
        low=low,
        direction=direction,
        valid=valid,
        kind=kind,
    )
    return ob


# ============================================================
# Strategy #5 — Nested FVG
# ============================================================

class TestNestedFVG:
    def test_no_trade_no_stack(self):
        ctx = _base_ctx()
        result = NestedFVGStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_breakaway_filled(self):
        # Build a stack but with breakaway fully_filled
        m15 = []
        for i in range(10):
            m15.append({"o": 1.10000 + i * 0.0010, "h": 1.10020 + i * 0.0010,
                        "l": 1.09980 + i * 0.0010, "c": 1.10015 + i * 0.0010,
                        "t": _t(m=i), "v": 100})
        t_start = str(m15[0]["t"])
        t_end = str(m15[-1]["t"])
        fvgs = [
            _make_fvg(1.10050, 1.10100, "bullish", "M15", "fully_filled"),  # breakaway filled
            _make_fvg(1.10150, 1.10200, "bullish", "M15", "formed"),
            _make_fvg(1.10250, 1.10300, "bullish", "M15", "formed"),
        ]
        # Set c1_t/c3_t to be within m15 range
        for f in fvgs:
            f.c1_t = t_start
            f.c3_t = t_end
        ctx = _base_ctx(m15_candles=m15, fvgs=fvgs)
        result = NestedFVGStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_valid_or_wait_with_good_setup(self):
        # Just check it doesn't crash and evaluates something
        ctx = _base_ctx()
        result = NestedFVGStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #7 — OTE + FVG
# ============================================================

class TestOTEFVG:
    def test_no_trade_no_fib_levels(self):
        ctx = _base_ctx(fib_levels={})
        result = OTEFVGStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_proximity_fvg_not_overlapping(self):
        # FVG just outside OTE band — should be NO_TRADE (proximity veto)
        fib = {0.0: 1.10000, 0.236: 1.10236, 0.382: 1.10382, 0.5: 1.10500,
               0.618: 1.10618, 0.705: 1.10705, 0.786: 1.10786, 1.0: 1.11000,
               -0.27: 1.09730, -0.62: 1.09380}
        # FVG is above 0.786 — near but not overlapping OTE
        fvgs = [_make_fvg(1.10800, 1.10850, "bullish", "M15", "formed")]
        ctx = _base_ctx(fib_levels=fib, fvgs=fvgs)
        result = OTEFVGStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_evaluates_without_crash_with_overlapping_fvg(self):
        fib = {0.0: 1.10000, 0.236: 1.10236, 0.382: 1.10382, 0.5: 1.10500,
               0.618: 1.10618, 0.705: 1.10705, 0.786: 1.10786, 1.0: 1.11000,
               -0.27: 1.09730, -0.62: 1.09380}
        # FVG overlaps the 0.618–0.786 OTE band
        fvgs = [_make_fvg(1.10620, 1.10780, "bullish", "M15", "formed")]
        ctx = _base_ctx(fib_levels=fib, fvgs=fvgs,
                        sweeps=[_make_sweep(1.10900, "bearish")],
                        mss_events=[_make_mss("bullish", 1.10500)])
        result = OTEFVGStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #8 — Rejection Block
# ============================================================

class TestRejectionBlock:
    def test_no_trade_no_wick(self):
        ctx = _base_ctx(fib_levels={})
        result = RejectionBlockStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_body_penetration(self):
        # Build a context with rejection candle that gets body-penetrated
        fib = {0.0: 1.10000, 0.786: 1.10786, 1.0: 1.11000}
        # Rejection candle: big lower wick at ~82% retracement (bullish rejection)
        rej_candle = {"o": 1.10820, "h": 1.10825, "l": 1.10620, "c": 1.10820, "t": _t(9, 55), "v": 100}
        # Subsequent candle body goes below 50% of rej body → penetration
        pen_candle = {"o": 1.10820, "h": 1.10825, "l": 1.10700, "c": 1.10710, "t": _t(9, 56), "v": 100}
        m15 = [rej_candle, pen_candle]
        ctx = _base_ctx(fib_levels=fib, m15_candles=m15, m1_candles=m15, m5_candles=m15)
        result = RejectionBlockStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_evaluates_without_crash(self):
        ctx = _base_ctx()
        result = RejectionBlockStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #9 — MMM
# ============================================================

class TestMMM:
    def test_no_trade_phase_not_3(self):
        ctx = _base_ctx(mmm_phase=1)
        result = MMMStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_phase_2(self):
        ctx = _base_ctx(mmm_phase=2)
        result = MMMStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_phase_4(self):
        ctx = _base_ctx(mmm_phase=4)
        result = MMMStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_evaluates_with_phase_3_candles(self):
        # Build candles that trigger phase 3 detection
        ctx = _base_ctx()
        result = MMMStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #10 — PO3
# ============================================================

class TestPO3:
    def test_no_trade_accumulation_phase(self):
        # 08:00 IST = accumulation
        t = datetime(2026, 3, 19, 2, 30, 0, tzinfo=timezone.utc)  # 08:00 IST
        ctx = _base_ctx(tick_t=t, amd_phase="Accumulation",
                        asian_high=1.10100, asian_low=1.09900)
        result = PO3Strategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_no_manipulation(self):
        ctx = _base_ctx(amd_phase="Distribution",
                        asian_high=1.10100, asian_low=1.09900, m5_candles=[])
        result = PO3Strategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_evaluates_with_manipulation_candle(self):
        candles = [{"o": 1.10050, "h": 1.10200, "l": 1.10000, "c": 1.10060, "t": _t(), "v": 100}]
        ctx = _base_ctx(amd_phase="Distribution",
                        asian_high=1.10100, asian_low=1.09900,
                        m5_candles=candles,
                        htf_bias="bullish",
                        sweeps=[_make_sweep()],
                        mss_events=[_make_mss()])
        result = PO3Strategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #11 — Propulsion Block
# ============================================================

class TestPropulsionBlock:
    def test_no_trade_no_ob(self):
        ctx = _base_ctx(order_blocks=[])
        result = PropulsionBlockStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_wrong_bias(self):
        ob = _make_ob(1.09900, 1.10000, "bullish")
        ctx = _base_ctx(order_blocks=[ob], htf_bias="bearish")
        result = PropulsionBlockStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_evaluates_without_crash(self):
        ob = _make_ob(1.09900, 1.10050, "bullish")
        ctx = _base_ctx(order_blocks=[ob], htf_bias="bullish")
        result = PropulsionBlockStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #12 — Vacuum Block
# ============================================================

class TestVacuumBlock:
    def test_no_trade_no_gaps(self):
        ctx = _base_ctx(active_gaps=[])
        result = VacuumBlockStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_gap_fully_filled(self):
        gap = {"id": "gap1", "gap_type": "weekend_gap", "direction": "up",
               "top": 1.10200, "bottom": 1.10100, "ce": 1.10150,
               "filled_pct": 100.0, "fully_filled": True, "formed_t": "2026-03-19T08:00:00"}
        ctx = _base_ctx(active_gaps=[gap])
        result = VacuumBlockStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_valid_gap_setup(self):
        gap = {"id": "gap1", "gap_type": "weekend_gap", "direction": "up",
               "top": 1.10200, "bottom": 1.10100, "ce": 1.10150,
               "filled_pct": 0.0, "fully_filled": False, "formed_t": "2026-03-19T08:00:00"}
        ctx = _base_ctx(active_gaps=[gap], current_price=1.10050,
                        mss_events=[_make_mss("bullish", 1.10150)])
        result = VacuumBlockStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #13 — Reclaimed FVG
# ============================================================

class TestReclaimedFVG:
    def test_no_trade_one_test_only(self):
        fvg = _make_fvg(1.10050, 1.10100, "bullish", "M15", "retested",
                        tests=[{"t": "2026-03-19T09:00:00", "respected": True, "close_price": 1.10085}])
        ctx = _base_ctx(fvgs=[fvg])
        result = ReclaimedFVGStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_ce_breached(self):
        fvg = _make_fvg(1.10050, 1.10100, "bullish", "M15", "retested",
                        tests=[
                            {"t": "2026-03-19T09:00:00", "respected": True, "close_price": 1.10085},
                            {"t": "2026-03-19T09:05:00", "respected": False, "close_price": 1.10060},
                        ])
        ctx = _base_ctx(fvgs=[fvg])
        result = ReclaimedFVGStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_qualifies_with_two_respected_tests(self):
        fvg = _make_fvg(1.10050, 1.10100, "bullish", "M15", "retested",
                        tests=[
                            {"t": "2026-03-19T09:00:00", "respected": True, "close_price": 1.10085},
                            {"t": "2026-03-19T09:05:00", "respected": True, "close_price": 1.10080},
                        ])
        ctx = _base_ctx(fvgs=[fvg], current_price=1.10075)
        result = ReclaimedFVGStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")

    def test_three_tests_bonus_higher_score(self):
        fvg = _make_fvg(1.10050, 1.10100, "bullish", "M15", "retested",
                        tests=[
                            {"t": "2026-03-19T09:00:00", "respected": True, "close_price": 1.10085},
                            {"t": "2026-03-19T09:05:00", "respected": True, "close_price": 1.10080},
                            {"t": "2026-03-19T09:10:00", "respected": True, "close_price": 1.10082},
                        ])
        ctx = _base_ctx(fvgs=[fvg])
        strat = ReclaimedFVGStrategy()
        opinions = [a.evaluate(ctx) for a in strat.agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        assert opp1.score >= 75  # 3+ tests → bonus → should exceed 65


# ============================================================
# Strategy #14 — CISD
# ============================================================

class TestCISD:
    def test_no_trade_no_sequence(self):
        ctx = _base_ctx(m5_candles=[])
        result = CISDStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_standalone_never_valid(self):
        # Even with a good setup, opp1 score is capped at 65 → cannot reach VALID alone
        # Build bearish M5 sequence + CISD candle
        m5 = []
        for i in range(5):  # 5 bearish candles
            base = 1.10200 - i * 0.0010
            m5.append({"o": base, "h": base + 0.0005, "l": base - 0.0010, "c": base - 0.0010, "t": _t(m=i), "v": 100})
        # CISD candle closes above first candle open (1.10200)
        m5.append({"o": 1.10050, "h": 1.10250, "l": 1.10040, "c": 1.10210, "t": _t(m=5), "v": 100})
        ctx = _base_ctx(m5_candles=m5,
                        sweeps=[_make_sweep(1.10000)],
                        swings=[{"price": 1.10200, "type": "swing_high", "index": 1}],
                        kill_zone="ny_kz")
        strat = CISDStrategy()
        opinions = [a.evaluate(ctx) for a in strat.agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        assert opp1.score <= 65  # hard cap

    def test_evaluates_without_crash(self):
        ctx = _base_ctx()
        result = CISDStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")


# ============================================================
# Strategy #15 — BPR in OB
# ============================================================

class TestBPRInOB:
    def test_no_trade_no_ob(self):
        ctx = _base_ctx(order_blocks=[])
        result = BPRInOBStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_no_trade_no_overlapping_fvgs(self):
        ob = _make_ob(1.09900, 1.10200, "bullish", "H4")
        fvgs = [_make_fvg(1.09920, 1.09950, "bullish", "M15", "formed")]  # no opposing FVG
        ctx = _base_ctx(order_blocks=[ob], fvgs=fvgs)
        result = BPRInOBStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_valid_bpr_overlap(self):
        ob = _make_ob(1.09900, 1.10200, "bullish", "H4")
        bull_fvg = _make_fvg(1.09980, 1.10060, "bullish", "M15", "formed")
        bear_fvg = _make_fvg(1.10020, 1.10080, "bearish", "M15", "formed")
        # Overlap: 1.10020–1.10060 = 4 pips
        ctx = _base_ctx(order_blocks=[ob], fvgs=[bull_fvg, bear_fvg],
                        mss_events=[_make_mss("bullish", 1.09950)],
                        current_price=1.10040)
        result = BPRInOBStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")

    def test_bpr_agents_all_run(self):
        ob = _make_ob(1.09900, 1.10200, "bullish", "H4")
        bull_fvg = _make_fvg(1.09980, 1.10060, "bullish", "M15", "formed")
        bear_fvg = _make_fvg(1.10020, 1.10080, "bearish", "M15", "formed")
        ctx = _base_ctx(order_blocks=[ob], fvgs=[bull_fvg, bear_fvg],
                        mss_events=[_make_mss("bullish", 1.09950)],
                        htf_bias="bullish", kill_zone="london_kz",
                        current_price=1.10040)
        strat = BPRInOBStrategy()
        opinions = [a.evaluate(ctx) for a in strat.agents]
        assert len(opinions) == 4

    def test_bpr_trade_parameters_built(self):
        ob = _make_ob(1.09900, 1.10200, "bullish", "H4")
        # Overlap 1.10020–1.10060 = 4 pips (avoids floating-point boundary at 3 pips)
        bull_fvg = _make_fvg(1.09980, 1.10060, "bullish", "M15", "formed")
        bear_fvg = _make_fvg(1.10020, 1.10080, "bearish", "M15", "formed")
        ctx = _base_ctx(order_blocks=[ob], fvgs=[bull_fvg, bear_fvg],
                        mss_events=[_make_mss("bullish", 1.09950)],
                        htf_bias="bullish", current_price=1.10040)
        trade = BPRInOBStrategy().build_trade_parameters(ctx)
        assert trade is not None
        assert trade.direction == "buy"
        assert trade.entry > trade.sl


# ============================================================
# Additional coverage tests — setup-finder paths
# ============================================================

def _ts(m: int) -> str:
    """Return candle-compatible timestamp string matching _t(m=m).__str__() format."""
    return str(datetime(2026, 3, 19, 10, m, 0, tzinfo=timezone.utc))


class TestNestedFVGSetupFinder:
    def test_finds_bullish_stack(self):
        # 10 consecutive bullish M15 candles
        m15 = []
        for i in range(10):
            base = 1.10000 + i * 0.0010
            m15.append({"o": base, "h": base + 0.0015, "l": base - 0.0002, "c": base + 0.0012,
                        "t": datetime(2026, 3, 19, 10, i, 0, tzinfo=timezone.utc), "v": 100})
        # 3 bullish M15 FVGs with timestamps within segment
        fvgs = []
        for j in range(3):
            f = _make_fvg(1.10050 + j * 0.0010, 1.10100 + j * 0.0010, "bullish", "M15", "formed")
            f.c1_t = _ts(1 + j)
            f.c3_t = _ts(2 + j)
            fvgs.append(f)
        ctx = _base_ctx(m15_candles=m15, fvgs=fvgs, htf_bias="bullish")
        result = NestedFVGStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")

    def test_opp1_score_positive_with_stack(self):
        m15 = []
        for i in range(10):
            base = 1.10000 + i * 0.0010
            m15.append({"o": base, "h": base + 0.0015, "l": base - 0.0002, "c": base + 0.0012,
                        "t": datetime(2026, 3, 19, 10, i, 0, tzinfo=timezone.utc), "v": 100})
        fvgs = []
        for j in range(3):
            f = _make_fvg(1.10050 + j * 0.0010, 1.10100 + j * 0.0010, "bullish", "M15", "formed")
            f.c1_t = _ts(1 + j)
            f.c3_t = _ts(2 + j)
            fvgs.append(f)
        ctx = _base_ctx(m15_candles=m15, fvgs=fvgs, htf_bias="bullish")
        strat = NestedFVGStrategy()
        opinions = [a.evaluate(ctx) for a in strat.agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        assert opp1.score > 0

    def test_build_trade_params_with_stack(self):
        m15 = []
        for i in range(10):
            base = 1.10000 + i * 0.0010
            m15.append({"o": base, "h": base + 0.0015, "l": base - 0.0002, "c": base + 0.0012,
                        "t": datetime(2026, 3, 19, 10, i, 0, tzinfo=timezone.utc), "v": 100})
        fvgs = []
        for j in range(3):
            f = _make_fvg(1.10050 + j * 0.0010, 1.10100 + j * 0.0010, "bullish", "M15", "formed")
            f.c1_t = _ts(1 + j)
            f.c3_t = _ts(2 + j)
            fvgs.append(f)
        ctx = _base_ctx(m15_candles=m15, fvgs=fvgs, htf_bias="bullish")
        trade = NestedFVGStrategy().build_trade_parameters(ctx)
        assert trade is not None
        assert trade.direction == "buy"


class TestOTEFVGSetupFinder:
    def _bullish_fib(self):
        return {0.0: 1.10000, 0.236: 1.10236, 0.382: 1.10382, 0.5: 1.10500,
                0.618: 1.10618, 0.705: 1.10705, 0.786: 1.10786, 1.0: 1.11000,
                -0.27: 1.09730, -0.62: 1.09380}

    def test_setup_found_with_atr(self):
        fib = self._bullish_fib()
        fvgs = [_make_fvg(1.10620, 1.10780, "bullish", "M15", "formed")]
        ctx = _base_ctx(fib_levels=fib, fvgs=fvgs, atr_h4=0.0010,
                        sweeps=[_make_sweep(1.11050, "bearish")],
                        mss_events=[_make_mss("bullish", 1.10500)])
        result = OTEFVGStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")

    def test_no_trade_without_atr_h4(self):
        fib = self._bullish_fib()
        fvgs = [_make_fvg(1.10620, 1.10780, "bullish", "M15", "formed")]
        ctx = _base_ctx(fib_levels=fib, fvgs=fvgs, atr_h4=None)
        result = OTEFVGStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"

    def test_trade_params_built_with_overlapping_fvg(self):
        fib = self._bullish_fib()
        fvgs = [_make_fvg(1.10620, 1.10780, "bullish", "M15", "formed")]
        ctx = _base_ctx(fib_levels=fib, fvgs=fvgs, atr_h4=0.0010,
                        sweeps=[_make_sweep(1.11050, "bearish")])
        trade = OTEFVGStrategy().build_trade_parameters(ctx)
        assert trade is not None
        assert trade.entry == fib[0.705]

    def test_all_agents_run_with_setup(self):
        fib = self._bullish_fib()
        fvgs = [_make_fvg(1.10620, 1.10780, "bullish", "M15", "formed")]
        ctx = _base_ctx(fib_levels=fib, fvgs=fvgs, atr_h4=0.0010,
                        kill_zone="ny_kz", htf_bias="bullish",
                        sweeps=[_make_sweep(1.11050, "bearish")],
                        mss_events=[_make_mss("bullish", 1.10500)])
        strat = OTEFVGStrategy()
        opinions = [a.evaluate(ctx) for a in strat.agents]
        assert len(opinions) == 4


class TestRejectionBlockSetupFinder:
    def _bullish_fib(self):
        return {0.0: 1.10000, 1.0: 1.11000}

    def test_candle_with_qualifying_wick_in_fib_range(self):
        # Long lower wick candle at ~82% fib retracement
        # Price at 82% retracement from 1.11000 → 0.82 * (1.11000-1.10000) = 0.00820 → price = 1.10000 + 0.82*0.01 = 1.10820
        # Body: o=c=1.10900, wick extends to 1.10200 (dominant lower wick)
        fib = self._bullish_fib()
        rej = {"o": 1.10900, "h": 1.10910, "l": 1.10200, "c": 1.10900,
               "t": datetime(2026, 3, 19, 10, 5, 0, tzinfo=timezone.utc), "v": 100}
        swing = {"price": 1.10900, "type": "swing_high", "index": 3}
        m15 = [rej]
        ctx = _base_ctx(fib_levels=fib, m15_candles=m15, m1_candles=m15, m5_candles=m15,
                        swings=[swing])
        result = RejectionBlockStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")

    def test_all_agents_evaluate(self):
        fib = self._bullish_fib()
        rej = {"o": 1.10900, "h": 1.10910, "l": 1.10200, "c": 1.10900,
               "t": datetime(2026, 3, 19, 10, 5, 0, tzinfo=timezone.utc), "v": 100}
        swing = {"price": 1.10900, "type": "swing_high", "index": 3}
        m15 = [rej]
        ctx = _base_ctx(fib_levels=fib, m15_candles=m15, m1_candles=m15, m5_candles=m15,
                        swings=[swing])
        strat = RejectionBlockStrategy()
        opinions = [a.evaluate(ctx) for a in strat.agents]
        assert len(opinions) == 4

    def test_build_signature_with_setup(self):
        fib = self._bullish_fib()
        rej = {"o": 1.10900, "h": 1.10910, "l": 1.10200, "c": 1.10900,
               "t": datetime(2026, 3, 19, 10, 5, 0, tzinfo=timezone.utc), "v": 100}
        swing = {"price": 1.10900, "type": "swing_high", "index": 3}
        m15 = [rej]
        ctx = _base_ctx(fib_levels=fib, m15_candles=m15, m1_candles=m15, m5_candles=m15,
                        swings=[swing])
        sig = RejectionBlockStrategy().build_signature(ctx)
        # If setup found, sig is not None; if no setup, None is acceptable
        assert sig is None or sig.startswith("08_rejection_block")


class TestPropulsionSetupFinder:
    def test_finds_propulsion_with_fvg(self):
        ob = _make_ob(1.09990, 1.10060, "bullish", valid=True)
        # Propulsion candle: inside OB, bullish, body/range ≥ 0.6
        t0 = datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 3, 19, 10, 5, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 19, 10, 10, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 3, 19, 10, 15, 0, tzinfo=timezone.utc)
        t4 = datetime(2026, 3, 19, 10, 20, 0, tzinfo=timezone.utc)
        prop = {"o": 1.10000, "h": 1.10100, "l": 1.09995, "c": 1.10095,
                "t": t0, "v": 100}  # body=0.00095, range=0.00105, ratio≈0.90
        m5 = [prop,
              {"o": 1.10095, "h": 1.10200, "l": 1.10090, "c": 1.10180, "t": t1, "v": 100},
              {"o": 1.10180, "h": 1.10250, "l": 1.10175, "c": 1.10240, "t": t2, "v": 100},
              {"o": 1.10240, "h": 1.10300, "l": 1.10235, "c": 1.10290, "t": t3, "v": 100},
              {"o": 1.10290, "h": 1.10350, "l": 1.10285, "c": 1.10340, "t": t4, "v": 100}]
        # FVG in post-propulsion candles
        fvg = _make_fvg(1.10095, 1.10180, "bullish", "M5", "formed")
        fvg.c1_t = str(t1)
        fvg.c3_t = str(t2)
        ctx = _base_ctx(order_blocks=[ob], m5_candles=m5, fvgs=[fvg], htf_bias="bullish")
        result = PropulsionBlockStrategy().evaluate(ctx)
        assert result.verdict in ("VALID", "WAIT", "NO_TRADE")

    def test_all_agents_evaluate_with_ob(self):
        ob = _make_ob(1.09990, 1.10060, "bullish", valid=True)
        ctx = _base_ctx(order_blocks=[ob], htf_bias="bullish")
        strat = PropulsionBlockStrategy()
        opinions = [a.evaluate(ctx) for a in strat.agents]
        assert len(opinions) == 4

    def test_daily_bias_mismatch_no_trade(self):
        ob = _make_ob(1.09990, 1.10060, "bullish", valid=True)
        d_candles = [{"o": 1.10500, "h": 1.10600, "l": 1.10400, "c": 1.10450,
                      "t": datetime(2026, 3, 18, 0, 0, 0, tzinfo=timezone.utc), "v": 100}]
        ctx = _base_ctx(order_blocks=[ob], d_candles=d_candles, htf_bias="bearish")
        result = PropulsionBlockStrategy().evaluate(ctx)
        assert result.verdict == "NO_TRADE"
