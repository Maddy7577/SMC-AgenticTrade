"""Strategy #2 — Judas Swing (FR-SP-02-*).

Asian session H/L marked (IST 05:30–12:30).
False breakout of Asian range during London KZ (IST 12:30–15:30) against daily bias.
Entry: FVG or OB from displacement after MSS.
TP1: opposite side of Asian range; TP2: PDH/PDL.
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
from app.strategies.scoring import displacement_strength, structure_clarity
from config.instruments import pips_to_price

log = logging.getLogger(__name__)

def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


STRATEGY_ID = "02_judas"


def _asian_range_valid(ctx: CanonicalContext) -> bool:
    return ctx.asian_high is not None and ctx.asian_low is not None


def _in_london_kz(ctx: CanonicalContext) -> bool:
    return ctx.kill_zone == "london_kz"


def _false_breakout_direction(ctx: CanonicalContext) -> str | None:
    """Detect if price has swept Asian range contrary to HTF bias."""
    if not _asian_range_valid(ctx) or not ctx.m1_candles:
        return None
    last = ctx.m1_candles[-1]
    # Bearish Judas: price sweeps above Asian high then reverses → bias should be bearish
    if last["h"] > ctx.asian_high and last["c"] < ctx.asian_high and ctx.htf_bias == "bearish":
        return "bearish"
    # Bullish Judas: price sweeps below Asian low then reverses → bias should be bullish
    if last["l"] < ctx.asian_low and last["c"] > ctx.asian_low and ctx.htf_bias == "bullish":
        return "bullish"
    return None


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        checks: list[bool] = []

        # Asian range established
        ar_ok = _asian_range_valid(ctx)
        checks.append(ar_ok)
        reasons.append("✓ Asian range established" if ar_ok else "✗ no Asian range today")

        # London KZ active
        london_ok = _in_london_kz(ctx)
        checks.append(london_ok)
        reasons.append("✓ London KZ active" if london_ok else f"✗ not in London KZ ({ctx.kill_zone})")

        # False breakout detected
        fb_dir = _false_breakout_direction(ctx)
        fb_ok = fb_dir is not None
        checks.append(fb_ok)
        if fb_ok:
            reasons.append(f"✓ false breakout: {fb_dir}")
            evidence["false_breakout_direction"] = fb_dir
        else:
            reasons.append("✗ no false breakout of Asian range")

        # MSS on M1/M5 after sweep (FR-SP-02-03)
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 10]
        mss_ok = len(mss) > 0
        checks.append(mss_ok)
        reasons.append("✓ MSS confirmed" if mss_ok else "✗ no MSS after sweep")

        passes = sum(checks)
        score = (passes / len(checks)) * 100
        verdict = "support" if passes >= 3 else ("neutral" if passes == 2 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict, reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 50.0
        reasons: list[str] = []

        if ctx.m1_candles and ctx.atr_m1:
            ds = displacement_strength(ctx.m1_candles[-1], ctx.atr_m1)
            score += ds * 20
            reasons.append(f"displacement strength: {ds:.2f}")

        # Asian range size — larger range = cleaner Judas
        if ctx.asian_high and ctx.asian_low:
            from config.instruments import price_to_pips
            range_pips = price_to_pips(ctx.asian_high - ctx.asian_low)
            if range_pips >= 15:
                score += 15
                reasons.append(f"Asian range {range_pips:.0f} pips (clean)")
            elif range_pips < 8:
                score -= 15
                reasons.append(f"Asian range too narrow ({range_pips:.0f} pips)")

        sc = structure_clarity(ctx.mss_events, ctx.fvgs)
        score += sc * 15
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
            score += 20
            reasons.append("unclear HTF bias")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []

        if not _in_london_kz(ctx):
            score += 35
            reasons.append("outside London KZ — Judas requires London window")

        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 15
            reasons.append(f"elevated spread: {ctx.current_spread_pips:.1f} pips")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class JudasSwingStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Judas Swing"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        if not _asian_range_valid(ctx) or not ctx.atr_m1:
            return None
        fb_dir = _false_breakout_direction(ctx)
        if not fb_dir:
            return None
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        sweeps = ctx.sweeps
        if not sweeps:
            return None
        sweep = sweeps[-1]

        if fb_dir == "bullish":
            entry = fvgs[-1].midpoint if fvgs else ctx.asian_low
            sl = sweep.wick_extreme - pips_to_price(15)
            tp1 = ctx.asian_high  # opposite side of Asian range
            tp2 = ctx.asian_high + pips_to_price(20)  # approximate PDH
            direction = "buy"
        else:
            entry = fvgs[-1].midpoint if fvgs else ctx.asian_high
            sl = sweep.wick_extreme + pips_to_price(15)
            tp1 = ctx.asian_low
            tp2 = ctx.asian_low - pips_to_price(20)
            direction = "sell"

        risk = abs(entry - sl)
        if risk <= 0:
            return None
        return TradeParameters(direction=direction, entry=round(entry, 5), sl=round(sl, 5), tp1=round(tp1, 5), tp2=round(tp2, 5))

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        if not _asian_range_valid(ctx):
            return None
        fb_dir = _false_breakout_direction(ctx)
        if not fb_dir:
            return None
        mss = ctx.mss_events
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        if not mss or not fvgs:
            return None
        return f"{STRATEGY_ID}:{fb_dir}:{_rnd(ctx.asian_high)}:{_rnd(mss[-1].broken_level)}:{_rnd(fvgs[-1].midpoint)}"

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
