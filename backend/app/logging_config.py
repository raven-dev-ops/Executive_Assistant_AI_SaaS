from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict

from .context import request_id_ctx, business_id_ctx, call_sid_ctx, message_sid_ctx


class RequestIdFilter(logging.Filter):
    """Attach correlation fields from contextvars when available."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rid = request_id_ctx.get()
        except Exception:
            rid = None
        record.request_id = rid or "-"
        try:
            biz = business_id_ctx.get()
        except Exception:
            biz = None
        try:
            call_sid = call_sid_ctx.get()
        except Exception:
            call_sid = None
        try:
            msg_sid = message_sid_ctx.get()
        except Exception:
            msg_sid = None
        record.business_id = biz or "-"
        record.call_sid = call_sid or "-"
        record.message_sid = msg_sid or "-"
        return True


def _ensure_request_id_filter(handler: logging.Handler) -> None:
    """Attach a single RequestIdFilter to the given handler."""

    if any(isinstance(f, RequestIdFilter) for f in handler.filters):
        return
    handler.addFilter(RequestIdFilter())


class JsonFormatter(logging.Formatter):
    """Lightweight JSON formatter for stdout logs."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        service = os.getenv("LOG_SERVICE_NAME", "ai-telephony-backend")
        env = os.getenv("ENVIRONMENT", "dev")
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": service,
            "environment": env,
        }
        # Include request id if present (added by RequestIdFilter).
        if hasattr(record, "request_id"):
            payload["request_id"] = getattr(record, "request_id")
        if hasattr(record, "business_id"):
            payload["business_id"] = getattr(record, "business_id")
        if hasattr(record, "call_sid"):
            payload["call_sid"] = getattr(record, "call_sid")
        if hasattr(record, "message_sid"):
            payload["message_sid"] = getattr(record, "message_sid")
        # Include extra simple fields (ints/str/bool) if provided in log records.
        for key, value in record.__dict__.items():
            if key in payload or key.startswith("_"):
                continue
            if isinstance(value, (str, int, float, bool)):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Configure basic structured logging for the backend.

    This keeps things simple (stdout, single formatter) while including
    useful fields like level and logger name. In a real deployment,
    logs would typically be shipped to a central system.
    """
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            _ensure_request_id_filter(handler)
        return

    handler = logging.StreamHandler(sys.stdout)
    log_format = os.getenv("LOG_FORMAT", None)
    if log_format is None and os.getenv("ENVIRONMENT", "dev").lower() == "prod":
        log_format = "json"
    log_format = (log_format or "plain").lower()
    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s tenant=%(business_id)s call=%(call_sid)s msg=%(message_sid)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    handler.setFormatter(formatter)
    _ensure_request_id_filter(handler)
    root.addHandler(handler)
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        root.setLevel(level)
    except Exception:
        root.setLevel(logging.INFO)
