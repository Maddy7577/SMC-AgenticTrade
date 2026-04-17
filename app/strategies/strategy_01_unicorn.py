"""Strategy #1 — Unicorn Model (FR-SP-01-*).

Requires FVG to geometrically overlap Breaker Block with ≥ 10% overlap.
Entry: CE (50%) of overlap region.
SL: beyond Breaker Block extreme + max(10 pips, 0.5× ATR).
TP1: nearest internal liquidity; TP2: next external (target RR ≥ 3).
Preferred session: NY AM Silver Bullet window (IST 20:30–21:30).
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
from app.strategies.scoring import (
    displacement_strength,
    fvg_overlap_pct,
    structure_clarity,
)
from config.instruments import pips_to_price

log = logging.getLogger(__name__)

def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


STRATEGY_ID = "01_unicorn"
MIN_OVERLAP_PCT = 0.10


def _find_fvg_breaker_overlap(ctx: CanonicalContext):
    """Return (fvg, breaker, overlap_pct) or None."""
    breakers = [ob for ob in ctx.order_blocks if ob.kind == "breaker_block"]
    fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
    if not breakers or not fvgs:
        return None
    for fvg in reversed(fvgs):
        for bb in reversed(breakers):
            pct = fvg_overlap_pct(fvg.top, fvg.bottom, bb.high, bb.low)
            if pct >= MIN_OVERLAP_PCT:
                return fvg, bb, pct
    return None


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        checks: list[bool] = []

        # FVG ∩ Breaker ≥ 10%
        overlap_result = _find_fvg_breaker_overlap(ctx)
        overlap_ok = overlap_result is not None
        checks.append(overlap_ok)
        if overlap_ok:
            fvg, bb, pct = overlap_result
            reasons.append(f"✓ FVG ∩ Breaker overlap: {pct:.0%}")
            evidence["overlap_pct"] = round(pct, 3)
            evidence["fvg_midpoint"] = fvg.midpoint
            evidence["bb_range"] = {"high": bb.high, "low": bb.low}
        else:
            reasons.append("✗ no FVG overlapping a Breaker Block (≥ 10%)")

        # Sweep present
        sweeps = ctx.sweeps
        sweep_ok = len(sweeps) > 0
        checks.append(sweep_ok)
        reasons.append("✓ liquidity sweep present" if sweep_ok else "✗ no sweep")

        # MSS
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        mss_ok = len(mss) > 0
        checks.append(mss_ok)
        reasons.append("✓ MSS confirmed" if mss_ok else "✗ no MSS")

        # HTF bias
        bias_ok = ctx.htf_bias != "neutral"
        checks.append(bias_ok)
        reasons.append(f"✓ HTF bias: {ctx.htf_bias}" if bias_ok else "✗ HTF neutral")

        passes = sum(checks)
        score = (passes / len(checks)) * 100
        verdict = "support" if passes >= 3 else ("neutral" if passes == 2 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict, reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 50.0
        reasons: list[str] = []

        # Overlap quality bonus
        overlap_result = _find_fvg_breaker_overlap(ctx)
        if overlap_result:
            _, _, pct = overlap_result
            score += min(pct * 30, 25)  # bonus up to 25 for clean overlap
            reasons.append(f"overlap {pct:.0%} — {'clean' if pct >= 0.3 else 'minimal'}")

        if ctx.m1_candles and ctx.atr_m1:
            ds = displacement_strength(ctx.m1_candles[-1], ctx.atr_m1)
            score += ds * 15
            reasons.append(f"displacement: {ds:.2f}")

        # NY AM Silver Bullet preferred
        if ctx.kill_zone == "silver_bullet_ny_am":
            score += 10
            reasons.append("✓ preferred session: NY AM Silver Bullet")

        sc = structure_clarity(ctx.mss_events, ctx.fvgs)
        score += sc * 10
        reasons.append(f"structure clarity: {sc:.2f}")

        score = round(min(max(score, 0), 100), 1)
        verdict = "support" if score >= 65 else ("neutral" if score >= 45 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk1Agent(BaseAgent):
    agent_id = "risk1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 15.0
        reasons: list[str] = []

        if ctx.m1_candles and ctx.atr_m1:
            close_swings = [
                s for s in ctx.swings
                if abs(s["price"] - (ctx.current_price or ctx.m1_candles[-1]["c"])) < ctx.atr_m1
            ]
            if close_swings:
                score += 25
                reasons.append("opposing liquidity within ATR")

        if ctx.htf_bias == "neutral":
            score += 15
            reasons.append("no clear HTF bias")

        # Overlap below threshold warning
        overlap_result = _find_fvg_breaker_overlap(ctx)
        if not overlap_result:
            score += 20
            reasons.append("FVG∩Breaker overlap not found — pattern weak")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []

        if ctx.kill_zone not in ("silver_bullet_ny_am", "ny_kz", "none"):
            pass  # Unicorn can fire outside NY session, just less preferred
        if ctx.kill_zone == "none":
            reasons.append("outside all session windows — reduced probability")
            score += 10

        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread elevated: {ctx.current_spread_pips:.1f} pips")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class UnicornModelStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Unicorn Model"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        overlap_result = _find_fvg_breaker_overlap(ctx)
        if not overlap_result or not ctx.atr_m1:
            return None
        fvg, bb, _ = overlap_result
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        if not mss:
            return None

        # Entry = CE of the overlap region
        overlap_top = min(fvg.top, bb.high)
        overlap_bot = max(fvg.bottom, bb.low)
        entry = round((overlap_top + overlap_bot) / 2, 5)

        direction = mss[-1].direction
        sl_buffer = max(pips_to_price(10), 0.5 * ctx.atr_m1)

        if direction == "bullish":
            sl = round(bb.low - sl_buffer, 5)
            risk = entry - sl
            tp1 = round(entry + risk, 5)     # nearest internal liquidity proxy
            tp2 = round(entry + 3 * risk, 5)  # external liquidity (RR ≥ 3)
            trade_dir = "buy"
        else:
            sl = round(bb.high + sl_buffer, 5)
            risk = sl - entry
            tp1 = round(entry - risk, 5)
            tp2 = round(entry - 3 * risk, 5)
            trade_dir = "sell"

        if risk <= 0:
            return None
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        overlap_result = _find_fvg_breaker_overlap(ctx)
        if not overlap_result:
            return None
        fvg, bb, _ = overlap_result
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        sweeps = ctx.sweeps
        if not mss or not sweeps:
            return None
        return f"{STRATEGY_ID}:{mss[-1].direction}:{_rnd(sweeps[-1].swept_level)}:{_rnd(mss[-1].broken_level)}:{_rnd(fvg.midpoint)}"

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        strict_rules_met = opp1.score >= 75

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
