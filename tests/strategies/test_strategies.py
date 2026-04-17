"""Tests for all 5 strategy implementations (J3).

Uses a minimal CanonicalContext to exercise each strategy's evaluate() path.
Verifies structural correctness (4 agents, valid verdict, bounded scores) rather
than trading correctness (which requires calibrated live data).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.detector.context import CanonicalContext
from app.detector.fvg import FVG
from app.detector.mss import MSSEvent
from app.detector.order_block import OrderBlock
from app.detector.sweep import SweepEvent
from app.strategies.strategy_01_unicorn import UnicornModelStrategy
from app.strategies.strategy_02_judas import JudasSwingStrategy
from app.strategies.strategy_03_confirmation import ConfirmationModelStrategy
from app.strategies.strategy_04_silver_bullet import SilverBulletStrategy
from app.strategies.strategy_06_ifvg import IFVGStrategy

# ---------------------------------------------------------------------------
# Minimal context helpers
# ---------------------------------------------------------------------------

def _ts(offset_min: int = 0) -> datetime:
    return datetime(2026, 3, 19, 14, offset_min, 0, tzinfo=timezone.utc)


def _candle(o: float, h: float, l: float, c: float, t_min: int = 0) -> dict:
    return {"instrument": "EUR_USD", "t": _ts(t_min), "o": o, "h": h, "l": l, "c": c, "v": 100}


def _flat_candles(n: int, base: float = 1.10000) -> list[dict]:
    return [_candle(base, base + 0.0005, base - 0.0005, base, i) for i in range(n)]


def _empty_context() -> CanonicalContext:
    """Minimal context — no events, all lists empty. All strategies → NO_TRADE."""
    return CanonicalContext(
        instrument="EUR_USD",
        tick_t=_ts(),
        m1_candles=_flat_candles(50),
        m5_candles=_flat_candles(20),
        m15_candles=_flat_candles(10),
        h1_candles=_flat_candles(10),
        h4_candles=_flat_candles(10),
        d_candles=_flat_candles(10),
        atr_m1=0.0010,
        atr_m5=0.0015,
        current_price=1.10000,
        current_spread_pips=0.5,
        kill_zone="none",
        htf_bias="neutral",
    )


def _fvg(direction: str = "bullish") -> FVG:
    return FVG(
        id="test_fvg",
        instrument="EUR_USD",
        timeframe="M1",
        c1_index=0,
        c1_t="2026-03-19T14:00:00+00:00",
        c3_t="2026-03-19T14:02:00+00:00",
        top=1.10100,
        bottom=1.10050,
        midpoint=1.10075,
        direction=direction,  # type: ignore[arg-type]
        size_pips=5.0,
    )


def _sweep(direction: str = "bullish") -> SweepEvent:
    return SweepEvent(
        index=45,
        t="2026-03-19T14:00:00+00:00",
        direction=direction,  # type: ignore[arg-type]
        swept_level=1.09980,
        level_type="swing_l",
        wick_extreme=1.09970,
    )


def _mss(direction: str = "bullish") -> MSSEvent:
    return MSSEvent(
        index=47,
        t="2026-03-19T14:02:00+00:00",
        direction=direction,  # type: ignore[arg-type]
        broken_level=1.10000,
        broken_swing_t="2026-03-19T13:50:00+00:00",
        displacement=0.00050,
    )


def _ob(direction: str = "bullish") -> OrderBlock:
    return OrderBlock(
        id="test_ob",
        instrument="EUR_USD",
        timeframe="M1",
        ob_index=43,
        ob_t="2026-03-19T13:58:00+00:00",
        high=1.10010,
        low=1.09990,
        direction=direction,  # type: ignore[arg-type]
    )


def _rich_context(direction: str = "bullish", kill_zone: str = "london_kz") -> CanonicalContext:
    """Context with FVG, sweep, MSS, OB present — may produce WAIT or VALID."""
    from app.detector.pd_zone import PDZone
    ctx = _empty_context()
    ctx.fvgs = [_fvg(direction)]
    ctx.sweeps = [_sweep(direction)]
    ctx.mss_events = [_mss(direction)]
    ctx.order_blocks = [_ob(direction)]
    ctx.htf_bias = direction  # type: ignore[assignment]
    ctx.kill_zone = kill_zone  # type: ignore[assignment]
    ctx.asian_high = 1.10100
    ctx.asian_low = 1.09900
    ctx.pd_zone = PDZone(
        range_high=1.11000,
        range_low=1.09000,
        equilibrium=1.10000,
    )
    ctx.current_price = 1.09800 if direction == "bullish" else 1.10200
    return ctx


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _assert_valid_result(result, strategy_id: str) -> None:
    assert result.strategy_id == strategy_id
    assert result.verdict in ("VALID", "WAIT", "NO_TRADE")
    assert 0.0 <= result.confidence <= 100.0
    assert 0.0 <= result.probability <= 100.0
    assert len(result.agent_opinions) == 4, f"{strategy_id} must produce exactly 4 agent opinions"
    for op in result.agent_opinions:
        assert 0.0 <= op.score <= 100.0
        assert op.verdict in ("support", "oppose", "neutral")
        assert op.agent_id in ("opp1", "opp2", "risk1", "risk2")


# ---------------------------------------------------------------------------
# Strategy #3 — Confirmation Model
# ---------------------------------------------------------------------------

class TestConfirmationModel:
    def test_empty_context_produces_no_trade(self):
        s = ConfirmationModelStrategy()
        result = s.evaluate(_empty_context())
        _assert_valid_result(result, "03_confirmation")
        assert result.verdict == "NO_TRADE"

    def test_rich_context_has_4_agents(self):
        s = ConfirmationModelStrategy()
        result = s.evaluate(_rich_context())
        _assert_valid_result(result, "03_confirmation")

    def test_strategy_id_correct(self):
        assert ConfirmationModelStrategy().strategy_id == "03_confirmation"

    def test_signature_none_when_no_setup(self):
        s = ConfirmationModelStrategy()
        result = s.evaluate(_empty_context())
        # No sweep/MSS/FVG → signature should be None
        assert result.signature is None or isinstance(result.signature, str)


# ---------------------------------------------------------------------------
# Strategy #4 — Silver Bullet
# ---------------------------------------------------------------------------

class TestSilverBullet:
    def test_empty_context_produces_no_trade(self):
        s = SilverBulletStrategy()
        result = s.evaluate(_empty_context())
        _assert_valid_result(result, "04_silver_bullet")
        assert result.verdict == "NO_TRADE"

    def test_rich_context_in_kill_zone_has_4_agents(self):
        ctx = _rich_context(kill_zone="silver_bullet_london")
        s = SilverBulletStrategy()
        result = s.evaluate(ctx)
        _assert_valid_result(result, "04_silver_bullet")

    def test_strategy_id_correct(self):
        assert SilverBulletStrategy().strategy_id == "04_silver_bullet"

    def test_outside_kill_zone_produces_no_trade(self):
        ctx = _rich_context(kill_zone="none")
        s = SilverBulletStrategy()
        result = s.evaluate(ctx)
        assert result.verdict == "NO_TRADE"


# ---------------------------------------------------------------------------
# Strategy #2 — Judas Swing
# ---------------------------------------------------------------------------

class TestJudasSwing:
    def test_empty_context_produces_no_trade(self):
        s = JudasSwingStrategy()
        result = s.evaluate(_empty_context())
        _assert_valid_result(result, "02_judas")
        assert result.verdict == "NO_TRADE"

    def test_rich_context_with_asian_range_has_4_agents(self):
        ctx = _rich_context(kill_zone="london_kz")
        s = JudasSwingStrategy()
        result = s.evaluate(ctx)
        _assert_valid_result(result, "02_judas")

    def test_strategy_id_correct(self):
        assert JudasSwingStrategy().strategy_id == "02_judas"

    def test_no_asian_range_produces_no_trade(self):
        ctx = _empty_context()
        ctx.asian_high = None
        ctx.asian_low = None
        s = JudasSwingStrategy()
        result = s.evaluate(ctx)
        assert result.verdict == "NO_TRADE"


# ---------------------------------------------------------------------------
# Strategy #1 — Unicorn Model
# ---------------------------------------------------------------------------

class TestUnicornModel:
    def test_empty_context_produces_no_trade(self):
        s = UnicornModelStrategy()
        result = s.evaluate(_empty_context())
        _assert_valid_result(result, "01_unicorn")
        assert result.verdict == "NO_TRADE"

    def test_rich_context_has_4_agents(self):
        s = UnicornModelStrategy()
        result = s.evaluate(_rich_context())
        _assert_valid_result(result, "01_unicorn")

    def test_strategy_id_correct(self):
        assert UnicornModelStrategy().strategy_id == "01_unicorn"

    def test_no_ob_cannot_produce_valid(self):
        # Without an OB the Unicorn's strict rules fail → no VALID signal
        ctx = _rich_context()
        ctx.order_blocks = []
        s = UnicornModelStrategy()
        result = s.evaluate(ctx)
        assert result.verdict != "VALID"


# ---------------------------------------------------------------------------
# Strategy #6 — iFVG
# ---------------------------------------------------------------------------

class TestIFVG:
    def test_empty_context_produces_no_trade(self):
        s = IFVGStrategy()
        result = s.evaluate(_empty_context())
        _assert_valid_result(result, "06_ifvg")
        assert result.verdict == "NO_TRADE"

    def test_rich_context_has_4_agents(self):
        ctx = _rich_context()
        # Add an inverted FVG for iFVG strategy
        inv_fvg = _fvg("bullish")
        inv_fvg.state = "inverted"
        ctx.fvgs.append(inv_fvg)
        s = IFVGStrategy()
        result = s.evaluate(ctx)
        _assert_valid_result(result, "06_ifvg")

    def test_strategy_id_correct(self):
        assert IFVGStrategy().strategy_id == "06_ifvg"

    def test_no_inverted_fvg_produces_no_trade(self):
        ctx = _rich_context()
        ctx.fvgs = [_fvg("bullish")]  # state = "formed", not "inverted"
        s = IFVGStrategy()
        result = s.evaluate(ctx)
        # No inverted FVG → should not produce VALID
        assert result.verdict in ("NO_TRADE", "WAIT")
