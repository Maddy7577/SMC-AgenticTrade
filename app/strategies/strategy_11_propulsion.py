"""Strategy #11 — Propulsion Block (FR-SP2-11-*).

Activated OB + propulsion candle (body/range ≥ 0.6) + FVG in candles [prop+1 to prop+3].
OB must not be retouched after propulsion. H1 accumulated liquidity required.
Entry: retest of propulsion block zone. SL: beyond OB extreme + 10 pips.
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

STRATEGY_ID = "11_propulsion"
_SL_BUFFER_PIPS = 10.0
_PROPULSION_RATIO = 0.6
_LIQUIDITY_LOOKBACK_H1 = 50
_LIQUIDITY_MIN_TOUCHES = 2


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_propulsion_setup(ctx: CanonicalContext):
    """Return (ob, prop_candle, prop_ratio, post_fvg, direction) or None."""
    m5 = ctx.m5_candles
    # Consider all OBs (valid = not yet retouched)
    valid_obs = [ob for ob in ctx.order_blocks if ob.valid]
    if not valid_obs or len(m5) < 5:
        return None

    fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]

    for ob in reversed(valid_obs):
        direction = ob.direction
        # Find propulsion candle inside OB zone
        for i, c in enumerate(m5):
            if i + 3 >= len(m5):
                break
            total_range = c["h"] - c["l"]
            if total_range <= 0:
                continue
            body = abs(c["c"] - c["o"])
            ratio = body / total_range
            if ratio < _PROPULSION_RATIO:
                continue
            # Candle inside OB zone
            c_mid = (c["h"] + c["l"]) / 2
            if not (ob.low <= c_mid <= ob.high):
                continue
            # Direction match
            is_bull = c["c"] > c["o"]
            if direction == "bullish" and not is_bull:
                continue
            if direction == "bearish" and is_bull:
                continue
            # FVG in candles [i+1 to i+3]
            post_window_t_start = str(m5[i + 1]["t"])
            post_window_t_end = str(m5[min(i + 3, len(m5) - 1)]["t"])
            post_fvgs = [
                f for f in fvgs
                if f.timeframe in ("M5", "M15") and
                f.direction == direction and
                f.c1_t >= post_window_t_start and
                f.c3_t <= post_window_t_end
            ]
            if not post_fvgs:
                continue
            # OB not retouched after propulsion
            retouched = False
            for later in m5[i + 1:]:
                if direction == "bullish" and later["l"] <= ob.low:
                    retouched = True
                    break
                if direction == "bearish" and later["h"] >= ob.high:
                    retouched = True
                    break
            if retouched:
                continue
            return ob, c, ratio, post_fvgs[0], direction
    return None


def _has_h1_liquidity(ctx: CanonicalContext, direction: str) -> bool:
    """Check if H1 has accumulated liquidity (swing H/L touched ≥2 times)."""
    h1 = ctx.h1_candles[-_LIQUIDITY_LOOKBACK_H1:]
    if not h1:
        return False
    highs = [c["h"] for c in h1]
    lows = [c["l"] for c in h1]
    if direction == "bullish":
        swing_low = min(lows)
        touches = sum(1 for l in lows if abs(l - swing_low) <= 0.0005)
        return touches >= _LIQUIDITY_MIN_TOUCHES
    else:
        swing_high = max(highs)
        touches = sum(1 for h in highs if abs(h - swing_high) <= 0.0005)
        return touches >= _LIQUIDITY_MIN_TOUCHES


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        setup = _find_propulsion_setup(ctx)
        if not setup:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no propulsion block setup found"], evidence={})
        ob, prop_c, ratio, post_fvg, direction = setup
        checks: list[bool] = []
        checks.append(True)  # activated OB found
        reasons.append(f"✓ OB zone: {ob.low:.5f}–{ob.high:.5f} ({direction})")
        evidence["ob"] = {"low": ob.low, "high": ob.high, "direction": direction}
        checks.append(ratio >= _PROPULSION_RATIO)
        reasons.append(f"✓ propulsion candle body/range: {ratio:.2f}" if ratio >= _PROPULSION_RATIO else f"✗ body ratio: {ratio:.2f}")
        evidence["prop_ratio"] = round(ratio, 3)
        checks.append(post_fvg is not None)
        reasons.append(f"✓ FVG after propulsion: CE={post_fvg.ce:.5f}" if post_fvg else "✗ no FVG after propulsion")
        liq = _has_h1_liquidity(ctx, direction)
        checks.append(liq)
        reasons.append("✓ H1 accumulated liquidity present" if liq else "✗ no H1 accumulated liquidity")
        # Daily bias
        bias_ok = ctx.htf_bias == direction or (direction == "bullish" and ctx.htf_bias == "bullish") or (direction == "bearish" and ctx.htf_bias == "bearish")
        checks.append(bias_ok)
        reasons.append(f"✓ daily bias: {ctx.htf_bias}" if bias_ok else f"✗ daily bias mismatch: {ctx.htf_bias}")
        passes = sum(checks)
        score = (passes / len(checks)) * 100
        verdict = "support" if passes >= 4 else ("neutral" if passes >= 2 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict,
                            reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 45.0
        reasons: list[str] = []
        setup = _find_propulsion_setup(ctx)
        if setup:
            _, _, ratio, _, direction = setup
            score += ratio * 15
            reasons.append(f"propulsion quality: {ratio:.2f}")
            if ctx.htf_bias == direction:
                score += 15
                reasons.append("✓ daily bias alignment bonus")
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
        setup = _find_propulsion_setup(ctx)
        if setup:
            ob, _, _, _, direction = setup
            # Check if OB was retouched (already filtered in setup detection — add veto if daily mismatch)
            if ctx.htf_bias not in ("neutral", direction):
                score += 50
                reasons.append("✗ daily bias misalignment — NO_TRADE")
        if not setup:
            score += 30
            reasons.append("no valid propulsion setup")
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


class PropulsionBlockStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Propulsion Block"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        setup = _find_propulsion_setup(ctx)
        if not setup:
            return None
        ob, _, _, _, direction = setup
        buf = pips_to_price(_SL_BUFFER_PIPS)
        entry = round((ob.high + ob.low) / 2, 5)
        if direction == "bullish":
            sl = round(ob.low - buf, 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(entry + 2 * risk, 5)
            tp2 = round(entry + 3 * risk, 5)
            trade_dir = "buy"
        else:
            sl = round(ob.high + buf, 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(entry - 2 * risk, 5)
            tp2 = round(entry - 3 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        setup = _find_propulsion_setup(ctx)
        if not setup:
            return None
        ob, _, _, _, direction = setup
        entry = round((ob.high + ob.low) / 2, 5)
        return f"{STRATEGY_ID}:{direction}:{_rnd(ob.low)}:{_rnd(ob.high)}:{_rnd(entry)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        setup = _find_propulsion_setup(ctx)
        if not setup:
            return {}
        ob, _, prop_ratio, post_fvg, direction = setup
        return {
            "ob_low": ob.low,
            "ob_high": ob.high,
            "prop_ratio": round(prop_ratio, 2),
            "post_fvg_ce": post_fvg.ce if post_fvg else None,
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
