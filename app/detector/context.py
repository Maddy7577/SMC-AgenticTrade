"""CanonicalContext dataclass — snapshot of all CED outputs consumed by agents (C12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.detector.fvg import FVG
    from app.detector.htf_bias import HTFBias
    from app.detector.kill_zone import KillZoneLabel
    from app.detector.mss import MSSEvent
    from app.detector.order_block import OrderBlock
    from app.detector.pd_zone import PDZone
    from app.detector.smt_divergence import SMTResult
    from app.detector.sweep import SweepEvent
    from app.detector.swings import SwingPoint


@dataclass
class CanonicalContext:
    # Metadata
    instrument: str
    tick_t: datetime   # UTC time of the M1 candle that triggered this run

    # Candle data
    m1_candles: list[dict] = field(default_factory=list)
    m5_candles: list[dict] = field(default_factory=list)
    m15_candles: list[dict] = field(default_factory=list)
    h1_candles: list[dict] = field(default_factory=list)
    h4_candles: list[dict] = field(default_factory=list)
    d_candles: list[dict] = field(default_factory=list)

    # CED outputs
    fvgs: list[FVG] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    swings: list[SwingPoint] = field(default_factory=list)
    sweeps: list[SweepEvent] = field(default_factory=list)
    mss_events: list[MSSEvent] = field(default_factory=list)

    pd_zone: PDZone | None = None
    htf_bias: HTFBias = "neutral"
    kill_zone: KillZoneLabel = "none"
    smt_divergence: SMTResult = "none"

    # ATR values per timeframe
    atr_m1: float | None = None
    atr_m5: float | None = None
    atr_h1: float | None = None
    atr_h4: float | None = None

    # Asian session range (used by Judas Swing)
    asian_high: float | None = None
    asian_low: float | None = None

    # Live price at context build time
    current_price: float | None = None
    current_spread_pips: float | None = None

    # Phase 2 CED extensions (FR-C2-09)
    fib_levels: dict[float, float] = field(default_factory=dict)
    active_gaps: list[dict] = field(default_factory=list)
    amd_phase: str = "Unknown"
    mmm_phase: int = 0
    fvg_test_history: dict[str, list[dict]] = field(default_factory=dict)
