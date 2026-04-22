"""Strategy orchestrator — subscribes to the CED context queue, dispatches to
enabled strategies, and writes signals + agent scores to the database (D9, FR-S-10).

Each strategy is isolated in a try/except so a bug in one doesn't kill the engine (NFR-R-04).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from app.detector.context import CanonicalContext
from app.storage import db as _db
from app.storage.repositories import insert_agent_score, insert_signal
from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.strategy_01_unicorn import UnicornModelStrategy
from app.strategies.strategy_02_judas import JudasSwingStrategy
from app.strategies.strategy_03_confirmation import ConfirmationModelStrategy
from app.strategies.strategy_04_silver_bullet import SilverBulletStrategy
from app.strategies.strategy_05_nested_fvg import NestedFVGStrategy
from app.strategies.strategy_06_ifvg import IFVGStrategy
from app.strategies.strategy_07_ote_fvg import OTEFVGStrategy
from app.strategies.strategy_08_rejection_block import RejectionBlockStrategy
from app.strategies.strategy_09_mmm import MMMStrategy
from app.strategies.strategy_10_po3 import PO3Strategy
from app.strategies.strategy_11_propulsion import PropulsionBlockStrategy
from app.strategies.strategy_12_vacuum import VacuumBlockStrategy
from app.strategies.strategy_13_reclaimed_fvg import ReclaimedFVGStrategy
from app.strategies.strategy_14_cisd import CISDStrategy
from app.strategies.strategy_15_bpr_ob import BPRInOBStrategy

log = logging.getLogger(__name__)

ALL_STRATEGIES: list[BaseStrategy] = [
    # Phase 1
    ConfirmationModelStrategy(),
    SilverBulletStrategy(),
    JudasSwingStrategy(),
    UnicornModelStrategy(),
    IFVGStrategy(),
    # Phase 2
    NestedFVGStrategy(),
    OTEFVGStrategy(),
    RejectionBlockStrategy(),
    MMMStrategy(),
    PO3Strategy(),
    PropulsionBlockStrategy(),
    VacuumBlockStrategy(),
    ReclaimedFVGStrategy(),
    CISDStrategy(),
    BPRInOBStrategy(),
]


class StrategyOrchestrator:
    def __init__(
        self,
        context_queue: asyncio.Queue,
        signal_queue: asyncio.Queue,
        db_path=_db.DB_PATH,
        strategies: list[BaseStrategy] | None = None,
    ) -> None:
        self._ctx_q = context_queue
        self._sig_q = signal_queue
        self._db_path = db_path
        self._strategies = strategies if strategies is not None else [s for s in ALL_STRATEGIES if s.enabled]

    async def run(self) -> None:
        while True:
            ctx: CanonicalContext = await self._ctx_q.get()
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._evaluate_all, ctx
                )
            except Exception as exc:
                log.error("orchestrator error", extra={"error": str(exc)})
            finally:
                self._ctx_q.task_done()

    def _evaluate_all(self, ctx: CanonicalContext) -> None:
        t0 = time.perf_counter()
        for strategy in self._strategies:
            if not strategy.enabled:
                continue
            try:
                result = strategy.evaluate(ctx)
                evidence = strategy.build_evidence(ctx)
                signal_id = self._persist_result(result, ctx.tick_t, evidence=evidence)
                if signal_id:
                    self._sig_q.put_nowait((signal_id, result))
                    log.info(
                        "signal produced",
                        extra={
                            "strategy": strategy.strategy_id,
                            "verdict": result.verdict,
                            "confidence": result.confidence,
                            "signal_id": signal_id,
                        },
                    )
            except Exception as exc:
                log.error(
                    "strategy evaluation failed",
                    extra={"strategy": strategy.strategy_id, "error": str(exc)},
                )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > 500:
            log.warning("strategy pass over budget", extra={"elapsed_ms": round(elapsed_ms, 1), "budget_ms": 500})
        else:
            log.info("strategy pass complete", extra={"elapsed_ms": round(elapsed_ms, 1)})

    def _persist_result(self, result: StrategyResult, t: datetime, evidence: dict | None = None) -> int | None:
        trade = result.trade
        with _db.get_connection(self._db_path) as conn:
            signal_id = insert_signal(
                conn,
                t=t,
                strategy_id=result.strategy_id,
                verdict=result.verdict,
                confidence=result.confidence,
                probability=result.probability,
                direction=trade.direction if trade else None,
                entry=trade.entry if trade else None,
                sl=trade.sl if trade else None,
                tp1=trade.tp1 if trade else None,
                tp2=trade.tp2 if trade else None,
                tp3=trade.tp3 if trade else None,
                rr=trade.rr if trade else None,
                signature=result.signature,
                gate_result="pending",
                payload={"rejection_reasons": result.rejection_reasons, "evidence": evidence or {}},
            )
            if signal_id is None:
                return None  # duplicate

            for op in result.agent_opinions:
                insert_agent_score(
                    conn,
                    signal_id=signal_id,
                    agent_id=op.agent_id,
                    score=op.score,
                    verdict=op.verdict,
                    reasons=op.reasons,
                    evidence=op.evidence,
                )
            conn.commit()
        return signal_id
