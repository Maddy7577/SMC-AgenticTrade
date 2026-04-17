"""Server-Sent Events broadcaster (G3, NFR-P-04).

Clients subscribe to /stream/signals and receive JSON events when
new signals are published.
"""

from __future__ import annotations

import json
import queue
import threading

from flask import Blueprint, Response, stream_with_context

sse_bp = Blueprint("sse", __name__)

# Thread-safe queue; main.py pushes events here on publish
_event_queue: queue.Queue = queue.Queue(maxsize=200)
_subscribers: list[queue.Queue] = []
_lock = threading.Lock()


def push_signal_event(signal_id: int, verdict: str, strategy_id: str) -> None:
    """Called from the engine when a signal is published."""
    event = json.dumps({"signal_id": signal_id, "verdict": verdict, "strategy_id": strategy_id})
    with _lock:
        for sub in list(_subscribers):
            try:
                sub.put_nowait(event)
            except queue.Full:
                pass


@sse_bp.route("/stream/signals")
def stream_signals():
    def generate():
        sub: queue.Queue = queue.Queue(maxsize=50)
        with _lock:
            _subscribers.append(sub)
        try:
            yield "retry: 15000\n\n"  # tell browser to reconnect after 15s
            while True:
                try:
                    data = sub.get(timeout=30)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _lock:
                if sub in _subscribers:
                    _subscribers.remove(sub)

    return Response(stream_with_context(generate()), content_type="text/event-stream")
