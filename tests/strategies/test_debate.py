"""Unit tests for debate aggregator — threshold transitions (J3)."""

from __future__ import annotations

import pytest

from app.strategies.base import AgentOpinion, TradeParameters
from app.strategies.debate import compute_verdict


def _opinions(opp1: float, opp2: float, risk1: float, risk2: float) -> list[AgentOpinion]:
    def _v(score: float) -> str:
        return "support" if score >= 50 else "oppose"
    return [
        AgentOpinion("opp1", opp1, _v(opp1)),   # type: ignore[arg-type]
        AgentOpinion("opp2", opp2, _v(opp2)),   # type: ignore[arg-type]
        AgentOpinion("risk1", risk1, _v(risk1)), # type: ignore[arg-type]
        AgentOpinion("risk2", risk2, _v(risk2)), # type: ignore[arg-type]
    ]


def _trade(rr: float = 2.5) -> TradeParameters:
    entry, sl = 1.10000, 1.09900  # 10 pip risk
    tp1 = entry + rr * (entry - sl)
    t = TradeParameters(direction="buy", entry=entry, sl=sl, tp1=tp1)
    return t


# ---------------------------------------------------------------------------
# VALID path
# ---------------------------------------------------------------------------

def test_high_opp_low_risk_produces_valid():
    opinions = _opinions(opp1=90, opp2=85, risk1=20, risk2=25)
    result = compute_verdict(
        "03_test", "Test Strategy", opinions,
        trade=_trade(2.5),
        strict_rules_met=True,
        price_at_entry=True,
        signature="test_sig",
    )
    assert result.verdict == "VALID"
    assert result.confidence >= 75.0


# ---------------------------------------------------------------------------
# WAIT path (confidence 65–74)
# ---------------------------------------------------------------------------

def test_moderate_confidence_produces_wait():
    # Moderate opp, moderate risk, strict rules met but price not at entry
    opinions = _opinions(opp1=70, opp2=65, risk1=40, risk2=35)
    result = compute_verdict(
        "03_test", "Test Strategy", opinions,
        trade=_trade(2.5),
        strict_rules_met=True,
        price_at_entry=False,  # not at entry → can't be VALID
        signature="test_sig",
    )
    assert result.verdict in ("WAIT", "NO_TRADE")


def test_confidence_below_65_produces_no_trade():
    opinions = _opinions(opp1=30, opp2=35, risk1=70, risk2=60)
    result = compute_verdict(
        "03_test", "Test Strategy", opinions,
        trade=_trade(2.5),
        strict_rules_met=True,
        price_at_entry=True,
        signature="test_sig",
    )
    assert result.verdict == "NO_TRADE"


# ---------------------------------------------------------------------------
# RR floor boundary
# ---------------------------------------------------------------------------

def test_rr_199_blocks_valid():
    opinions = _opinions(opp1=90, opp2=85, risk1=20, risk2=25)
    entry, sl = 1.10000, 1.09900  # 10 pip risk
    tp1 = entry + 1.99 * (entry - sl)  # RR = 1.99
    trade = TradeParameters("buy", entry, sl, tp1)
    result = compute_verdict(
        "03_test", "Test Strategy", opinions,
        trade=trade,
        strict_rules_met=True,
        price_at_entry=True,
        signature="test_sig",
    )
    assert result.verdict != "VALID"


def test_rr_200_allows_valid():
    opinions = _opinions(opp1=90, opp2=85, risk1=20, risk2=25)
    entry, sl = 1.10000, 1.09900
    tp1 = entry + 2.0 * (entry - sl)  # RR exactly 2.0
    trade = TradeParameters("buy", entry, sl, tp1)
    result = compute_verdict(
        "03_test", "Test Strategy", opinions,
        trade=trade,
        strict_rules_met=True,
        price_at_entry=True,
        signature="test_sig",
    )
    assert result.verdict == "VALID"


# ---------------------------------------------------------------------------
# Strict rules gate
# ---------------------------------------------------------------------------

def test_strict_rules_not_met_blocks_valid():
    opinions = _opinions(opp1=90, opp2=85, risk1=20, risk2=25)
    result = compute_verdict(
        "03_test", "Test Strategy", opinions,
        trade=_trade(3.0),
        strict_rules_met=False,  # hard gate
        price_at_entry=True,
        signature="test_sig",
    )
    assert result.verdict != "VALID"


# ---------------------------------------------------------------------------
# Hard veto
# ---------------------------------------------------------------------------

def test_risk_hard_veto_blocks_valid():
    opinions = [
        AgentOpinion("opp1", 90, "support"),  # type: ignore[arg-type]
        AgentOpinion("opp2", 85, "support"),  # type: ignore[arg-type]
        AgentOpinion("risk1", 80, "oppose"),  # hard veto: oppose + score > 70
        AgentOpinion("risk2", 20, "support"), # type: ignore[arg-type]
    ]
    result = compute_verdict(
        "03_test", "Test Strategy", opinions,
        trade=_trade(3.0),
        strict_rules_met=True,
        price_at_entry=True,
        signature="test_sig",
    )
    assert result.verdict != "VALID"
    assert any("veto" in r for r in result.rejection_reasons)


# ---------------------------------------------------------------------------
# Empty opinions
# ---------------------------------------------------------------------------

def test_empty_opinions_produces_no_trade():
    result = compute_verdict(
        "03_test", "Test Strategy", opinions=[],
        trade=_trade(),
        strict_rules_met=True,
        price_at_entry=True,
        signature=None,
    )
    assert result.verdict == "NO_TRADE"
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# TradeParameters RR auto-calculation
# ---------------------------------------------------------------------------

def test_trade_parameters_rr_computed():
    entry, sl, tp1 = 1.10000, 1.09900, 1.10200  # 10 pip risk, 20 pip reward = RR 2.0
    t = TradeParameters("buy", entry, sl, tp1)
    assert t.rr == pytest.approx(2.0, abs=0.01)
