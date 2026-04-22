"""Strategy #7 — OTE + FVG Confluence (FR-SP2-07-*).

H4 impulse ≥3× ATR; M15 FVG physically overlaps OTE band 0.618–0.786.
Prior sweep required. Entry: 0.705 fib. SL: 100% fib + 15 pips.
TP1=0%, TP2=−0.27 ext, TP3=−0.62 ext.
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

STRATEGY_ID = "07_ote_fvg"
_SL_BUFFER_PIPS = 15.0


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_ote_fvg_setup(ctx: CanonicalContext):
    """Return (fib_levels, ote_fvg, direction, overlap_pips) or None."""
    if not ctx.fib_levels or not ctx.atr_h4:
        return None
    fib = ctx.fib_levels
    if 0.618 not in fib or 0.786 not in fib or 0.705 not in fib:
        return None
    ote_low = min(fib[0.618], fib[0.786])
    ote_high = max(fib[0.618], fib[0.786])

    m15_fvgs = [f for f in ctx.fvgs if f.timeframe == "M15" and f.state in ("formed", "retested")]
    if not m15_fvgs:
        return None

    # Determine direction from fib context (0.0 < 1.0 for bullish)
    direction = "bullish" if fib.get(0.0, 0) < fib.get(1.0, 1) else "bearish"

    for fvg in reversed(m15_fvgs):
        if fvg.direction != direction:
            continue
        # Physical overlap with OTE band (not just proximity)
        overlap_top = min(fvg.top, ote_high)
        overlap_bot = max(fvg.bottom, ote_low)
        if overlap_top <= overlap_bot:
            continue
        overlap_pips = price_to_pips(overlap_top - overlap_bot)
        if overlap_pips <= 0:
            continue
        return fib, fvg, direction, overlap_pips
    return None


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        setup = _find_ote_fvg_setup(ctx)
        if not setup:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no OTE+FVG overlap found"], evidence={})
        fib, ote_fvg, direction, overlap_pips = setup
        checks: list[bool] = []

        # H4 impulse ≥3× ATR verified (fib_levels only computed when impulse qualifies)
        checks.append(True)
        reasons.append("✓ H4 impulse ≥3× ATR (fib levels present)")

        # FVG overlaps OTE
        checks.append(overlap_pips > 0)
        reasons.append(f"✓ FVG overlaps OTE band: {overlap_pips:.1f} pips")
        evidence["overlap_pips"] = round(overlap_pips, 1)
        evidence["ote_low"] = min(fib[0.618], fib[0.786])
        evidence["ote_high"] = max(fib[0.618], fib[0.786])
        evidence["fvg_top"] = ote_fvg.top
        evidence["fvg_bottom"] = ote_fvg.bottom
        evidence["entry_705"] = fib[0.705]

        # Prior sweep
        sweep_ok = len(ctx.sweeps) > 0
        checks.append(sweep_ok)
        reasons.append("✓ prior sweep present" if sweep_ok else "✗ no sweep before impulse")

        # HTF bias
        bias_ok = (direction == "bullish" and ctx.htf_bias == "bullish") or \
                  (direction == "bearish" and ctx.htf_bias == "bearish") or \
                  ctx.htf_bias == "neutral"
        checks.append(bias_ok)
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
        setup = _find_ote_fvg_setup(ctx)
        if setup:
            _, _, direction, overlap_pips = setup
            score += min(overlap_pips * 2, 20)
            reasons.append(f"OTE overlap: {overlap_pips:.1f} pips quality bonus")
            # OB within OTE zone bonus
            fib = ctx.fib_levels
            ote_low = min(fib.get(0.618, 0), fib.get(0.786, 0))
            ote_high = max(fib.get(0.618, 0), fib.get(0.786, 0))
            obs_in_ote = [ob for ob in ctx.order_blocks if ob.valid and ob.direction == direction and ob.high >= ote_low and ob.low <= ote_high]
            if obs_in_ote:
                score += 10
                reasons.append("✓ OB within OTE zone — additional confluence")
        # NY KZ preferred (IST 18:00–20:30 = silver_bullet_ny_am / ny_kz)
        if ctx.kill_zone in ("silver_bullet_ny_am", "ny_kz"):
            score += 15
            reasons.append(f"✓ NY Kill Zone: {ctx.kill_zone}")
        score = round(min(max(score, 0), 100), 1)
        verdict = "support" if score >= 65 else ("neutral" if score >= 45 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk1Agent(BaseAgent):
    agent_id = "risk1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        setup = _find_ote_fvg_setup(ctx)
        if not setup:
            # FVG near OTE but NOT overlapping → hard veto signal
            if ctx.fib_levels:
                fib = ctx.fib_levels
                ote_low = min(fib.get(0.618, 0), fib.get(0.786, 0))
                ote_high = max(fib.get(0.618, 0), fib.get(0.786, 0))
                m15_fvgs = [f for f in ctx.fvgs if f.timeframe == "M15" and f.state in ("formed", "retested")]
                near_misses = [f for f in m15_fvgs if abs(f.bottom - ote_high) < pips_to_price(5) or abs(f.top - ote_low) < pips_to_price(5)]
                if near_misses:
                    score += 70
                    reasons.append("✗ FVG near OTE but NOT overlapping — NO_TRADE veto")
        if not ctx.sweeps:
            score += 20
            reasons.append("✗ no sweep — setup weakened")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []
        if ctx.kill_zone not in ("silver_bullet_ny_am", "ny_kz"):
            score += 15
            reasons.append(f"outside NY Kill Zone: {ctx.kill_zone}")
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread elevated: {ctx.current_spread_pips:.1f} pips")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class OTEFVGStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "OTE + FVG Confluence"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        setup = _find_ote_fvg_setup(ctx)
        if not setup:
            return None
        fib, ote_fvg, direction, _ = setup
        entry = fib.get(0.705)
        if entry is None:
            return None
        sl_extreme = fib.get(1.0 if direction == "bearish" else 0.0, entry)
        buf = pips_to_price(_SL_BUFFER_PIPS)
        tp1 = fib.get(0.0 if direction == "bullish" else 1.0, entry)
        tp2 = fib.get(-0.27)
        tp3 = fib.get(-0.62)
        if direction == "bullish":
            sl = round(sl_extreme - buf, 5)
            trade_dir = "buy"
        else:
            sl = round(sl_extreme + buf, 5)
            trade_dir = "sell"
        risk = abs(entry - sl)
        if risk <= 0:
            return None
        return TradeParameters(
            direction=trade_dir,
            entry=entry,
            sl=sl,
            tp1=tp1 or round(entry + 2 * risk * (1 if direction == "bullish" else -1), 5),
            tp2=tp2,
            tp3=tp3,
        )

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        setup = _find_ote_fvg_setup(ctx)
        if not setup:
            return None
        fib, ote_fvg, direction, _ = setup
        impulse_low = fib.get(0.0) if direction == "bullish" else fib.get(1.0)
        impulse_high = fib.get(1.0) if direction == "bullish" else fib.get(0.0)
        return f"{STRATEGY_ID}:{direction}:{_rnd(impulse_low or 0)}:{_rnd(impulse_high or 0)}:{_rnd(ote_fvg.ce)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        setup = _find_ote_fvg_setup(ctx)
        if not setup:
            return {}
        fib, ote_fvg, direction, overlap_pips = setup
        return {
            "fib_levels": {str(k): v for k, v in fib.items()},
            "ote_low": min(fib[0.618], fib[0.786]),
            "ote_high": max(fib[0.618], fib[0.786]),
            "overlap_pips": round(overlap_pips, 1),
            "fvg_ce": ote_fvg.ce,
            "entry_705": fib.get(0.705),
            "direction": direction,
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
