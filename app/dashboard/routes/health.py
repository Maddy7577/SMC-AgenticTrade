"""Health endpoint (NFR-O-03, FR-D-09, G9)."""

from __future__ import annotations

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)

# Stream + Finnhub client injected at startup by main.py
_stream = None
_finnhub = None


def init_health(stream, finnhub) -> None:
    global _stream, _finnhub
    _stream = stream
    _finnhub = finnhub


@health_bp.route("/health")
def health():
    from app.ingestion.health import build_health_snapshot
    if _stream is None or _finnhub is None:
        return jsonify({"ok": False, "error": "not initialised"}), 503
    snapshot = build_health_snapshot(_stream, _finnhub)
    return jsonify(snapshot)
