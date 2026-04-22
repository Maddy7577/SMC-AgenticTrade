"""Strategy #10 — Power of 3 / AMD Intraday Cycle (FR-SP2-10-*).

Distribution phase → VALID/WAIT. Manipulation phase → WAIT max.
Accumulation → NO_TRADE.
Judas family — Judas always representative when both fire.
"""

from __future__ import annotations

import logging

from app.detector.amd_phase import detect_manipulation_event
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

STRATEGY_ID = "10_po3"


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_po3_setup(ctx: CanonicalContext):
    """Return (amd_phase, manip_event, entry_fvg, direction) or None."""
    amd = ctx.amd_phase
    asian_high = ctx.asian_high
    asian_low = ctx.asian_low
    if amd == "Accumulation":
        return amd, None, None, None
    manip = detect_manipulation_event(
        ctx.m5_candles, asian_high or 0.0, asian_low or 0.0, ctx.htf_bias
    ) if asian_high and asian_low else None
    if not manip:
        return amd, None, None, None
    direction = "bullish" if manip["direction"] == "bullish_sweep" else "bearish"
    # Entry: FVG or OB after MSS
    mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
    if not mss:
        return amd, manip, None, direction
    fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested") and f.direction == direction]
    entry_fvg = fvgs[-1] if fvgs else None
    return amd, manip, entry_fvg, direction


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        result = _find_po3_setup(ctx)
        amd, manip, entry_fvg, direction = result
        evidence["amd_phase"] = amd
        evidence["asian_high"] = ctx.asian_high
        evidence["asian_low"] = ctx.asian_low
        reasons.append(f"AMD Phase: {amd}")
        if amd == "Accumulation":
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ Accumulation phase — NO_TRADE"], evidence=evidence)
        if not manip:
            return AgentOpinion(agent_id=self.agent_id, score=30.0, verdict="oppose",
                                reasons=[f"AMD: {amd} — waiting for manipulation event"], evidence=evidence)
        checks: list[bool] = []
        checks.append(True)
        reasons.append(f"✓ Asian range marked: {ctx.asian_low:.5f}–{ctx.asian_high:.5f}")
        checks.append(True)
        reasons.append(f"✓ Manipulation: {manip['direction']} at {manip['manipulation_extreme']:.5f}")
        evidence["manipulation"] = manip
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        checks.append(len(mss) > 0)
        reasons.append("✓ MSS/CHoCH after manipulation" if mss else "✗ no MSS after manipulation")
        # VALID only in Distribution; Manipulation capped at WAIT
        dist_ok = amd == "Distribution"
        if not dist_ok:
            reasons.append(f"phase {amd} — max WAIT")
        passes = sum(checks)
        score = (passes / len(checks)) * 100
        if not dist_ok:
            score = min(score, 64.0)  # ensure max WAIT level
        verdict = "support" if passes >= 3 else ("neutral" if passes == 2 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict,
                            reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 45.0
        reasons: list[str] = []
        result = _find_po3_setup(ctx)
        _, manip, entry_fvg, direction = result
        if manip:
            score += 15
            reasons.append("manipulation event confirmed")
        if entry_fvg:
            score += 10
            reasons.append(f"✓ FVG entry available: CE={entry_fvg.ce:.5f}")
        if ctx.htf_bias != "neutral" and direction:
            if (direction == "bullish" and ctx.htf_bias == "bullish") or (direction == "bearish" and ctx.htf_bias == "bearish"):
                score += 15
                reasons.append("✓ HTF bias aligned")
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
        result = _find_po3_setup(ctx)
        amd, manip, _, _ = result
        if amd == "Accumulation":
            score += 70
            reasons.append("✗ Accumulation phase — NO_TRADE")
        elif not manip:
            score += 35
            reasons.append("✗ no manipulation sweep")
        if not ctx.mss_events:
            score += 25
            reasons.append("✗ no MSS/CHoCH")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread: {ctx.current_spread_pips:.1f} pips")
        result = _find_po3_setup(ctx)
        amd = result[0]
        if amd == "Manipulation":
            score += 10
            reasons.append("Manipulation phase — WAIT max, not VALID")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class PO3Strategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Power of 3 / AMD"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        result = _find_po3_setup(ctx)
        amd, manip, entry_fvg, direction = result
        if amd == "Accumulation" or not manip or not direction:
            return None
        entry = entry_fvg.ce if entry_fvg else None
        if entry is None:
            obs = [ob for ob in ctx.order_blocks if ob.valid and ob.direction == direction]
            if obs:
                entry = round((obs[-1].high + obs[-1].low) / 2, 5)
        if entry is None:
            return None
        manip_extreme = manip["manipulation_extreme"]
        buf = pips_to_price(10)
        asian_high = ctx.asian_high or 0.0
        asian_low = ctx.asian_low or 0.0
        if direction == "bullish":
            sl = round(manip_extreme - buf, 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(asian_high, 5)
            tp2 = round(asian_high + risk, 5)
            trade_dir = "buy"
        else:
            sl = round(manip_extreme + buf, 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(asian_low, 5)
            tp2 = round(asian_low - risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        result = _find_po3_setup(ctx)
        amd, manip, entry_fvg, direction = result
        if not manip or not direction:
            return None
        asian_high = ctx.asian_high or 0.0
        asian_low = ctx.asian_low or 0.0
        entry = entry_fvg.ce if entry_fvg else manip["manipulation_extreme"]
        return f"{STRATEGY_ID}:{direction}:{_rnd(asian_high)}:{_rnd(asian_low)}:{_rnd(entry)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        result = _find_po3_setup(ctx)
        amd, manip, _, direction = result
        return {
            "amd_phase": amd,
            "asian_high": ctx.asian_high,
            "asian_low": ctx.asian_low,
            "manipulation": manip,
            "direction": direction,
        }

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        result = _find_po3_setup(ctx)
        amd = result[0]
        strict_rules_met = opp1.score >= 65 and amd != "Accumulation"
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
