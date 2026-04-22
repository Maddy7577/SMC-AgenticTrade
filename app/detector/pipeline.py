"""CED Pipeline — orchestrates all detectors on every M1 close (C11).

Budget: < 500 ms per tick (NFR-P-01).
Persists events to DB and emits the CanonicalContext to an asyncio.Queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from app.detector.amd_phase import detect_manipulation_event, get_amd_phase
from app.detector.atr import atr
from app.detector.context import CanonicalContext
from app.detector.fibonacci import compute_fib_levels
from app.detector.fvg import detect_fvgs, update_fvg_ce_tests, update_fvg_state
from app.detector.gap_detector import detect_gaps, update_gap_fill_status
from app.detector.htf_bias import compute_htf_bias
from app.detector.kill_zone import current_kill_zone
from app.detector.mmm_phase import detect_mmm_phase
from app.detector.mss import detect_mss
from app.detector.order_block import detect_order_blocks, mark_breaker_blocks
from app.detector.pd_zone import compute_pd_zone
from app.detector.smt_divergence import detect_smt_divergence
from app.detector.sweep import detect_sweeps
from app.detector.swings import detect_swings
from app.storage import db as _db
from app.storage.repositories import get_candles, get_setting, insert_event, set_setting
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
        # Active gaps (carries across ticks for fill tracking)
        self._active_gaps: list[dict] = []
        # Whether FVG CE-test history has been rebuilt from DB on startup
        self._fvg_tests_rebuilt: bool = False
        # Dedup keys — prevent re-inserting events that haven't changed
        self._seen_sweep_keys: set[str] = set()
        self._last_mss_key: str = ""
        self._last_fib_key: str = ""
        self._seen_gap_ids: set[str] = set()

    async def run(self) -> None:
        log.info("CED pipeline started, waiting for candle triggers")
        while True:
            candle = await self._in.get()
            log.info("CED trigger received, building context")
            try:
                t0 = time.perf_counter()
                ctx = await asyncio.get_event_loop().run_in_executor(
                    None, self._build_context, candle
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if elapsed_ms > 700:
                    log.warning("CED tick over budget", extra={"elapsed_ms": round(elapsed_ms, 1), "budget_ms": 700})
                else:
                    log.info("CED tick complete", extra={"elapsed_ms": round(elapsed_ms, 1)})
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
        new_fvgs = (
            detect_fvgs(m1, PRIMARY, "M1")
            + detect_fvgs(m5, PRIMARY, "M5")
            + detect_fvgs(m15, PRIMARY, "M15")
        )
        # Update existing active FVG states with latest candle
        _prev_test_counts: dict[str, int] = {f.id: len(f.tests) for f in self._active_fvgs}
        if m1:
            last_c = m1[-1]
            self._active_fvgs = [update_fvg_state(f, last_c) for f in self._active_fvgs]
            self._active_fvgs = update_fvg_ce_tests(self._active_fvgs, last_c)
        # Collect new CE-test entries for event persistence
        _new_ce_tests: list[tuple] = []
        for f in self._active_fvgs:
            prev = _prev_test_counts.get(f.id, 0)
            if len(f.tests) > prev:
                _new_ce_tests.extend((f, entry) for entry in f.tests[prev:])
        self._active_fvgs.extend(new_fvgs)
        # Prune fully_filled FVGs older than 200 candles (memory management)
        self._active_fvgs = [
            f for f in self._active_fvgs
            if f.state not in ("fully_filled",)
        ][-400:]

        # P2: Rebuild FVG CE-test history from DB on first tick after restart
        if not self._fvg_tests_rebuilt:
            self._fvg_tests_rebuilt = True
            self._rebuild_fvg_tests_from_db()

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

        # --- Phase 2: Gaps ---
        new_gaps = detect_gaps(h1)
        _prev_gap_filled: dict[str, bool] = {g["id"]: g.get("fully_filled", False) for g in self._active_gaps}
        if h1:
            self._active_gaps = update_gap_fill_status(self._active_gaps, h1[-1])
        _newly_filled_gaps = [
            g for g in self._active_gaps
            if g.get("fully_filled") and not _prev_gap_filled.get(g["id"], False)
        ]
        # Add newly detected gaps that aren't already tracked
        existing_ids = {g["id"] for g in self._active_gaps}
        truly_new_gaps = [g for g in new_gaps if g["id"] not in existing_ids]
        self._active_gaps.extend(truly_new_gaps)
        active_gaps = [g for g in self._active_gaps if not g["fully_filled"]]

        # --- Phase 2: AMD phase ---
        amd_phase = get_amd_phase(t, asian_high, asian_low, m5, htf_bias)
        _manip_event = (
            detect_manipulation_event(m5, asian_high, asian_low, htf_bias)
            if asian_high and asian_low else None
        )

        # --- Phase 2: MMM phase ---
        mmm_data = detect_mmm_phase(h4, d)
        mmm_phase_int = mmm_data["phase"]
        # Persist MMM phase change to settings KV + events table
        with _db.get_connection(self._db_path) as conn:
            prev_mmm = get_setting(conn, "mmm_phase", "0")
            if str(mmm_phase_int) != prev_mmm:
                set_setting(conn, "mmm_phase", str(mmm_phase_int))
                insert_event(
                    conn,
                    t=t,
                    instrument=PRIMARY,
                    timeframe="H4",
                    event_type="mmm_phase_change",
                    direction=mmm_data.get("direction"),
                    payload={"prev_phase": int(prev_mmm), "new_phase": mmm_phase_int},
                )
                conn.commit()

        # --- Phase 2: Fib levels (from last H4 swing) ---
        fib_levels: dict[float, float] = {}
        if len(h4) >= 3 and atr_h4:
            fib_levels = _compute_impulse_fib(h4, atr_h4, htf_bias)

        # --- Phase 2: FVG test history ---
        fvg_test_history: dict[str, list[dict]] = {
            f.id: f.tests for f in self._active_fvgs if f.tests
        }

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
            fib_levels=fib_levels,
            active_gaps=active_gaps,
            amd_phase=amd_phase,
            mmm_phase=mmm_phase_int,
            fvg_test_history=fvg_test_history,
        )

        self._persist_events(ctx, _new_ce_tests, _newly_filled_gaps, _manip_event, new_fvgs, truly_new_gaps)
        return ctx

    def _rebuild_fvg_tests_from_db(self) -> None:
        """Load persisted fvg_ce_test events and restore tests on active FVGs."""
        try:
            with _db.get_connection(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT payload FROM events WHERE event_type = 'fvg_ce_test' ORDER BY t"
                ).fetchall()
            historical: dict[tuple, list] = {}
            for row in rows:
                p = json.loads(row[0])
                key = (p.get("c1_t"), p.get("timeframe"), p.get("instrument"))
                if None not in key:
                    historical.setdefault(key, []).append({
                        "t": p["test_t"],
                        "respected": p["respected"],
                        "close_price": p["close_price"],
                    })
            for fvg in self._active_fvgs:
                key = (fvg.c1_t, fvg.timeframe, fvg.instrument)
                if key in historical and not fvg.tests:
                    fvg.tests = historical[key]
        except Exception as exc:
            log.warning("FVG CE-test rebuild failed", extra={"error": str(exc)})

    def _persist_events(
        self,
        ctx: CanonicalContext,
        new_ce_tests: list = (),
        newly_filled_gaps: list = (),
        manip_event: dict | None = None,
        new_fvgs: list | None = None,
        truly_new_gaps: list | None = None,
    ) -> None:
        with _db.get_connection(self._db_path) as conn:
            # Only newly detected FVGs (not all active ones)
            for fvg in (new_fvgs or []):
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
            # Only sweeps not already persisted this session
            for sw in ctx.sweeps[-5:]:
                key = f"{sw.direction}:{sw.swept_level}:{sw.level_type}"
                if key not in self._seen_sweep_keys:
                    self._seen_sweep_keys.add(key)
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
            # Only persist MSS when it changes
            if ctx.mss_events:
                m = ctx.mss_events[-1]
                mss_key = f"{m.direction}:{m.broken_level}"
                if mss_key != self._last_mss_key:
                    self._last_mss_key = mss_key
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
            # Only newly detected gaps (not all active ones each tick)
            for gap in (truly_new_gaps or []):
                insert_event(
                    conn,
                    t=ctx.tick_t,
                    instrument=ctx.instrument,
                    timeframe="H1",
                    event_type="gap_formed",
                    direction=gap.get("direction"),
                    payload={
                        "gap_type": gap["gap_type"],
                        "top": gap["top"],
                        "bottom": gap["bottom"],
                        "ce": gap["ce"],
                    },
                )
            # Only persist fibonacci when levels change
            if ctx.fib_levels:
                fib_key = str(sorted(ctx.fib_levels.items()))
                if fib_key != self._last_fib_key:
                    self._last_fib_key = fib_key
                    insert_event(
                        conn,
                        t=ctx.tick_t,
                        instrument=ctx.instrument,
                        timeframe="H4",
                        event_type="fibonacci_impulse",
                        direction=ctx.htf_bias if ctx.htf_bias != "neutral" else None,
                        payload={"fib_levels": {str(k): v for k, v in ctx.fib_levels.items()}},
                    )
            # Phase 2: fvg_ce_test events (FR-C2-10)
            for fvg, test in new_ce_tests:
                insert_event(
                    conn,
                    t=ctx.tick_t,
                    instrument=ctx.instrument,
                    timeframe=fvg.timeframe,
                    event_type="fvg_ce_test",
                    direction=fvg.direction,
                    payload={
                        "fvg_id": fvg.id,
                        "c1_t": fvg.c1_t,
                        "instrument": fvg.instrument,
                        "timeframe": fvg.timeframe,
                        "test_t": test["t"],
                        "respected": test["respected"],
                        "close_price": test["close_price"],
                        "fvg_top": fvg.top,
                        "fvg_bottom": fvg.bottom,
                        "fvg_ce": fvg.ce,
                    },
                )
            # Phase 2: gap_filled events
            for gap in newly_filled_gaps:
                insert_event(
                    conn,
                    t=ctx.tick_t,
                    instrument=ctx.instrument,
                    timeframe="H1",
                    event_type="gap_filled",
                    direction=gap.get("direction"),
                    payload={
                        "gap_id": gap["id"],
                        "gap_type": gap["gap_type"],
                        "top": gap["top"],
                        "bottom": gap["bottom"],
                        "ce": gap["ce"],
                    },
                )
            # Phase 2: amd_manipulation_detected event
            if manip_event:
                insert_event(
                    conn,
                    t=ctx.tick_t,
                    instrument=ctx.instrument,
                    timeframe="M5",
                    event_type="amd_manipulation_detected",
                    direction=manip_event.get("direction"),
                    payload=manip_event,
                )
            conn.commit()


def _compute_impulse_fib(
    h4_candles: list[dict],
    atr_h4: float,
    htf_bias: str,
) -> dict[float, float]:
    """Compute fib levels from the most recent qualifying H4 impulse leg."""
    if len(h4_candles) < 5 or atr_h4 <= 0:
        return {}
    # Find swing high and low from last 20 h4 candles
    recent = h4_candles[-20:]
    swing_high = max(c["h"] for c in recent)
    swing_low = min(c["l"] for c in recent)
    leg_size = swing_high - swing_low
    # Only compute if impulse is meaningful (≥ 3× ATR)
    if leg_size < 3 * atr_h4:
        return {}
    direction = htf_bias if htf_bias in ("bullish", "bearish") else "bullish"
    # Use body-to-body: find candle highs/lows from open/close
    swing_high_body = max(max(c["o"], c["c"]) for c in recent)
    swing_low_body = min(min(c["o"], c["c"]) for c in recent)
    return compute_fib_levels(swing_high_body, swing_low_body, direction)


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
