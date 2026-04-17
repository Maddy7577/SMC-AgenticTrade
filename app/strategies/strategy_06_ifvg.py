"""Strategy #6 — Inverse FVG (iFVG) (FR-SP-06-*).

Requires candle BODY (not wick) to close through the entire original FVG.
Requires prior liquidity sweep at a key level.
SMT Divergence is strongly-weighted confluence (not hard requirement).
Preferred window: NY session onward (IST 17:30+).
Entry at iFVG boundary or CE; SL at wider of (iFVG zone + 10 pips) or (beyond sweep wick).
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

STRATEGY_ID = "06_ifvg"

_NY_WINDOWS = {"ny_kz", "silver_bullet_ny_am", "silver_bullet_ny_pm"}


def _find_inverted_fvg(ctx: CanonicalContext):
    """Return the most recent inverted FVG, or None."""
    inv = [f for f in ctx.fvgs if f.state == "inverted"]
    return inv[-1] if inv else None


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        checks: list[bool] = []

        # iFVG present (body close through FVG) — FR-SP-06-01
        ifvg = _find_inverted_fvg(ctx)
        ifvg_ok = ifvg is not None
        checks.append(ifvg_ok)
        if ifvg_ok:
            reasons.append("✓ iFVG detected (body closed through FVG)")
            evidence["ifvg"] = {"top": ifvg.top, "bottom": ifvg.bottom, "direction": ifvg.direction}
        else:
            reasons.append("✗ no iFVG (no FVG with body-close inversion)")

        # Prior liquidity sweep — FR-SP-06-02
        sweeps = ctx.sweeps
        sweep_ok = len(sweeps) > 0
        checks.append(sweep_ok)
        reasons.append("✓ prior sweep present" if sweep_ok else "✗ no prior liquidity sweep")

        # MSS
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        mss_ok = len(mss) > 0
        checks.append(mss_ok)
        reasons.append("✓ MSS present" if mss_ok else "✗ no MSS")

        passes = sum(checks)
        score = (passes / len(checks)) * 100
        verdict = "support" if passes >= 2 else ("neutral" if passes == 1 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict, reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 50.0
        reasons: list[str] = []

        # SMT divergence — strongly weighted (FR-SP-06-03)
        if ctx.smt_divergence != "none":
            score += 20
            reasons.append(f"✓ SMT divergence: {ctx.smt_divergence} (strong confluence)")
        else:
            score -= 10
            reasons.append("no SMT divergence")

        if ctx.m1_candles and ctx.atr_m1:
            ds = displacement_strength(ctx.m1_candles[-1], ctx.atr_m1)
            score += ds * 15
            reasons.append(f"displacement: {ds:.2f}")

        # NY session preference
        if ctx.kill_zone in _NY_WINDOWS:
            score += 10
            reasons.append(f"✓ preferred NY window: {ctx.kill_zone}")

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

        # Penalise if SMT opposes direction
        if ctx.smt_divergence != "none":
            mss = ctx.mss_events
            if mss and ctx.smt_divergence != mss[-1].direction:
                score += 20  # plan §Ambiguities #3: SMT-opposed = Risk1 +15
                reasons.append(f"SMT opposes MSS direction: {ctx.smt_divergence} vs {mss[-1].direction}")

        if ctx.m1_candles and ctx.atr_m1:
            close_swings = [
                s for s in ctx.swings
                if abs(s["price"] - (ctx.current_price or ctx.m1_candles[-1]["c"])) < ctx.atr_m1
            ]
            if close_swings:
                score += 20
                reasons.append("opposing liquidity within ATR")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []

        # Outside NY session is a soft concern for iFVG
        if ctx.kill_zone not in _NY_WINDOWS and ctx.kill_zone != "none":
            score += 5
            reasons.append(f"suboptimal session for iFVG: {ctx.kill_zone}")

        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread elevated: {ctx.current_spread_pips:.1f} pips")

        if ctx.htf_bias == "neutral":
            score += 15
            reasons.append("no HTF bias confirmation")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class IFVGStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Inverse FVG (iFVG)"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        ifvg = _find_inverted_fvg(ctx)
        if not ifvg or not ctx.sweeps or not ctx.atr_m1:
            return None
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        if not mss:
            return None

        sweep = ctx.sweeps[-1]
        m = mss[-1]
        entry = ifvg.midpoint

        sl_from_ifvg = pips_to_price(10)
        sl_from_sweep = abs(sweep.wick_extreme - entry)

        if m.direction == "bullish":
            sl = round(min(ifvg.bottom - sl_from_ifvg, sweep.wick_extreme), 5)
            risk = entry - sl
            tp1 = round(entry + 2 * risk, 5)
            direction = "buy"
        else:
            sl = round(max(ifvg.top + sl_from_ifvg, sweep.wick_extreme), 5)
            risk = sl - entry
            tp1 = round(entry - 2 * risk, 5)
            direction = "sell"

        if risk <= 0:
            return None
        return TradeParameters(direction=direction, entry=round(entry, 5), sl=sl, tp1=tp1)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        ifvg = _find_inverted_fvg(ctx)
        if not ifvg or not ctx.sweeps:
            return None
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        if not mss:
            return None
        rnd = lambda p: round(round(p / 0.0005) * 0.0005, 5)
        return f"{STRATEGY_ID}:{mss[-1].direction}:{rnd(ctx.sweeps[-1].swept_level)}:{rnd(mss[-1].broken_level)}:{rnd(ifvg.midpoint)}"

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        strict_rules_met = opp1.score >= 67  # 2/3 hard conditions

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
