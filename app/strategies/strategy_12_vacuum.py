"""Strategy #12 — Vacuum Block (FR-SP2-12-*).

Open price gap (H1). 50% CE = primary target. LTF MSS near CE = entry trigger.
Fully filled gap → strict_rules_met = False → NO_TRADE.
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
from config.instruments import pips_to_price, price_to_pips

log = logging.getLogger(__name__)

STRATEGY_ID = "12_vacuum"
_GAP_SCORE = {"weekend_gap": 80, "news_gap": 65, "session_gap": 50}


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_vacuum_setup(ctx: CanonicalContext):
    """Return (gap, direction) or None."""
    gaps = [g for g in ctx.active_gaps if not g["fully_filled"]]
    if not gaps:
        return None
    current = ctx.current_price or (ctx.m1_candles[-1]["c"] if ctx.m1_candles else None)
    if current is None:
        return None
    # Pick gap closest to current price
    best = min(gaps, key=lambda g: abs(g["ce"] - current))
    direction = "bullish" if current < best["ce"] else "bearish"
    return best, direction


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        setup = _find_vacuum_setup(ctx)
        if not setup:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no open gap found"], evidence={})
        gap, direction = setup
        checks: list[bool] = []
        checks.append(not gap["fully_filled"])
        reasons.append(f"✓ gap open: {gap['gap_type']} — {gap['bottom']:.5f}–{gap['top']:.5f}")
        evidence["gap"] = {k: gap[k] for k in ("gap_type", "top", "bottom", "ce", "filled_pct")}
        # LTF MSS near CE
        ce = gap["ce"]
        mss_near = [m for m in ctx.mss_events
                    if m.index >= len(ctx.m1_candles) - 20
                    and price_to_pips(abs(m.broken_level - ce)) <= 10]
        checks.append(len(mss_near) > 0)
        reasons.append("✓ LTF MSS near gap CE" if mss_near else "✗ no LTF MSS near CE")
        evidence["mss_near_ce"] = len(mss_near) > 0
        passes = sum(checks)
        score = (passes / len(checks)) * 100
        verdict = "support" if passes >= 2 else ("neutral" if passes == 1 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict,
                            reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 40.0
        reasons: list[str] = []
        setup = _find_vacuum_setup(ctx)
        if setup:
            gap, _ = setup
            type_score = _GAP_SCORE.get(gap["gap_type"], 50)
            score = type_score
            reasons.append(f"gap type: {gap['gap_type']} → base score {type_score}")
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
        setup = _find_vacuum_setup(ctx)
        if setup:
            gap, _ = setup
            if gap["fully_filled"]:
                score += 70
                reasons.append("✗ gap fully filled — strict_rules_met=False")
            if not any(m.index >= len(ctx.m1_candles) - 20 for m in ctx.mss_events):
                score += 25
                reasons.append("✗ no MSS — oppose")
        else:
            score += 40
            reasons.append("no open gap found")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        if ctx.kill_zone not in ("london_kz", "ny_kz", "silver_bullet_ny_am"):
            score += 20
            reasons.append("outside London/NY KZ — reduced probability")
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread elevated: {ctx.current_spread_pips:.1f} pips")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class VacuumBlockStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Vacuum Block"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        setup = _find_vacuum_setup(ctx)
        if not setup:
            return None
        gap, direction = setup
        if gap["fully_filled"]:
            return None
        entry = gap["ce"]
        if direction == "bullish":
            sl = round(gap["bottom"] - pips_to_price(5), 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(entry + 2 * risk, 5)
            tp2 = round(entry + 3 * risk, 5)
            trade_dir = "buy"
        else:
            sl = round(gap["top"] + pips_to_price(5), 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(entry - 2 * risk, 5)
            tp2 = round(entry - 3 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        setup = _find_vacuum_setup(ctx)
        if not setup:
            return None
        gap, direction = setup
        return f"{STRATEGY_ID}:{direction}:{_rnd(gap['bottom'])}:{_rnd(gap['top'])}:{_rnd(gap['ce'])}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        setup = _find_vacuum_setup(ctx)
        if not setup:
            return {}
        gap, direction = setup
        return {
            "gap": {k: gap[k] for k in ("gap_type", "top", "bottom", "ce", "filled_pct", "fully_filled")},
            "direction": direction,
        }

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        setup = _find_vacuum_setup(ctx)
        gap_filled = setup and setup[0]["fully_filled"]
        strict_rules_met = opp1.score >= 75 and not gap_filled
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
