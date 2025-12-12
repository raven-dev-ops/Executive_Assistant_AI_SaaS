from __future__ import annotations

import logging
import sys

from .context import request_id_ctx


class RequestIdFilter(logging.Filter):
    """Attach request_id from contextvar when available."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rid = request_id_ctx.get()
        except Exception:
            rid = None
        record.request_id = rid or "-"
        return True


def _ensure_request_id_filter(handler: logging.Handler) -> None:
    """Attach a single RequestIdFilter to the given handler."""

    if any(isinstance(f, RequestIdFilter) for f in handler.filters):
        return
    handler.addFilter(RequestIdFilter())


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
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    _ensure_request_id_filter(handler)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
