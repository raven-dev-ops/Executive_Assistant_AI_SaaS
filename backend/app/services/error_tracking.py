from __future__ import annotations

import logging
import os
from typing import Any, Dict

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
except Exception:  # pragma: no cover - sentry is optional
    sentry_sdk = None  # type: ignore
    FastApiIntegration = object  # type: ignore

from ..context import business_id_ctx, call_sid_ctx, message_sid_ctx, request_id_ctx

logger = logging.getLogger(__name__)


def init_sentry(app: Any = None) -> None:
    """Initialize Sentry only when DSN is provided and SDK is available."""

    dsn = os.getenv("SENTRY_DSN")
    if not dsn or sentry_sdk is None:
        return

    traces_sample_rate = 0.0
    try:
        traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0"))
    except Exception:
        traces_sample_rate = 0.0

    def _before_send(event: Dict[str, Any], hint: Any) -> Dict[str, Any] | None:
        # Scrub auth headers pre-flight.
        req = event.get("request", {})
        headers = req.get("headers") or {}
        for key in list(headers.keys()):
            if str(key).lower() in {
                "authorization",
                "x-api-key",
                "x-owner-token",
                "x-widget-token",
                "x-business-id",
            }:
                headers[key] = "[redacted]"
        return event

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration()],
        send_default_pii=False,
        traces_sample_rate=traces_sample_rate,
        environment=os.getenv("ENVIRONMENT", "dev"),
        before_send=_before_send,
    )
    logger.info("sentry_initialized", extra={"traces_sample_rate": traces_sample_rate})


def bind_request_context(request: Any, business_id: str | None = None) -> None:
    """Attach correlation fields to Sentry scope when enabled."""

    if sentry_sdk is None:
        return
    hub = sentry_sdk.Hub.current
    if not hub or not hub.client:
        return
    with hub.configure_scope() as scope:
        rid = getattr(request.state, "request_id", None) or request_id_ctx.get(None)
        if rid:
            scope.set_tag("request_id", rid)
        biz = business_id or business_id_ctx.get(None)
        if biz:
            scope.set_tag("business_id", biz)
        call_sid = (
            getattr(request.headers, "get", lambda _k: None)("X-CallSid")
            if getattr(request, "headers", None)
            else None
        ) or call_sid_ctx.get(None)
        msg_sid = (
            getattr(request.headers, "get", lambda _k: None)("X-Message-Sid")
            if getattr(request, "headers", None)
            else None
        ) or message_sid_ctx.get(None)
        if call_sid:
            scope.set_tag("call_sid", call_sid)
        if msg_sid:
            scope.set_tag("message_sid", msg_sid)
