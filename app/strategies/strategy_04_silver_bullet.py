"""Strategy #4 — Silver Bullet (FR-SP-04-*).

Time-window constrained: only fires within IST 13:30–14:30, 20:30–21:30, 00:30–01:30.
Both setup AND entry must occur within the active 1-hour window.
Minimum 15-pip distance from entry to target liquidity.
SL: Conservative (beyond sweep extreme) by default.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.detector.context import CanonicalContext
from app.detector.kill_zone import is_in_kill_zone
from app.strategies.base import (
    AgentOpinion,
    BaseAgent,
    BaseStrategy,
    StrategyResult,
    TradeParameters,
)
from app.strategies.debate import compute_verdict
from app.strategies.scoring import displacement_strength, structure_clarity
from config.instruments import pips_to_price, price_to_pips
from config.settings import TZ_IST

log = logging.getLogger(__name__)

STRATEGY_ID = "04_silver_bullet"
MIN_TARGET_PIPS = 15.0

_SB_WINDOWS = ["silver_bullet_london", "silver_bullet_ny_am", "silver_bullet_ny_pm"]


def _in_sb_window(ctx: CanonicalContext) -> bool:
    return ctx.kill_zone in _SB_WINDOWS


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        checks: list[bool] = []

        # Must be in a Silver Bullet window (FR-SP-04-01/02)
        in_window = _in_sb_window(ctx)
        checks.append(in_window)
        if in_window:
            reasons.append(f"✓ in Silver Bullet window: {ctx.kill_zone}")
        else:
            reasons.append(f"✗ outside Silver Bullet windows (current: {ctx.kill_zone})")

        # MSS present
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 15]
        mss_ok = len(mss) > 0
        checks.append(mss_ok)
        if mss_ok:
            reasons.append("✓ MSS confirmed within window")
            evidence["mss"] = {"level": mss[-1].broken_level}
        else:
            reasons.append("✗ no MSS in window")

        # FVG present
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        fvg_ok = len(fvgs) > 0
        checks.append(fvg_ok)
        if fvg_ok:
            reasons.append("✓ FVG present")
            evidence["fvg"] = {"midpoint": fvgs[-1].midpoint}
        else:
            reasons.append("✗ no FVG")

        # Minimum 15-pip to target (FR-SP-04-03)
        target_ok = False
        if ctx.swings and ctx.current_price:
            highs = [s for s in ctx.swings if s["kind"] == "high"]
            lows = [s for s in ctx.swings if s["kind"] == "low"]
            if highs and lows:
                nearest_h = min(highs, key=lambda s: abs(s["price"] - ctx.current_price))
                nearest_l = min(lows, key=lambda s: abs(s["price"] - ctx.current_price))
                best_dist = max(
                    price_to_pips(abs(nearest_h["price"] - ctx.current_price)),
                    price_to_pips(abs(nearest_l["price"] - ctx.current_price)),
                )
                target_ok = best_dist >= MIN_TARGET_PIPS
        checks.append(target_ok)
        if target_ok:
            reasons.append("✓ ≥ 15 pip distance to target")
        else:
            reasons.append("✗ < 15 pips to nearest target")

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
            score += ds * 25
            reasons.append(f"displacement strength: {ds:.2f}")

        sc = structure_clarity(ctx.mss_events, ctx.fvgs)
        score += sc * 15
        reasons.append(f"structure clarity: {sc:.2f}")

        # HTF aligned bonus
        if ctx.htf_bias != "neutral":
            score += 10
            reasons.append(f"HTF bias: {ctx.htf_bias}")

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
                score += 30
                reasons.append("opposing liquidity within ATR")
            else:
                reasons.append("path clear to target")

        if ctx.htf_bias == "neutral":
            score += 15
            reasons.append("no clear HTF bias")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 10.0
        reasons: list[str] = []

        if not _in_sb_window(ctx):
            score += 40
            reasons.append("not in Silver Bullet window — hard constraint")
        else:
            reasons.append(f"window active: {ctx.kill_zone}")

        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread {ctx.current_spread_pips:.1f} pips elevated")

        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class SilverBulletStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Silver Bullet"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        if not _in_sb_window(ctx):
            return None
        sweeps = [s for s in ctx.sweeps if s.index >= len(ctx.m1_candles) - 10]
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 15]
        if not sweeps or not fvgs or not mss or not ctx.atr_m1:
            return None

        sweep = sweeps[-1]
        fvg = fvgs[-1]
        m = mss[-1]
        entry = fvg.midpoint

        if m.direction == "bullish":
            sl = sweep.wick_extreme - ctx.atr_m1 * 0.5  # conservative: beyond sweep extreme
            risk = entry - sl
            tp1 = entry + 2 * risk
            direction = "buy"
        else:
            sl = sweep.wick_extreme + ctx.atr_m1 * 0.5
            risk = sl - entry
            tp1 = entry - 2 * risk
            direction = "sell"

        if risk <= 0:
            return None
        return TradeParameters(direction=direction, entry=round(entry, 5), sl=round(sl, 5), tp1=round(tp1, 5))

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        sweeps = [s for s in ctx.sweeps if s.index >= len(ctx.m1_candles) - 10]
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 15]
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested")]
        if not sweeps or not mss or not fvgs:
            return None
        rnd = lambda p: round(round(p / 0.0005) * 0.0005, 5)
        return f"{STRATEGY_ID}:{mss[-1].direction}:{rnd(sweeps[-1].swept_level)}:{rnd(mss[-1].broken_level)}:{rnd(fvgs[-1].midpoint)}"

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        strict_rules_met = opp1.score >= 75  # all 4 strict checks passed

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
