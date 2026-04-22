"""Strategy #15 — Balanced Price Range in Order Block (FR-SP2-15-*).

HTF OB (H4+) with overlapping bullish AND bearish M15 FVGs inside.
Overlap ≥ 3 pips = BPR. Entry: BPR midpoint. SL: beyond full OB extreme.
Independent ancestry root — never clusters with any family.
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

STRATEGY_ID = "15_bpr_ob"
_MIN_BPR_PIPS = 3.0


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_bpr_setup(ctx: CanonicalContext):
    """Return (ob, bull_fvg, bear_fvg, bpr_top, bpr_bottom, bpr_mid, direction) or None."""
    # HTF OBs from H4+ (use H4-timeframe OBs — order_blocks is computed on M5 but we need H4 scope)
    # We use the order_blocks detected from H4 candles (timeframe filtering)
    h4_obs = [ob for ob in ctx.order_blocks if ob.timeframe in ("H4", "H1") and ob.valid]
    if not h4_obs:
        return None
    m15_fvgs = [f for f in ctx.fvgs if f.timeframe == "M15" and f.state in ("formed", "retested")]
    bull_m15 = [f for f in m15_fvgs if f.direction == "bullish"]
    bear_m15 = [f for f in m15_fvgs if f.direction == "bearish"]
    if not bull_m15 or not bear_m15:
        return None

    for ob in reversed(h4_obs):
        # Find bull and bear FVGs inside OB zone
        bull_in_ob = [f for f in bull_m15 if f.bottom >= ob.low and f.top <= ob.high]
        bear_in_ob = [f for f in bear_m15 if f.bottom >= ob.low and f.top <= ob.high]
        if not bull_in_ob or not bear_in_ob:
            continue
        # Find the overlap between a bull and bear FVG
        for bf in bull_in_ob:
            for br in bear_in_ob:
                overlap_top = min(bf.top, br.top)
                overlap_bot = max(bf.bottom, br.bottom)
                if overlap_top <= overlap_bot:
                    continue
                overlap_pips = price_to_pips(overlap_top - overlap_bot)
                if overlap_pips < _MIN_BPR_PIPS:
                    continue
                bpr_mid = round((overlap_top + overlap_bot) / 2, 5)
                direction = ob.direction
                return ob, bf, br, overlap_top, overlap_bot, bpr_mid, direction
    return None


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        setup = _find_bpr_setup(ctx)
        if not setup:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no BPR in OB setup found"], evidence={})
        ob, bf, br, bpr_top, bpr_bot, bpr_mid, direction = setup
        checks: list[bool] = []
        overlap_pips = price_to_pips(bpr_top - bpr_bot)

        checks.append(True)  # HTF OB present
        reasons.append(f"✓ HTF OB: {ob.low:.5f}–{ob.high:.5f} ({ob.timeframe})")
        evidence["ob"] = {"low": ob.low, "high": ob.high, "timeframe": ob.timeframe}

        checks.append(overlap_pips >= _MIN_BPR_PIPS)
        reasons.append(f"✓ BPR overlap: {overlap_pips:.1f} pips" if overlap_pips >= _MIN_BPR_PIPS else f"✗ BPR overlap too small: {overlap_pips:.1f} pips")
        evidence["bpr_pips"] = round(overlap_pips, 1)
        evidence["bpr_mid"] = bpr_mid

        # LTF structure shift
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        checks.append(len(mss) > 0)
        reasons.append("✓ LTF MSS present" if mss else "✗ no LTF MSS")

        # HTF bias
        bias_ok = ctx.htf_bias == direction
        checks.append(bias_ok)
        reasons.append(f"✓ HTF bias: {ctx.htf_bias}" if bias_ok else f"HTF bias: {ctx.htf_bias}")

        # High base score for BPR (highest-probability model)
        base_score = 75.0
        passes = sum(checks)
        score = base_score * (passes / len(checks))
        verdict = "support" if passes >= 3 else ("neutral" if passes == 2 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict,
                            reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 50.0
        reasons: list[str] = []
        setup = _find_bpr_setup(ctx)
        if setup:
            ob, _, _, bpr_top, bpr_bot, _, _ = setup
            # H4 OB scores max; H1 OB reduced
            if ob.timeframe == "H4":
                score += 20
                reasons.append("✓ H4 OB — max score")
            else:
                score += 5
                reasons.append(f"H1 OB — reduced score ({ob.timeframe})")
            reasons.append(f"BPR overlap: {price_to_pips(bpr_top - bpr_bot):.1f} pips")
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
        setup = _find_bpr_setup(ctx)
        if not setup:
            score += 40
            reasons.append("no BPR setup found")
        else:
            _, _, _, bpr_top, bpr_bot, _, _ = setup
            overlap_pips = price_to_pips(bpr_top - bpr_bot)
            if overlap_pips < _MIN_BPR_PIPS:
                score += 60
                reasons.append("✗ BPR overlap < 3 pips — NO_TRADE")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


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


class BPRInOBStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "BPR in OB"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        setup = _find_bpr_setup(ctx)
        if not setup:
            return None
        ob, _, _, _, _, bpr_mid, direction = setup
        entry = bpr_mid
        if direction == "bullish":
            sl = round(ob.low - pips_to_price(10), 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(entry + 2 * risk, 5)
            tp2 = round(entry + 3 * risk, 5)
            trade_dir = "buy"
        else:
            sl = round(ob.high + pips_to_price(10), 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(entry - 2 * risk, 5)
            tp2 = round(entry - 3 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        setup = _find_bpr_setup(ctx)
        if not setup:
            return None
        ob, _, _, _, _, bpr_mid, direction = setup
        return f"{STRATEGY_ID}:{direction}:{_rnd(ob.low)}:{_rnd(ob.high)}:{_rnd(bpr_mid)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        setup = _find_bpr_setup(ctx)
        if not setup:
            return {}
        ob, _, _, bpr_top, bpr_bottom, bpr_mid, direction = setup
        return {
            "ob_low": ob.low,
            "ob_high": ob.high,
            "ob_timeframe": ob.timeframe,
            "bpr_top": bpr_top,
            "bpr_bottom": bpr_bottom,
            "bpr_mid": bpr_mid,
            "overlap_pips": round(price_to_pips(bpr_top - bpr_bottom), 1),
            "direction": direction,
        }

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        strict_rules_met = opp1.score >= 56  # 75% of 75 base
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
