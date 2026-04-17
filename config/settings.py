"""Central configuration — all tunables in one place.

Load order: defaults here → overridden by .env values where applicable.
Never import API keys directly; always use the property accessors below.
"""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------
TZ_IST = ZoneInfo("Asia/Kolkata")
TZ_UTC = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# OANDA
# ---------------------------------------------------------------------------
OANDA_API_TOKEN: str = os.environ.get("OANDA_API_TOKEN", "")
OANDA_ACCOUNT_ID: str = os.environ.get("OANDA_ACCOUNT_ID", "")
OANDA_ENVIRONMENT: str = os.environ.get("OANDA_ENVIRONMENT", "practice")

# ---------------------------------------------------------------------------
# Finnhub
# ---------------------------------------------------------------------------
FINNHUB_API_KEY: str = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_POLL_INTERVAL_SECONDS: int = 900  # 15 minutes

# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-2.5-flash"
GEMINI_TIMEOUT_SECONDS: int = 5
GEMINI_NARRATIVE_MIN_WORDS: int = 80
GEMINI_NARRATIVE_MAX_WORDS: int = 150

# ---------------------------------------------------------------------------
# Timeframes ingested (OANDA granularity codes)
# ---------------------------------------------------------------------------
TIMEFRAMES: list[str] = ["M1", "M5", "M15", "H1", "H4", "D"]
BACKFILL_DAYS_INTRADAY: int = 30   # M1 / M5 / M15
BACKFILL_DAYS_DAILY: int = 365     # H1 / H4 / D

# ---------------------------------------------------------------------------
# Signal thresholds (FR-S-09, FR-G-01/02)
# ---------------------------------------------------------------------------
CONFIDENCE_VALID_THRESHOLD: float = 75.0
CONFIDENCE_WAIT_THRESHOLD: float = 65.0
RR_FLOOR: float = 2.0

# ---------------------------------------------------------------------------
# Confluence boost (FR-CL-04)  cluster_size -> additive confidence boost
# ---------------------------------------------------------------------------
CONFLUENCE_BOOST: dict[int, float] = {
    1: 0.0,
    2: 10.0,
    3: 15.0,
}
CONFLUENCE_BOOST_CAP: float = 20.0   # hard ceiling regardless of cluster size

# ---------------------------------------------------------------------------
# Decision gate counters (FR-G-05/06/08)
# ---------------------------------------------------------------------------
MAX_DAILY_LOSSES: int = 2
MAX_MONTHLY_TRADES: int = 15
POST_STOPLOSS_COOLING_MINUTES: int = 20
NEWS_BLACKOUT_MINUTES: int = 30      # ±30 min around high-impact events

# ---------------------------------------------------------------------------
# Spread gate (FR-G-07) — in pips
# ---------------------------------------------------------------------------
MAX_SPREAD_PIPS: float = 1.5

# ---------------------------------------------------------------------------
# Kill zone windows in IST (24h format, inclusive both ends)
# Labels follow the Silver Bullet / London / NY convention from source docs.
# ---------------------------------------------------------------------------
KILL_ZONES_IST: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    # (start_hour, start_min), (end_hour, end_min)
    "asian_session":        ((5, 30),  (12, 30)),
    "london_kz":            ((12, 30), (15, 30)),
    "silver_bullet_london": ((13, 30), (14, 30)),
    "ny_kz":                ((17, 30), (20, 30)),
    "silver_bullet_ny_am":  ((20, 30), (21, 30)),
    "silver_bullet_ny_pm":  ((0, 30),  (1, 30)),
}

# ---------------------------------------------------------------------------
# CED parameters
# ---------------------------------------------------------------------------
FVG_MIN_PIPS: float = 5.0           # minimum FVG size (FR-C-02)
EQH_EQL_TOLERANCE_PIPS: float = 5.0  # equal high/low tolerance (FR-C-06)
OB_DISPLACEMENT_ATR_MULTIPLIER: float = 2.0  # (FR-C-04)
SMT_LOOKBACK_CANDLES_M5: int = 50   # (FR-C-11)
SWING_LOOKBACK: int = 10            # bars each side for swing detection

# ---------------------------------------------------------------------------
# Probability formula weights (plan §Ambiguities #1)
# ---------------------------------------------------------------------------
PROB_AGREEMENT_RANGE: tuple[float, float] = (0.6, 1.0)
CONFLUENCE_PROB_MAP: dict[int, float] = {1: 1.0, 2: 1.10, 3: 1.15, 4: 1.20}

# ---------------------------------------------------------------------------
# OANDA reconnect backoff (FR-D-06) — seconds
# ---------------------------------------------------------------------------
RECONNECT_BACKOFF_SEQUENCE: list[int] = [1, 2, 4, 8, 16, 30]

# ---------------------------------------------------------------------------
# Logging (NFR-O-01/02)
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE: str = "logs/smc.log"
LOG_MAX_BYTES: int = 10 * 1024 * 1024   # 10 MB
LOG_BACKUP_COUNT: int = 5

# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------
FLASK_HOST: str = "127.0.0.1"
FLASK_PORT: int = int(os.environ.get("FLASK_PORT", "8010"))
FLASK_DEBUG: bool = False
SSE_RETRY_MS: int = 15_000   # 15-second SSE reconnect hint to browser
