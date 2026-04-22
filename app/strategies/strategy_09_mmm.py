"""Strategy #9 — Market Maker Model (FR-SP2-09-*).

Only active during Phase 3 (Smart Money Reversal).
Phases 1/2/4 are observation-only (NO_TRADE).
Confirmation ancestry family.
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

STRATEGY_ID = "09_mmm"
_PHASE_NAMES = {0: "Unknown", 1: "Consolidation", 2: "Sell Program", 3: "Smart Money Reversal", 4: "Buy Program"}


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_mmm_setup(ctx: CanonicalContext):
    """Return (phase, consol_low, consol_high, direction, entry_fvg) or None."""
    from app.detector.mmm_phase import detect_mmm_phase
    mmm = detect_mmm_phase(ctx.h4_candles, ctx.d_candles)
    phase = mmm["phase"]
    consol_low = mmm["consolidation_low"]
    consol_high = mmm["consolidation_high"]
    direction = mmm["direction"]
    if phase != 3 or not direction:
        return phase, consol_low, consol_high, direction, None
    # Find entry FVG after MSS
    mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 30]
    if not mss:
        return phase, consol_low, consol_high, direction, None
    entry_fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested") and f.direction == direction]
    entry_fvg = entry_fvgs[-1] if entry_fvgs else None
    return phase, consol_low, consol_high, direction, entry_fvg


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        result = _find_mmm_setup(ctx)
        phase, consol_low, consol_high, direction, entry_fvg = result
        evidence["phase"] = phase
        evidence["phase_name"] = _PHASE_NAMES.get(phase, "Unknown")
        reasons.append(f"MMM Phase: {phase} — {_PHASE_NAMES.get(phase, 'Unknown')}")
        if consol_low and consol_high:
            evidence["consolidation"] = {"low": consol_low, "high": consol_high}
            reasons.append(f"consolidation zone: {consol_low:.5f}–{consol_high:.5f}")
        if phase != 3:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=reasons, evidence=evidence)
        checks: list[bool] = []
        checks.append(True)  # phase 3 confirmed
        reasons.append("✓ Phase 3 — Smart Money Reversal active")
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 30]
        checks.append(len(mss) > 0)
        reasons.append("✓ MSS at HTF PD array" if mss else "✗ no MSS")
        checks.append(entry_fvg is not None)
        reasons.append(f"✓ FVG after MSS: CE={entry_fvg.ce:.5f}" if entry_fvg else "✗ no FVG after MSS")
        htf_ok = (direction == "bullish" and ctx.htf_bias == "bullish") or (direction == "bearish" and ctx.htf_bias == "bearish") or ctx.htf_bias == "neutral"
        checks.append(htf_ok)
        reasons.append(f"HTF bias: {ctx.htf_bias}")
        passes = sum(checks)
        score = (passes / len(checks)) * 100
        verdict = "support" if passes >= 3 else ("neutral" if passes == 2 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict,
                            reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 45.0
        reasons: list[str] = []
        result = _find_mmm_setup(ctx)
        phase, consol_low, consol_high, direction, _ = result
        if phase == 3:
            score += 25
            reasons.append("Phase 3 quality bonus")
            if consol_low and consol_high:
                span = consol_high - consol_low
                if span < 0.01:  # tight consolidation = clearer
                    score += 10
                    reasons.append("tight consolidation zone")
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
        result = _find_mmm_setup(ctx)
        phase = result[0]
        if phase != 3:
            score += 70
            reasons.append(f"✗ Phase {phase} — NOT Phase 3 → NO_TRADE")
        elif result[3] is None:
            score += 30
            reasons.append("no consolidation direction")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={"phase": phase})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread: {ctx.current_spread_pips:.1f} pips")
        # Check if Daily range is too low (thin day)
        if ctx.d_candles:
            last_d = ctx.d_candles[-1]
            daily_range = last_d["h"] - last_d["l"]
            if daily_range < 0.003:
                score += 15
                reasons.append("thin daily range — low probability day")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class MMMStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Market Maker Model"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        result = _find_mmm_setup(ctx)
        phase, consol_low, consol_high, direction, entry_fvg = result
        if phase != 3 or not direction or entry_fvg is None:
            return None
        entry = entry_fvg.ce
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 30]
        if not mss:
            return None
        mss_extreme = mss[-1].broken_level
        if direction == "bullish":
            sl = round(mss_extreme - pips_to_price(20), 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(consol_low if consol_low else entry + 2 * risk, 5)
            tp2 = round(consol_high if consol_high else entry + 3 * risk, 5)
            tp3 = round(entry + 4 * risk, 5)
            trade_dir = "buy"
        else:
            sl = round(mss_extreme + pips_to_price(20), 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(consol_high if consol_high else entry - 2 * risk, 5)
            tp2 = round(consol_low if consol_low else entry - 3 * risk, 5)
            tp3 = round(entry - 4 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        result = _find_mmm_setup(ctx)
        phase, consol_low, consol_high, direction, entry_fvg = result
        if phase != 3 or not direction:
            return None
        entry = entry_fvg.ce if entry_fvg else 0.0
        return f"{STRATEGY_ID}:{direction}:{_rnd(consol_low or 0)}:{_rnd(consol_high or 0)}:{_rnd(entry)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        result = _find_mmm_setup(ctx)
        phase, consol_low, consol_high, direction, _ = result
        return {
            "phase": phase,
            "phase_name": _PHASE_NAMES.get(phase, "Unknown"),
            "consolidation": {"low": consol_low, "high": consol_high} if consol_low and consol_high else None,
            "consolidation_low": consol_low,
            "consolidation_high": consol_high,
            "direction": direction,
        }

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        result = _find_mmm_setup(ctx)
        phase = result[0]
        strict_rules_met = opp1.score >= 75 and phase == 3
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
