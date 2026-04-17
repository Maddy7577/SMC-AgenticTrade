"""CED Pipeline — orchestrates all detectors on every M1 close (C11).

Budget: < 500 ms per tick (NFR-P-01).
Persists events to DB and emits the CanonicalContext to an asyncio.Queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.detector.atr import atr
from app.detector.context import CanonicalContext
from app.detector.fvg import detect_fvgs, update_fvg_state
from app.detector.htf_bias import compute_htf_bias
from app.detector.kill_zone import current_kill_zone
from app.detector.mss import detect_mss
from app.detector.order_block import detect_order_blocks, mark_breaker_blocks
from app.detector.pd_zone import compute_pd_zone
from app.detector.smt_divergence import detect_smt_divergence
from app.detector.sweep import detect_sweeps
from app.detector.swings import detect_swings
from app.storage import db as _db
from app.storage.repositories import get_candles, insert_event
from config.instruments import PRIMARY, SMT_PAIR
from config.settings import TZ_IST

log = logging.getLogger(__name__)

# Number of recent candles loaded per timeframe for CED computation
_LOAD: dict[str, int] = {
    "M1": 200,
    "M5": 100,
    "M15": 60,
    "H1": 50,
    "H4": 30,
    "D": 30,
}

# Asian session in UTC: 05:30 IST = 00:00 UTC,  12:30 IST = 07:00 UTC
_ASIAN_START_UTC_H = 0
_ASIAN_END_UTC_H = 7


class CEDPipeline:
    def __init__(
        self,
        candle_queue: asyncio.Queue,
        context_queue: asyncio.Queue,
        db_path=_db.DB_PATH,
    ) -> None:
        self._in = candle_queue
        self._out = context_queue
        self._db_path = db_path
        # State: active FVGs (carries across ticks for state machine)
        self._active_fvgs: list = []

    async def run(self) -> None:
        log.info("CED pipeline started, waiting for candle triggers")
        while True:
            candle = await self._in.get()
            log.info("CED trigger received, building context")
            try:
                ctx = await asyncio.get_event_loop().run_in_executor(
                    None, self._build_context, candle
                )
                log.info("CED context built, pushing to strategy queue")
                await self._out.put(ctx)
            except Exception as exc:
                log.error("CED pipeline error", extra={"error": str(exc)})
            finally:
                self._in.task_done()

    def _build_context(self, trigger_candle: dict) -> CanonicalContext:
        t = trigger_candle.get("t") or datetime.now(tz=timezone.utc)
        if isinstance(t, str):
            t = datetime.fromisoformat(t)

        with _db.get_connection(self._db_path) as conn:
            m1 = get_candles(conn, PRIMARY, "M1", limit=_LOAD["M1"])
            m5 = get_candles(conn, PRIMARY, "M5", limit=_LOAD["M5"])
            m15 = get_candles(conn, PRIMARY, "M15", limit=_LOAD["M15"])
            h1 = get_candles(conn, PRIMARY, "H1", limit=_LOAD["H1"])
            h4 = get_candles(conn, PRIMARY, "H4", limit=_LOAD["H4"])
            d = get_candles(conn, PRIMARY, "D", limit=_LOAD["D"])
            gbp_m5 = get_candles(conn, SMT_PAIR, "M5", limit=_LOAD["M5"])

        # --- Swings ---
        swings = detect_swings(m1)

        # --- ATR ---
        atr_m1 = atr(m1)
        atr_m5 = atr(m5)
        atr_h1 = atr(h1)
        atr_h4 = atr(h4)

        # --- FVGs (multi-TF) ---
        new_fvgs = detect_fvgs(m1, PRIMARY, "M1") + detect_fvgs(m5, PRIMARY, "M5")
        # Update existing active FVG states with latest candle
        if m1:
            last_c = m1[-1]
            self._active_fvgs = [update_fvg_state(f, last_c) for f in self._active_fvgs]
        self._active_fvgs.extend(new_fvgs)
        # Prune fully_filled FVGs older than 200 candles (memory management)
        self._active_fvgs = [
            f for f in self._active_fvgs
            if f.state not in ("fully_filled",)
        ][-400:]

        # --- Order Blocks + Breakers ---
        obs = detect_order_blocks(m5, PRIMARY, "M5")
        obs = mark_breaker_blocks(obs, m5)

        # --- Sweeps ---
        asian_high, asian_low = _asian_range(m1, t)
        sweeps = detect_sweeps(m1, PRIMARY, d, asian_high=asian_high, asian_low=asian_low)

        # --- MSS ---
        mss_events = detect_mss(m1)

        # --- PD Zone ---
        pd_zone = compute_pd_zone(h4)

        # --- HTF Bias ---
        htf_bias = compute_htf_bias(d, h4)

        # --- Kill Zone ---
        kill_zone = current_kill_zone(t)

        # --- SMT ---
        smt = detect_smt_divergence(m5, gbp_m5)

        ctx = CanonicalContext(
            instrument=PRIMARY,
            tick_t=t,
            m1_candles=m1,
            m5_candles=m5,
            m15_candles=m15,
            h1_candles=h1,
            h4_candles=h4,
            d_candles=d,
            fvgs=list(self._active_fvgs),
            order_blocks=obs,
            swings=swings,
            sweeps=sweeps,
            mss_events=mss_events,
            pd_zone=pd_zone,
            htf_bias=htf_bias,
            kill_zone=kill_zone,
            smt_divergence=smt,
            atr_m1=atr_m1,
            atr_m5=atr_m5,
            atr_h1=atr_h1,
            atr_h4=atr_h4,
            asian_high=asian_high,
            asian_low=asian_low,
        )

        self._persist_events(ctx)
        return ctx

    def _persist_events(self, ctx: CanonicalContext) -> None:
        with _db.get_connection(self._db_path) as conn:
            for fvg in ctx.fvgs[-10:]:  # only newly detected
                insert_event(
                    conn,
                    t=ctx.tick_t,
                    instrument=ctx.instrument,
                    timeframe=fvg.timeframe,
                    event_type="fvg",
                    direction=fvg.direction,
                    payload={
                        "top": fvg.top,
                        "bottom": fvg.bottom,
                        "midpoint": fvg.midpoint,
                        "state": fvg.state,
                        "size_pips": fvg.size_pips,
                    },
                )
            for sw in ctx.sweeps[-5:]:
                insert_event(
                    conn,
                    t=ctx.tick_t,
                    instrument=ctx.instrument,
                    timeframe="M1",
                    event_type="sweep",
                    direction=sw.direction,
                    payload={
                        "swept_level": sw.swept_level,
                        "level_type": sw.level_type,
                        "wick_extreme": sw.wick_extreme,
                    },
                )
            if ctx.mss_events:
                m = ctx.mss_events[-1]
                insert_event(
                    conn,
                    t=ctx.tick_t,
                    instrument=ctx.instrument,
                    timeframe="M1",
                    event_type="mss",
                    direction=m.direction,
                    payload={
                        "broken_level": m.broken_level,
                        "displacement": m.displacement,
                    },
                )
            conn.commit()


def _asian_range(
    m1_candles: list[dict],
    current_t: datetime,
) -> tuple[float | None, float | None]:
    """Compute today's Asian session high/low from M1 candles."""
    ist = current_t.astimezone(TZ_IST)
    session_candles = []
    for c in m1_candles:
        ct = c["t"]
        if isinstance(ct, str):
            from datetime import datetime as _dt
            ct = _dt.fromisoformat(ct)
        ct_ist = ct.astimezone(TZ_IST)
        same_day = ct_ist.date() == ist.date()
        in_window = 5 * 60 + 30 <= ct_ist.hour * 60 + ct_ist.minute <= 12 * 60 + 30
        if same_day and in_window:
            session_candles.append(c)
    if not session_candles:
        return None, None
    return max(c["h"] for c in session_candles), min(c["l"] for c in session_candles)
