"""Base interfaces for agents and strategies (FR-S-03).

All agents are deterministic Python — no LLM calls inside the debate loop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["VALID", "WAIT", "NO_TRADE"]
AgentVerdict = Literal["support", "oppose", "neutral"]


@dataclass
class AgentOpinion:
    agent_id: str                       # opp1 / opp2 / risk1 / risk2
    score: float                        # 0–100
    verdict: AgentVerdict
    reasons: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


@dataclass
class TradeParameters:
    direction: Literal["buy", "sell"]
    entry: float
    sl: float
    tp1: float
    tp2: float | None = None
    tp3: float | None = None
    rr: float = 0.0

    def __post_init__(self) -> None:
        if self.entry and self.sl and self.tp1:
            risk = abs(self.entry - self.sl)
            reward = abs(self.tp1 - self.entry)
            self.rr = round(reward / risk, 2) if risk > 0 else 0.0


@dataclass
class StrategyResult:
    strategy_id: str
    verdict: Verdict
    confidence: float          # 0–100
    probability: float         # 0–100
    agent_opinions: list[AgentOpinion] = field(default_factory=list)
    trade: TradeParameters | None = None
    signature: str | None = None
    rejection_reasons: list[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Single agent in the 4-agent debate."""

    agent_id: str  # must be set in subclass: opp1 / opp2 / risk1 / risk2

    @abstractmethod
    def evaluate(self, context) -> AgentOpinion:  # context: CanonicalContext
        ...


class BaseStrategy(ABC):
    """Strategy composed of 4 agents."""

    strategy_id: str   # e.g. '03_confirmation'
    strategy_name: str
    enabled: bool = True

    @property
    @abstractmethod
    def agents(self) -> list[BaseAgent]:
        ...

    @abstractmethod
    def build_trade_parameters(self, context) -> TradeParameters | None:
        """Compute entry / SL / TP from current context. Return None if not computable."""
        ...

    @abstractmethod
    def build_signature(self, context) -> str | None:
        """Return canonical cluster signature or None if setup not present."""
        ...
