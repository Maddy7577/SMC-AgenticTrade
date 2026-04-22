"""Strategy #13 — Reclaimed FVG (FR-SP2-13-*).

≥2 respected CE tests required. CE breach → strict_rules_met=False forever.
Opp1 scales: 2 tests = baseline, 3+ = bonus.
"""

from __future__ import annotations

import logging

from app.detector.context import CanonicalContext
from app.strategies.base import (
    AgentOpinion,
    BaseAgent,
    BaseStrategy,
    StrategyResult,
    TradeParameters,
)
from app.strategies.debate import compute_verdict
from config.instruments import pips_to_price

log = logging.getLogger(__name__)

STRATEGY_ID = "13_reclaimed_fvg"
_MIN_CE_TESTS = 2


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_reclaimed_fvg(ctx: CanonicalContext):
    """Return (fvg, respected_tests, failed) or None."""
    active_fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested", "partially_filled")]
    for fvg in reversed(active_fvgs):
        tests = fvg.tests
        if not tests:
            continue
        respected = [t for t in tests if t["respected"]]
        failed = [t for t in tests if not t["respected"]]
        # Any failure = thesis broken
        if failed:
            continue
        if len(respected) >= _MIN_CE_TESTS:
            return fvg, respected, False
    return None


def _is_ce_breached(fvg) -> bool:
    """Return True if any test has respected=False (CE breach)."""
    return any(not t["respected"] for t in fvg.tests)


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        setup = _find_reclaimed_fvg(ctx)
        if not setup:
            # Check if there are FVGs with tests but CE breached
            breached = any(_is_ce_breached(f) for f in ctx.fvgs if f.tests)
            if breached:
                return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                    reasons=["✗ CE breach detected — NO_TRADE permanently"], evidence={"ce_breached": True})
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no FVG with ≥2 respected CE tests"], evidence={})
        fvg, respected, _ = setup
        test_count = len(respected)
        base_score = 70.0
        bonus = 10.0 if test_count >= 3 else 0.0
        score = min(base_score + bonus, 100.0)
        evidence["ce_test_count"] = test_count
        evidence["fvg_id"] = fvg.id
        evidence["fvg_zone"] = {"top": fvg.top, "bottom": fvg.bottom, "ce": fvg.ce}
        evidence["tests"] = respected
        reasons.append(f"✓ {test_count} respected CE tests (min: {_MIN_CE_TESTS})")
        if test_count >= 3:
            reasons.append("✓ 3+ tests bonus")
        # Perfect FVG check (Candle 3 body touches boundary exactly)
        # Approximate: check if gap size is ≤1 pip (clean)
        if fvg.size_pips <= 1.0:
            evidence["perfect_fvg"] = True
            reasons.append("✓ Perfect FVG (gap ≤1 pip)")
        elif fvg.size_pips <= 3.0:
            reasons.append("FVG gap clean (≤3 pips)")
        verdict = "support" if score >= 65 else "neutral"
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict,
                            reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 45.0
        reasons: list[str] = []
        setup = _find_reclaimed_fvg(ctx)
        if setup:
            fvg, respected, _ = setup
            # Gap cleanliness
            if fvg.size_pips <= 1.0:
                score += 20
                reasons.append("✓ perfect FVG — clean gap")
            elif fvg.size_pips <= 3.0:
                score += 10
                reasons.append("clean FVG gap")
            # Recency bonus
            if respected:
                score += 10
                reasons.append(f"last test: {respected[-1]['t']}")
        if ctx.kill_zone in ("london_kz", "ny_kz", "silver_bullet_ny_am"):
            score += 10
            reasons.append(f"✓ kill zone: {ctx.kill_zone}")
        score = round(min(max(score, 0), 100), 1)
        verdict = "support" if score >= 65 else ("neutral" if score >= 45 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk1Agent(BaseAgent):
    agent_id = "risk1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        breached = any(_is_ce_breached(f) for f in ctx.fvgs if f.tests)
        if breached:
            score += 80
            reasons.append("✗ CE breach — strict_rules_met=False → NO_TRADE permanently")
        elif not _find_reclaimed_fvg(ctx):
            score += 40
            reasons.append("insufficient CE tests or no qualified FVG")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={"ce_breached": breached})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        if ctx.kill_zone == "none":
            score += 15
            reasons.append("outside session windows")
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread elevated: {ctx.current_spread_pips:.1f} pips")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class ReclaimedFVGStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Reclaimed FVG"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        setup = _find_reclaimed_fvg(ctx)
        if not setup:
            return None
        fvg, _, _ = setup
        if _is_ce_breached(fvg):
            return None
        direction = fvg.direction
        entry = fvg.ce  # optimal entry
        if direction == "bullish":
            sl = round(fvg.bottom - pips_to_price(5), 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(entry + 2 * risk, 5)
            tp2 = round(entry + 3 * risk, 5)
            trade_dir = "buy"
        else:
            sl = round(fvg.top + pips_to_price(5), 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(entry - 2 * risk, 5)
            tp2 = round(entry - 3 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        setup = _find_reclaimed_fvg(ctx)
        if not setup:
            return None
        fvg, _, _ = setup
        return f"{STRATEGY_ID}:{fvg.direction}:{_rnd(fvg.bottom)}:{_rnd(fvg.top)}:{_rnd(fvg.ce)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        setup = _find_reclaimed_fvg(ctx)
        if not setup:
            return {}
        fvg, respected, _ = setup
        return {
            "fvg_zone": {"bottom": fvg.bottom, "top": fvg.top, "ce": fvg.ce},
            "fvg_bottom": fvg.bottom,
            "fvg_top": fvg.top,
            "fvg_ce": fvg.ce,
            "ce_test_count": len(respected),
            "tests": respected,
            "ce_breached": _is_ce_breached(fvg),
        }

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        breached = any(_is_ce_breached(f) for f in ctx.fvgs if f.tests)
        strict_rules_met = opp1.score >= 65 and not breached
        trade = self.build_trade_parameters(ctx)
        price_at_entry = False
        if trade and ctx.current_price:
            margin = abs(trade.entry - trade.sl) * 0.5
            price_at_entry = abs(ctx.current_price - trade.entry) <= margin
        return compute_verdict(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            opinions=opinions,
            trade=trade,
            strict_rules_met=strict_rules_met,
            price_at_entry=price_at_entry,
            signature=self.build_signature(ctx),
        )
