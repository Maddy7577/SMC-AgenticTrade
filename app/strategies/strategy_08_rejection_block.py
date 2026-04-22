"""Strategy #8 — Rejection Block at Last-Defense Levels (FR-SP2-08-*).

Rejection candle (wick ≥2× body); Fib retracement 80–90%; HTF key level; MSS/CHoCH.
50%-body-penetration hard veto → strict_rules_met = False → NO_TRADE.
SL: 10 pips beyond wick extreme. TP: RR ≥ 3.0.
"""

from __future__ import annotations

import logging

from app.detector.context import CanonicalContext
from app.detector.long_wick_classifier import classify_wick
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

STRATEGY_ID = "08_rejection_block"
_SL_BUFFER_PIPS = 10.0
_FIB_RETRACEMENT_MIN = 0.80
_FIB_RETRACEMENT_MAX = 0.90


def _rnd(p: float) -> float:
    return round(round(p / 0.0005) * 0.0005, 5)


def _fib_retracement_pct(price: float, fib_levels: dict[float, float], direction: str) -> float | None:
    """Compute how deep price has retraced into the fib range (0=0%, 1=100%)."""
    high = fib_levels.get(1.0)
    low = fib_levels.get(0.0)
    if high is None or low is None or high == low:
        return None
    if direction == "bullish":
        # retracement from swing high toward swing low
        return (high - price) / (high - low)
    else:
        return (price - low) / (high - low)


def _find_rejection_setup(ctx: CanonicalContext):
    """Return (wick_info, rejection_candle, fib_pct, key_level, direction) or None."""
    if not ctx.fib_levels:
        return None

    # Check recent M15 and H1 candles for rejection wicks
    candidates: list[tuple[dict, str]] = []
    for c in ctx.m15_candles[-5:]:
        candidates.append((c, "M15"))
    for c in ctx.h1_candles[-3:]:
        candidates.append((c, "H1"))

    for candle, _tf in reversed(candidates):
        wick_info = classify_wick(candle)
        if wick_info is None:
            continue
        rej_direction = "bullish" if wick_info["type"] == "bullish_rejection" else "bearish"
        # H1 = 1 wick required; M15 = ≥2 wicks required — we check single here (multi is Opp2)
        fib_pct = _fib_retracement_pct(candle["c"], ctx.fib_levels, rej_direction)
        if fib_pct is None:
            continue
        if not (_FIB_RETRACEMENT_MIN <= fib_pct <= _FIB_RETRACEMENT_MAX):
            continue
        # Nearest key level
        key = _find_key_level(ctx, candle["c"], rej_direction)
        if key is None:
            continue
        return wick_info, candle, fib_pct, key, rej_direction
    return None


def _find_key_level(ctx: CanonicalContext, price: float, direction: str) -> float | None:
    candidates: list[float] = []
    if ctx.swings:
        candidates += [s["price"] for s in ctx.swings[-10:]]
    for ob in ctx.order_blocks:
        candidates += [ob.high, ob.low]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda x: abs(x - price))
    if price_to_pips(abs(nearest - price)) <= 20:
        return nearest
    return None


def _check_50pct_body_penetration(rejection_candle: dict, ctx: CanonicalContext) -> bool:
    """Return True if any subsequent candle penetrates >50% of the rejection candle body."""
    rej_t = str(rejection_candle["t"])
    rej_body_high = max(rejection_candle["o"], rejection_candle["c"])
    rej_body_low = min(rejection_candle["o"], rejection_candle["c"])
    rej_body_mid = (rej_body_high + rej_body_low) / 2
    all_candles = ctx.m1_candles + ctx.m5_candles + ctx.m15_candles
    for c in all_candles:
        if str(c["t"]) <= rej_t:
            continue
        # Bearish rejection: subsequent candle body goes below 50% of the body = penetration
        if c["l"] < rej_body_mid and c["c"] < rej_body_mid:
            return True
        # Bullish rejection: subsequent candle body goes above 50% = penetration
        if c["h"] > rej_body_mid and c["c"] > rej_body_mid:
            return True
    return False


class _Opp1Agent(BaseAgent):
    agent_id = "opp1"

    def evaluate(self, ctx: CanonicalContext) -> AgentOpinion:
        reasons: list[str] = []
        evidence: dict = {}
        setup = _find_rejection_setup(ctx)
        if not setup:
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=["✗ no rejection block setup found"], evidence={})
        wick_info, rej_c, fib_pct, key, direction = setup
        checks: list[bool] = []
        checks.append(True)
        reasons.append(f"✓ rejection candle: {wick_info['type']}, ratio {wick_info['ratio']:.1f}×")
        evidence["wick_info"] = wick_info
        evidence["fib_pct"] = round(fib_pct * 100, 1)
        fib_ok = _FIB_RETRACEMENT_MIN <= fib_pct <= _FIB_RETRACEMENT_MAX
        checks.append(fib_ok)
        reasons.append(f"✓ fib retracement: {fib_pct * 100:.0f}% (80–90% zone)" if fib_ok else f"✗ fib retracement: {fib_pct * 100:.0f}%")
        key_dist = price_to_pips(abs(rej_c["c"] - key))
        checks.append(key_dist <= 10)
        reasons.append(f"✓ HTF key level: {key:.5f} ({key_dist:.1f} pips)" if key_dist <= 10 else f"✗ key level too far: {key_dist:.1f} pips")
        evidence["key_level"] = key
        mss = [m for m in ctx.mss_events if m.index >= len(ctx.m1_candles) - 20]
        checks.append(len(mss) > 0)
        reasons.append("✓ MSS/CHoCH confirmed" if mss else "✗ no MSS/CHoCH")
        # 50%-body-penetration check
        penetrated = _check_50pct_body_penetration(rej_c, ctx)
        if penetrated:
            evidence["body_penetration"] = "FAIL"
            reasons.append("✗ 50%-body-penetration FAIL — setup invalid")
            return AgentOpinion(agent_id=self.agent_id, score=0.0, verdict="oppose",
                                reasons=reasons, evidence=evidence)
        evidence["body_penetration"] = "PASS"
        reasons.append("✓ 50%-body-penetration PASS")
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
        setup = _find_rejection_setup(ctx)
        if setup:
            wick_info, _, fib_pct, _, direction = setup
            score += min(wick_info["ratio"] * 5, 20)
            reasons.append(f"wick quality: {wick_info['ratio']:.1f}×")
            # M15 requires ≥2 rejection wicks (bonus check)
            m15_wicks = sum(1 for c in ctx.m15_candles[-10:] if classify_wick(c) and classify_wick(c)["type"] == wick_info["type"])
            if m15_wicks >= 2:
                score += 10
                reasons.append(f"✓ ≥2 M15 rejection wicks: {m15_wicks}")
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
        setup = _find_rejection_setup(ctx)
        if setup:
            wick_info, rej_c, _, _, _ = setup
            if _check_50pct_body_penetration(rej_c, ctx):
                score += 70
                reasons.append("✗ 50% body penetration — strict_rules_met=False")
            if not ctx.mss_events:
                score += 25
                reasons.append("✗ no MSS — oppose")
        else:
            score += 40
            reasons.append("no rejection block setup")
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


class RejectionBlockStrategy(BaseStrategy):
    strategy_id = STRATEGY_ID
    strategy_name = "Rejection Block"

    def __init__(self) -> None:
        self._agents = [_Opp1Agent(), _Opp2Agent(), _Risk1Agent(), _Risk2Agent()]

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def build_trade_parameters(self, ctx: CanonicalContext) -> TradeParameters | None:
        setup = _find_rejection_setup(ctx)
        if not setup:
            return None
        wick_info, rej_c, fib_pct, key, direction = setup
        if _check_50pct_body_penetration(rej_c, ctx):
            return None
        buf = pips_to_price(_SL_BUFFER_PIPS)
        body_high = max(rej_c["o"], rej_c["c"])
        body_low = min(rej_c["o"], rej_c["c"])
        if direction == "bullish":
            wick_extreme = rej_c["l"]
            entry = body_low  # price returns to body
            sl = round(wick_extreme - buf, 5)
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = round(entry + 3 * risk, 5)
            trade_dir = "buy"
        else:
            wick_extreme = rej_c["h"]
            entry = body_high
            sl = round(wick_extreme + buf, 5)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = round(entry - 3 * risk, 5)
            trade_dir = "sell"
        return TradeParameters(direction=trade_dir, entry=entry, sl=sl, tp1=tp1)

    def build_signature(self, ctx: CanonicalContext) -> str | None:
        setup = _find_rejection_setup(ctx)
        if not setup:
            return None
        wick_info, rej_c, _, key, direction = setup
        wick_extreme = rej_c["l"] if direction == "bullish" else rej_c["h"]
        body_ce = round((max(rej_c["o"], rej_c["c"]) + min(rej_c["o"], rej_c["c"])) / 2, 5)
        return f"{STRATEGY_ID}:{direction}:{_rnd(key)}:{_rnd(wick_extreme)}:{_rnd(body_ce)}"

    def build_evidence(self, ctx: CanonicalContext) -> dict:
        setup = _find_rejection_setup(ctx)
        if not setup:
            return {}
        wick_info, rej_c, fib_pct, key, direction = setup
        penetrated = _check_50pct_body_penetration(rej_c, ctx)
        return {
            "wick_info": wick_info,
            "fib_pct": round(fib_pct * 100, 1),
            "body_penetration": "FAIL" if penetrated else "PASS",
            "key_level": key,
            "direction": direction,
        }

    def evaluate(self, ctx: CanonicalContext) -> StrategyResult:
        opinions = [a.evaluate(ctx) for a in self._agents]
        opp1 = next(o for o in opinions if o.agent_id == "opp1")
        setup = _find_rejection_setup(ctx)
        penetrated = False
        if setup:
            _, rej_c, _, _, _ = setup
            penetrated = _check_50pct_body_penetration(rej_c, ctx)
        strict_rules_met = opp1.score >= 75 and not penetrated
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
