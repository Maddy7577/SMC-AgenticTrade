"""Strategy #5 — Nested FVG Stack (FR-SP2-05-*).

Displacement leg ≥5 consecutive same-direction M15 candles with ≥3 FVGs.
First FVG = breakaway_gap; rest = measuring_gap.
Breakaway gap fill → immediate invalidation.
Entry: CE of last FVG in stack.
SL: beyond entry FVG extreme + 5-pip buffer (trails dynamically behind each FVG).
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

STRATEGY_ID = "05_nested_fvg"
_SL_BUFFER_PIPS = 5.0


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_fvg_stack(ctx: CanonicalContext):
    """Return (direction, breakaway_fvg, measuring_fvgs, displacement_candles) or None."""
    m15 = ctx.m15_candles
    if len(m15) < 8:
        return None
    fvgs_m15 = [f for f in ctx.fvgs if f.timeframe == "M15" and f.state in ("formed", "retested", "partially_filled")]
    if len(fvgs_m15) < 3:
        return None

    # Try to find a displacement leg of ≥5 consecutive same-direction candles
    for end_idx in range(len(m15) - 1, 4, -1):
        for start_idx in range(end_idx - 4, max(end_idx - 15, 0), -1):
            segment = m15[start_idx:end_idx + 1]
            if len(segment) < 5:
                continue
            bull_count = sum(1 for c in segment if c["c"] > c["o"])
            bear_count = sum(1 for c in segment if c["c"] < c["o"])
            if bull_count >= 5:
                direction = "bullish"
            elif bear_count >= 5:
                direction = "bearish"
            else:
                continue
            # Find FVGs formed within this displacement window
            seg_t_start = str(segment[0]["t"])
            seg_t_end = str(segment[-1]["t"])
            seg_fvgs = [
                f for f in fvgs_m15
                if f.direction == direction and f.c1_t >= seg_t_start and f.c3_t <= seg_t_end
            ]
            if len(seg_fvgs) >= 3:
                seg_fvgs.sort(key=lambda f: f.c1_t)
                breakaway = seg_fvgs[0]
                measuring = seg_fvgs[1:]
                # Breakaway not fully filled
                if breakaway.state == "fully_filled":
                    continue
                return direction, breakaway, measuring, segment
    return None


def _m15_fvg_in_h4_fvg(m15_fvg, ctx: CanonicalContext) -> bool:
    """Check if the M15 FVG is contained within an H4 FVG."""
    h4_fvgs = [f for f in ctx.fvgs if f.timeframe == "H4" and f.state in ("formed", "retested")]
    for h4f in h4_fvgs:
        if m15_fvg.bottom >= h4f.bottom and m15_fvg.top <= h4f.top:
            return True
    return False


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        stack = _find_fvg_stack(ctx)
        if not stack:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no FVG stack found"], evidence={})
        direction, breakaway, measuring, seg = stack
        checks: list[bool] = []

        # ≥5 consecutive candles
        checks.append(True)
        reasons.append(f"✓ displacement: {len(seg)} candles, direction: {direction}")
        evidence["displacement_count"] = len(seg)
        evidence["direction"] = direction

        # ≥3 FVGs
        total_fvgs = 1 + len(measuring)
        checks.append(total_fvgs >= 3)
        reasons.append(f"✓ FVG stack: {total_fvgs} gaps" if total_fvgs >= 3 else f"✗ only {total_fvgs} FVGs")

        # Breakaway not filled
        checks.append(breakaway.state != "fully_filled")
        reasons.append("✓ breakaway gap intact" if breakaway.state != "fully_filled" else "✗ breakaway gap filled")
        evidence["breakaway_ce"] = breakaway.ce
        evidence["breakaway_state"] = breakaway.state

        # HTF bias alignment
        htf_ok = ctx.htf_bias != "neutral" and (
            (direction == "bullish" and ctx.htf_bias == "bullish") or
            (direction == "bearish" and ctx.htf_bias == "bearish")
        )
        checks.append(htf_ok)
        reasons.append(f"✓ HTF bias aligned: {ctx.htf_bias}" if htf_ok else f"✗ HTF bias: {ctx.htf_bias}")

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
        stack = _find_fvg_stack(ctx)
        if not stack:
            return AgentOpinion(agent_id=self.agent_id, score=35.0, verdict="neutral",
                                reasons=["no stack found"], evidence={})
        direction, breakaway, measuring, seg = stack
        last_fvg = measuring[-1] if measuring else breakaway
        # M15 FVG inside H4 FVG
        if _m15_fvg_in_h4_fvg(last_fvg, ctx):
            score += 20
            reasons.append("✓ M15 FVG contained within H4 FVG zone")
        else:
            reasons.append("M15 FVG not nested in H4 FVG — reduced quality")
        # Kill zone bonus
        if ctx.kill_zone in ("london_kz", "ny_kz", "silver_bullet_ny_am"):
            score += 15
            reasons.append(f"✓ Kill Zone active: {ctx.kill_zone}")
        else:
            score -= 10
            reasons.append(f"outside kill zone: {ctx.kill_zone}")
        score = round(min(max(score, 0), 100), 1)
        verdict = "support" if score >= 65 else ("neutral" if score >= 45 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk1Agent(BaseAgent):
    agent_id = "risk1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 15.0
        reasons: list[str] = []
        stack = _find_fvg_stack(ctx)
        if stack:
            direction, breakaway, measuring, _ = stack
            if breakaway.state == "fully_filled":
                score += 60
                reasons.append("✗ breakaway gap filled — pattern invalidated")
            if ctx.htf_bias != "neutral" and (
                (direction == "bullish" and ctx.htf_bias == "bearish") or
                (direction == "bearish" and ctx.htf_bias == "bullish")
            ):
                score += 25
                reasons.append("HTF bias opposes trade direction")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        if ctx.kill_zone == "none":
            score += 20
            reasons.append("outside all session windows — Asian stack penalty")
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread elevated: {ctx.current_spread_pips:.1f} pips")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class NestedFVGStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Nested FVG Stack"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        stack = _find_fvg_stack(ctx)
        if not stack:
            return None
        direction, breakaway, measuring, _ = stack
        if breakaway.state == "fully_filled":
            return None
        last_fvg = measuring[-1] if measuring else breakaway
        buf = pips_to_price(_SL_BUFFER_PIPS)
        entry = last_fvg.ce
        if direction == "bullish":
            sl = round(last_fvg.bottom - buf, 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(entry + 2 * risk, 5)
            tp2 = round(entry + 3 * risk, 5)
            trade_dir = "buy"
        else:
            sl = round(last_fvg.top + buf, 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(entry - 2 * risk, 5)
            tp2 = round(entry - 3 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        stack = _find_fvg_stack(ctx)
        if not stack:
            return None
        direction, breakaway, measuring, _ = stack
        last_fvg = measuring[-1] if measuring else breakaway
        return f"{STRATEGY_ID}:{direction}:{_rnd(breakaway.ce)}:{_rnd(last_fvg.ce)}:{_rnd(last_fvg.ce)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        stack = _find_fvg_stack(ctx)
        if not stack:
            return {}
        direction, breakaway, measuring, seg = stack
        return {
            "direction": direction,
            "displacement_candles": len(seg),
            "breakaway_fvg": {"ce": breakaway.ce, "top": breakaway.top, "bottom": breakaway.bottom, "state": breakaway.state},
            "measuring_fvgs": [{"ce": f.ce, "top": f.top, "bottom": f.bottom} for f in measuring],
        }

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
