"""Flask application factory (FR-UI-01).

Binds to 127.0.0.1 only. Dark theme. IST timezone filter for Jinja.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Flask

from config.settings import FLASK_DEBUG, TZ_IST


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = "smc-local-only"
    app.config["DEBUG"] = FLASK_DEBUG

    # Jinja IST filter (FR-UI-05)
    @app.template_filter("ist")
    def to_ist(value: str | datetime) -> str:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(TZ_IST).strftime("%d %b %Y %H:%M IST")

    @app.template_filter("ist_tooltip")
    def to_ist_tooltip(value: str | datetime) -> str:
        """Returns UTC string for tooltip."""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    from app.dashboard.routes.health import health_bp
    from app.dashboard.routes.segment_1_performance import seg1_bp
    from app.dashboard.routes.segment_2_strategies import seg2_bp
    from app.dashboard.routes.segment_3_details import seg3_bp
    from app.dashboard.routes.sse import sse_bp

    app.register_blueprint(seg1_bp)
    app.register_blueprint(seg2_bp)
    app.register_blueprint(seg3_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(sse_bp)

    return app
