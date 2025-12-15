from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any, Dict, List

from ..context import business_id_ctx, call_sid_ctx, message_sid_ctx
from ..metrics import metrics

logger = logging.getLogger(__name__)


class SecurityEventLog:
    """Thread-safe recent security events for admin visibility."""

    def __init__(self, max_items: int = 500) -> None:
        self._max_items = max_items
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []

    def append(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_items:
                # Drop oldest to bound memory.
                self._events = self._events[-self._max_items :]

    def list(
        self, *, business_id: str | None = None, since: datetime | None = None, limit: int = 200
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._events)
        if business_id:
            items = [e for e in items if e.get("business_id") == business_id]
        if since:
            items = [e for e in items if e.get("created_at_dt") and e["created_at_dt"] >= since]
        items.sort(key=lambda e: e.get("created_at_dt") or datetime.min, reverse=True)
        return [
            {
                "event": e.get("event"),
                "detail": e.get("detail"),
                "business_id": e.get("business_id"),
                "call_sid": e.get("call_sid"),
                "message_sid": e.get("message_sid"),
                "created_at": e.get("created_at"),
                "metadata": e.get("metadata") or {},
            }
            for e in items[:limit]
        ]


security_event_log = SecurityEventLog()


def record_security_event(
    event: str, detail: str | None = None, metadata: Dict[str, Any] | None = None
) -> None:
    """Increment a security event counter and emit a structured log entry."""
    if not event:
        return
    metrics.security_events[event] = metrics.security_events.get(event, 0) + 1
    # Enrich with correlation context when available.
    business_id = (metadata or {}).get("business_id") or business_id_ctx.get(None)
    call_sid = (metadata or {}).get("call_sid") or call_sid_ctx.get(None)
    message_sid = (metadata or {}).get("message_sid") or message_sid_ctx.get(None)

    extra: Dict[str, Any] = {
        "security_event": event,
        "security_event_count": metrics.security_events[event],
    }
    if detail:
        extra["detail"] = detail
    if business_id:
        extra["meta_business_id"] = business_id
    if call_sid:
        extra["meta_call_sid"] = call_sid
    if message_sid:
        extra["meta_message_sid"] = message_sid
    if metadata:
        for key, value in metadata.items():
            if value is None or key in {"business_id", "call_sid", "message_sid"}:
                continue
            extra[f"meta_{key}"] = value
    created_at = datetime.now(UTC)
    security_event_log.append(
        {
            "event": event,
            "detail": detail,
            "business_id": business_id,
            "call_sid": call_sid,
            "message_sid": message_sid,
            "metadata": metadata or {},
            "created_at": created_at.isoformat(),
            "created_at_dt": created_at,
        }
    )
    try:
        logger.info("security_event", extra=extra)
    except Exception:
        # Do not break request handling if structured logging fails.
        logger.debug("security_event_log_failed", exc_info=True, extra=extra)
