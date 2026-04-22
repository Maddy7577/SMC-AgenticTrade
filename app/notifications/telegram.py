"""Telegram alert sender for VALID/WAIT trade signals."""

from __future__ import annotations

import logging
import urllib.request
import urllib.parse
import json

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)

_EMOJI = {"VALID": "✅", "WAIT": "⏳"}
_DIR_EMOJI = {"buy": "🟢", "sell": "🔴"}


def send_signal_alert(
    verdict: str,
    strategy_name: str,
    direction: str | None,
    entry: float | None,
    sl: float | None,
    tp1: float | None,
    rr: float | None,
    confidence: float | None,
) -> None:
    """Send a Telegram message for a published signal. Silently skips if not configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    dir_str = direction.upper() if direction else "—"
    emoji = _EMOJI.get(verdict, "📊")
    dir_emoji = _DIR_EMOJI.get(direction, "")

    lines = [
        f"{emoji} *{verdict}* — {strategy_name}",
        f"{dir_emoji} Direction: *{dir_str}*",
    ]
    if entry is not None:
        lines.append(f"Entry:  `{entry:.5f}`")
    if sl is not None:
        lines.append(f"SL:     `{sl:.5f}`")
    if tp1 is not None:
        lines.append(f"TP1:    `{tp1:.5f}`")
    if rr is not None:
        lines.append(f"RR:     `{rr:.1f}`")
    if confidence is not None:
        lines.append(f"Confidence: `{confidence:.0f}/100`")

    text = "\n".join(lines)
    _send(text)


def _send(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                log.warning("telegram send failed", extra={"status": resp.status})
    except Exception as exc:
        log.warning("telegram send error", extra={"error": str(exc)})
