from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict

from .context import (
    business_id_ctx,
    call_sid_ctx,
    message_sid_ctx,
    request_id_ctx,
    trace_id_ctx,
)


class RequestContextFilter(logging.Filter):
    """Attach request correlation fields from contextvars when available."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = None
        try:
            rid = request_id_ctx.get()
        except Exception:
            rid = None
        record.request_id = rid or "-"

        try:
            trace_id = trace_id_ctx.get()
        except Exception:
            trace_id = None
        if trace_id:
            record.trace_id = trace_id

        try:
            business_id = business_id_ctx.get()
        except Exception:
            business_id = None
        if business_id:
            record.business_id = business_id

        try:
            call_sid = call_sid_ctx.get()
        except Exception:
            call_sid = None
        if call_sid:
            record.call_sid = call_sid

        try:
            message_sid = message_sid_ctx.get()
        except Exception:
            message_sid = None
        if message_sid:
            record.message_sid = message_sid
        return True


# Backwards-compatible alias used by older tests/imports.
RequestIdFilter = RequestContextFilter


def _ensure_request_context_filter(handler: logging.Handler) -> None:
    """Attach a single RequestContextFilter to the given handler."""

    if any(isinstance(f, RequestContextFilter) for f in handler.filters):
        return
    handler.addFilter(RequestContextFilter())


class JsonFormatter(logging.Formatter):
    """Lightweight JSON formatter for stdout logs."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "trace_id",
            "business_id",
            "call_sid",
            "message_sid",
        ):
            if hasattr(record, key):
                value = getattr(record, key)
                if value is not None:
                    payload[key] = value
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
            _ensure_request_context_filter(handler)
        return

    handler = logging.StreamHandler(sys.stdout)
    log_format = os.getenv("LOG_FORMAT", "plain").lower()
    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    handler.setFormatter(formatter)
    _ensure_request_context_filter(handler)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
