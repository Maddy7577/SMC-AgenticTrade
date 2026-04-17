"""Strategy #3 — Confirmation Model (FR-SP-03-*).

Five mandatory conditions (FR-SP-03-01):
  1. Liquidity taken (sweep present)
  2. MSS present after sweep
  3. FVG present in displacement zone
  4. HTF bias aligned
  5. Price in Premium/Discount aligned with direction

Entry: FVG boundary or CE (FR-SP-03-02)
SL: beyond swept wick + 0.75× ATR (FR-SP-03-03)
TP1: entry ± 2× risk; TP2: opposing H4 liquidity (FR-SP-03-04)
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
from app.strategies.scoring import displacement_strength, rr_score, structure_clarity, wick_quality
from config.instruments import pips_to_price, price_to_pips
from config.settings import RR_FLOOR

log = logging.getLogger(__name__)

STRATEGY_ID = "03_confirmation"


class _Opp1Agent(BaseAgent):
    """Strict rule compliance — binary pass/fail on each of the 5 conditions (FR-S-04)."""

    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        checks: list[bool] = []

        # 1. Liquidity sweep
        sweeps = [s for s in ctx.sweeps if s.index >= len(ctx.m1_candles) - 10]
        sweep_ok = len(sweeps) > 0
        checks.append(sweep_ok)
        if sweep_ok:
            reasons.append("✓ liquidity sweep detected")
            evidence["sweep"] = {"level": sweeps[-1].swept_level, "type": sweeps[-1].level_type}
        else:
            reasons.append("✗ no recent liquidity sweep")

        # 2. MSS present
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        mss_ok = len(mss) > 0
        checks.append(mss_ok)
        if mss_ok:
            reasons.append("✓ MSS confirmed")
            evidence["mss"] = {"level": mss[-1].broken_level, "direction": mss[-1].direction}
        else:
            reasons.append("✗ no MSS after sweep")

        # 3. FVG present
        formed_fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        fvg_ok = len(formed_fvgs) > 0
        checks.append(fvg_ok)
        if fvg_ok:
            reasons.append("✓ FVG present")
            evidence["fvg"] = {"top": formed_fvgs[-1].top, "bottom": formed_fvgs[-1].bottom}
        else:
            reasons.append("✗ no valid FVG")

        # 4. HTF bias
        bias_ok = ctx.htf_bias != "neutral"
        checks.append(bias_ok)
        if bias_ok:
            reasons.append(f"✓ HTF bias: {ctx.htf_bias}")
        else:
            reasons.append("✗ HTF bias neutral")

        # 5. Premium/Discount alignment
        pd_ok = False
        if ctx.pd_zone and ctx.current_price and ctx.htf_bias != "neutral":
            label = ctx.pd_zone.classify(ctx.current_price)
            if ctx.htf_bias == "bullish" and label == "discount":
                pd_ok = True
            elif ctx.htf_bias == "bearish" and label == "premium":
                pd_ok = True
        checks.append(pd_ok)
        if pd_ok:
            reasons.append("✓ price in correct premium/discount zone")
        else:
            reasons.append("✗ price not in aligned P/D zone")

        passes = sum(checks)
        score = (passes / len(checks)) * 90 + (10 if passes == len(checks) else 0)
        verdict = "support" if passes >= 4 else ("neutral" if passes == 3 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict, reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    """Setup quality scoring (FR-S-05)."""

    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        score = 50.0

        # Displacement strength
        if ctx.m1_candles and ctx.atr_m1:
            ds = displacement_strength(ctx.m1_candles[-1], ctx.atr_m1)
            score += ds * 20
            reasons.append(f"displacement strength: {ds:.2f}")

        # FVG quality
        good_fvgs = [f for f in ctx.fvgs if f.state == "formed" and f.size_pips >= 8]
        if good_fvgs:
            score += 15
            reasons.append(f"clean FVG ({good_fvgs[-1].size_pips:.1f} pips)")
        else:
            score -= 10
            reasons.append("FVG small or retested")

        # Structure clarity
        sc = structure_clarity(ctx.mss_events, ctx.fvgs)
        score += sc * 15
        reasons.append(f"structure clarity: {sc:.2f}")

        # SMT confluence bonus
        if ctx.smt_divergence != "none":
            score += 5
            reasons.append(f"SMT divergence: {ctx.smt_divergence}")

        score = round(min(max(score, 0), 100), 1)
        verdict = "support" if score >= 65 else ("neutral" if score >= 45 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence=evidence)


class _Risk1Agent(BaseAgent):
    """Technical risk (FR-S-06)."""

    agent_id = "risk1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        score = 20.0  # start low — risk agent scores are inverted (low = less risk)

        # Opposing liquidity nearby
        if ctx.m1_candles and ctx.atr_m1:
            # Check if there are swing points within 1× ATR of current price
            close_swings = [
                s for s in ctx.swings
                if abs(s["price"] - (ctx.current_price or ctx.m1_candles[-1]["c"])) < ctx.atr_m1
            ]
            if close_swings:
                score += 30
                reasons.append(f"opposing liquidity within ATR ({len(close_swings)} levels)")
            else:
                reasons.append("no opposing liquidity nearby")

        # HTF conflict
        if ctx.htf_bias == "neutral":
            score += 20
            reasons.append("HTF bias neutral — unclear trend")

        # Weak displacement
        if ctx.m1_candles and ctx.atr_m1:
            ds = displacement_strength(ctx.m1_candles[-1], ctx.atr_m1)
            if ds < 0.4:
                score += 15
                reasons.append("weak displacement candle")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    """Contextual risk (FR-S-07)."""

    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        score = 10.0

        # Kill zone check — confirmation model prefers to be in a session
        if ctx.kill_zone == "none":
            score += 25
            reasons.append("outside active kill zone")
        else:
            reasons.append(f"in kill zone: {ctx.kill_zone}")

        # Spread state
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"high spread: {ctx.current_spread_pips:.1f} pips")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class ConfirmationModelStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Confirmation Model"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        sweeps = [s for s in ctx.sweeps if s.index >= len(ctx.m1_candles) - 10]
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]

        if not sweeps or not fvgs or not mss or not ctx.atr_m1:
            return None

        sweep = sweeps[-1]
        fvg = fvgs[-1]
        m = mss[-1]
        direction = m.direction  # "bullish" → buy, "bearish" → sell

        entry = fvg.midpoint if fvg.midpoint else fvg.bottom
        atr_buf = 0.75 * ctx.atr_m1

        if direction == "bullish":
            sl = sweep.wick_extreme - atr_buf
            risk = entry - sl
            tp1 = entry + 2 * risk
            tp2 = entry + 4 * risk  # approximate H4 opposing liquidity
            trade_dir = "buy"
        else:
            sl = sweep.wick_extreme + atr_buf
            risk = sl - entry
            tp1 = entry - 2 * risk
            tp2 = entry - 4 * risk
            trade_dir = "sell"

        if risk <= 0:
            return None

        return TradeParameters(
            direction=trade_dir,
            entry=round(entry, 5),
            sl=round(sl, 5),
            tp1=round(tp1, 5),
            tp2=round(tp2, 5),
        )

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        sweeps = [s for s in ctx.sweeps if s.index >= len(ctx.m1_candles) - 10]
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        if not sweeps or not mss or not fvgs:
            return None
        # Round to 5-pip buckets
        rnd = lambda p: round(round(p / 0.0005) * 0.0005, 5)
        direction = mss[-1].direction
        return f"{STRATEGY_ID}:{direction}:{rnd(sweeps[-1].swept_level)}:{rnd(mss[-1].broken_level)}:{rnd(fvgs[-1].midpoint)}"

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        strict_rules_met = opp1.score >= 72  # 4/5 conditions = 72%

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
