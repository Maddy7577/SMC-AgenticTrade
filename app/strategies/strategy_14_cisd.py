"""Strategy #14 — CISD (Change in State of Delivery) (FR-SP2-14-*).

Bearish M5 sequence (≥3 consecutive bearish candles); CISD = close above first candle open.
Within 15 pips of HTF key level; prior sweep required.
Hard Opp1 score cap of 65 — prevents standalone VALID.
Confirmation ancestry family member.
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

STRATEGY_ID = "14_cisd"
_KEY_LEVEL_TOLERANCE_PIPS = 15.0
_OPP1_SCORE_CAP = 65.0
_MIN_BEARISH_SEQ = 3


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _find_cisd_setup(ctx: CanonicalContext):
    """Return (sequence, cisd_candle, key_level, direction) or None.

    Bearish sequence = ≥3 consecutive bearish M5 candles.
    Bullish CISD fires when a candle closes above the first candle's open.
    """
    m5 = ctx.m5_candles
    if len(m5) < _MIN_BEARISH_SEQ + 2:
        return None

    # Find bearish sequences
    for end_idx in range(len(m5) - 1, _MIN_BEARISH_SEQ, -1):
        seq: list[dict] = []
        for i in range(end_idx, max(end_idx - 15, 0), -1):
            if m5[i]["c"] < m5[i]["o"]:
                seq.insert(0, m5[i])
            else:
                break
        if len(seq) < _MIN_BEARISH_SEQ:
            continue
        seq_open = seq[0]["o"]
        # Look for CISD candle: close above seq[0].open
        for cisd_idx in range(end_idx + 1, min(end_idx + 5, len(m5))):
            cisd_c = m5[cisd_idx]
            if cisd_c["c"] > seq_open:
                # Find nearest HTF key level
                key = _find_nearest_key_level(ctx, cisd_c["c"])
                if key is None:
                    continue
                dist_pips = price_to_pips(abs(cisd_c["c"] - key))
                if dist_pips > _KEY_LEVEL_TOLERANCE_PIPS:
                    continue
                return seq, cisd_c, key, "bullish"

    # Inverse: bullish sequence → bearish CISD
    for end_idx in range(len(m5) - 1, _MIN_BEARISH_SEQ, -1):
        seq = []
        for i in range(end_idx, max(end_idx - 15, 0), -1):
            if m5[i]["c"] > m5[i]["o"]:
                seq.insert(0, m5[i])
            else:
                break
        if len(seq) < _MIN_BEARISH_SEQ:
            continue
        seq_open = seq[0]["o"]
        for cisd_idx in range(end_idx + 1, min(end_idx + 5, len(m5))):
            cisd_c = m5[cisd_idx]
            if cisd_c["c"] < seq_open:
                key = _find_nearest_key_level(ctx, cisd_c["c"])
                if key is None:
                    continue
                dist_pips = price_to_pips(abs(cisd_c["c"] - key))
                if dist_pips > _KEY_LEVEL_TOLERANCE_PIPS:
                    continue
                return seq, cisd_c, key, "bearish"

    return None


def _find_nearest_key_level(ctx: CanonicalContext, price: float) -> float | None:
    """Find nearest key level (PDH/PDL, swing H/L, OB boundary) within tolerance."""
    candidates: list[float] = []
    if ctx.swings:
        candidates += [s["price"] for s in ctx.swings[-10:]]
    for ob in ctx.order_blocks:
        candidates += [ob.high, ob.low]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda x: abs(x - price))
    if price_to_pips(abs(nearest - price)) <= _KEY_LEVEL_TOLERANCE_PIPS * 2:
        return nearest
    return None


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        setup = _find_cisd_setup(ctx)
        if not setup:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no CISD setup found"], evidence={})
        seq, cisd_c, key, direction = setup
        checks: list[bool] = []
        checks.append(len(seq) >= _MIN_BEARISH_SEQ)
        reasons.append(f"✓ sequence: {len(seq)} consecutive candles")
        evidence["sequence_len"] = len(seq)
        checks.append(True)  # CISD candle found
        reasons.append(f"✓ CISD trigger at {cisd_c['c']:.5f}")
        evidence["cisd_close"] = cisd_c["c"]
        dist_pips = price_to_pips(abs(cisd_c["c"] - key))
        checks.append(dist_pips <= _KEY_LEVEL_TOLERANCE_PIPS)
        reasons.append(f"✓ within {dist_pips:.1f} pips of key level {key:.5f}" if dist_pips <= _KEY_LEVEL_TOLERANCE_PIPS else f"✗ {dist_pips:.1f} pips from key — too far")
        evidence["key_level"] = key
        evidence["dist_pips"] = round(dist_pips, 1)
        sweep_ok = len(ctx.sweeps) > 0
        checks.append(sweep_ok)
        reasons.append("✓ prior sweep present" if sweep_ok else "✗ no sweep")
        passes = sum(checks)
        # Hard cap at 65 to prevent standalone VALID
        raw_score = (passes / len(checks)) * 100
        score = min(raw_score, _OPP1_SCORE_CAP)
        verdict = "support" if passes >= 3 else ("neutral" if passes == 2 else "oppose")
        return AgentOpinion(agent_id=self.agent_id, score=round(score, 1), verdict=verdict,
                            reasons=reasons, evidence=evidence)


class _Opp2Agent(BaseAgent):
    agent_id = "opp2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 45.0
        reasons: list[str] = []
        setup = _find_cisd_setup(ctx)
        if setup:
            _, _, _, direction = setup
            fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested") and f.direction == direction]
            obs = [ob for ob in ctx.order_blocks if ob.valid and ob.direction == direction]
            if fvgs or obs:
                score += 20
                reasons.append("✓ FVG or OB available for entry")
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
        setup = _find_cisd_setup(ctx)
        if setup:
            _, cisd_c, key, _ = setup
            dist = price_to_pips(abs(cisd_c["c"] - key))
            if dist > _KEY_LEVEL_TOLERANCE_PIPS:
                score += 60
                reasons.append(f"✗ too far from key level: {dist:.1f} pips")
            if not ctx.sweeps:
                score += 30
                reasons.append("✗ no sweep — oppose")
        else:
            score += 40
            reasons.append("no CISD setup")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class _Risk2Agent(BaseAgent):
    agent_id = "risk2"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        score = 15.0
        reasons: list[str] = []
        # Without cluster companion, cap is important — signal low without cluster context
        if ctx.kill_zone == "none":
            score += 15
            reasons.append("outside session windows")
        if ctx.current_spread_pips and ctx.current_spread_pips > 1.2:
            score += 20
            reasons.append(f"spread elevated: {ctx.current_spread_pips:.1f} pips")
        score = round(min(max(score, 0), 100), 1)
        verdict = "oppose" if score >= 50 else ("neutral" if score >= 30 else "support")
        return AgentOpinion(agent_id=self.agent_id, score=score, verdict=verdict, reasons=reasons, evidence={})


class CISDStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "CISD"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        setup = _find_cisd_setup(ctx)
        if not setup:
            return None
        seq, cisd_c, key, direction = setup
        # Entry: FVG or OB retest after CISD
        fvgs = [f for f in ctx.fvgs if f.state in ("formed", "retested") and f.direction == direction]
        obs = [ob for ob in ctx.order_blocks if ob.valid and ob.direction == direction]
        if fvgs:
            entry = fvgs[-1].ce
        elif obs:
            entry = round((obs[-1].high + obs[-1].low) / 2, 5)
        else:
            return None
        # SL: beyond key level sweep extreme
        sweeps = ctx.sweeps
        sweep_wick = sweeps[-1].wick_extreme if sweeps else key
        if direction == "bullish":
            sl = round(min(sweep_wick, key) - pips_to_price(5), 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(entry + 2 * risk, 5)
            tp2 = round(entry + 3 * risk, 5)
            trade_dir = "buy"
        else:
            sl = round(max(sweep_wick, key) + pips_to_price(5), 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(entry - 2 * risk, 5)
            tp2 = round(entry - 3 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1, tp2=tp2)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        setup = _find_cisd_setup(ctx)
        if not setup:
            return None
        seq, cisd_c, key, direction = setup
        entry_price = cisd_c["c"]
        return f"{STRATEGY_ID}:{direction}:{_rnd(key)}:{_rnd(seq[0]['o'])}:{_rnd(entry_price)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        setup = _find_cisd_setup(ctx)
        if not setup:
            return {}
        seq, cisd_c, key, direction = setup
        return {
            "key_level": key,
            "sequence_open": seq[0]["o"],
            "direction": direction,
            "trigger_candle_t": str(cisd_c["t"]),
        }

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        # Opp1 score is capped at 65 — strict_rules_met can be at most 65 < 75 → no standalone VALID
        strict_rules_met = opp1.score >= 50
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
