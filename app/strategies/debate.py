"""Debate aggregator — combines 4 agent opinions into a strategy verdict (D2).

Verdict logic (FR-S-09):
  VALID  when confidence ≥ 75 AND all strict rules met AND RR ≥ 2 AND no hard veto
  WAIT   when setup valid but price not at entry zone AND confidence ≥ 65
  else   NO_TRADE

Confidence formula:
  weighted_mean(support scores) − weighted_mean(oppose scores)
  mapped to 0–100 via sigmoid-like linear clamp.

Probability formula (plan §Ambiguities #1):
  agreement × confluence_factor × clarity
"""

from __future__ import annotations

import math

from app.strategies.base import AgentOpinion, StrategyResult, TradeParameters, Verdict
from config.settings import (
    CONFIDENCE_VALID_THRESHOLD,
    CONFIDENCE_WAIT_THRESHOLD,
    RR_FLOOR,
)

# Weights: opportunity agents contribute positively, risk agents negatively
_WEIGHTS: dict[str, float] = {
    "opp1": 1.5,   # strict rule compliance — highest weight
    "opp2": 1.0,   # quality score
    "risk1": 1.2,  # technical risk
    "risk2": 0.8,  # contextual risk
}


def compute_verdict(
    strategy_id: str,
    strategy_name: str,
    opinions: list[AgentOpinion],
    trade: TradeParameters | None,
    strict_rules_met: bool,
    price_at_entry: bool,
    signature: str | None,
) -> StrategyResult:
    if not opinions:
        return StrategyResult(
            strategy_id=strategy_id,
            verdict="NO_TRADE",
            confidence=0.0,
            probability=0.0,
            rejection_reasons=["no agent opinions produced"],
        )

    opp_weighted_sum = 0.0
    opp_weight_total = 0.0
    risk_weighted_sum = 0.0
    risk_weight_total = 0.0

    for op in opinions:
        w = _WEIGHTS.get(op.agent_id, 1.0)
        if op.agent_id.startswith("opp"):
            opp_weighted_sum += op.score * w
            opp_weight_total += w * 100
        else:
            risk_weighted_sum += op.score * w
            risk_weight_total += w * 100

    opp_norm = opp_weighted_sum / opp_weight_total if opp_weight_total else 0.5
    risk_norm = risk_weighted_sum / risk_weight_total if risk_weight_total else 0.5

    raw_conf = (opp_norm - risk_norm + 1.0) / 2.0  # maps to [0, 1]
    confidence = round(min(max(raw_conf * 100, 0.0), 100.0), 1)

    # Probability (plan §Ambiguities #1)
    scores = [op.score for op in opinions]
    variance = sum((s - (sum(scores) / len(scores))) ** 2 for s in scores) / len(scores)
    agreement = max(0.6, 1.0 - variance / 5000)  # less variance = higher agreement
    clarity = min(opp_norm, 1.0)
    probability = round(min(agreement * clarity * 100, 100.0), 1)

    rejection: list[str] = []

    # Check RR
    rr_ok = trade is not None and trade.rr >= RR_FLOOR

    if not strict_rules_met:
        rejection.append("strict rules not met")
    if trade is None:
        rejection.append("no valid trade parameters")
    if not rr_ok and trade is not None:
        rejection.append(f"RR {trade.rr:.1f} below floor {RR_FLOOR}")

    # Hard veto: any risk agent with score > 70 and verdict 'oppose'
    hard_veto = any(op.verdict == "oppose" and op.score > 70 for op in opinions if op.agent_id.startswith("risk"))

    verdict: Verdict
    if (
        confidence >= CONFIDENCE_VALID_THRESHOLD
        and strict_rules_met
        and rr_ok
        and not hard_veto
        and price_at_entry
    ):
        verdict = "VALID"
    elif (
        confidence >= CONFIDENCE_WAIT_THRESHOLD
        and strict_rules_met
        and not hard_veto
    ):
        verdict = "WAIT"
    else:
        verdict = "NO_TRADE"

    if hard_veto:
        rejection.append("hard veto from risk agent")

    return StrategyResult(
        strategy_id=strategy_id,
        verdict=verdict,
        confidence=confidence,
        probability=probability,
        agent_opinions=opinions,
        trade=trade if verdict != "NO_TRADE" else None,
        signature=signature,
        rejection_reasons=rejection,
    )
