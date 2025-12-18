from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sentry_sdk

logger = logging.getLogger(__name__)

_SENTRY_INITIALIZED = False
_SENTRY_ENABLED = False

_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-admin-api-key",
    "x-api-key",
    "x-owner-token",
    "x-widget-token",
    "x-twilio-signature",
    "twilio-signature",
    "x-forwarded-for",
    "x-real-ip",
}

_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "code",
    "key",
    "password",
    "secret",
    "signature",
    "state",
    "token",
}


def sentry_enabled() -> bool:
    return _SENTRY_ENABLED


def init_sentry() -> bool:
    global _SENTRY_INITIALIZED, _SENTRY_ENABLED
    if _SENTRY_INITIALIZED:
        return _SENTRY_ENABLED
    _SENTRY_INITIALIZED = True

    enabled_raw = os.getenv("SENTRY_ENABLED")
    if enabled_raw is not None and enabled_raw.strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        _SENTRY_ENABLED = False
        return False

    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        _SENTRY_ENABLED = False
        return False

    environment = (
        os.getenv("SENTRY_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "dev"
    ).strip()
    release = (
        os.getenv("SENTRY_RELEASE") or os.getenv("GIT_SHA") or ""
    ).strip() or None
    traces_sample_rate_raw = os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or "0"
    try:
        traces_sample_rate = float(traces_sample_rate_raw)
    except Exception:
        traces_sample_rate = 0.0
        logger.warning(
            "invalid_sentry_traces_sample_rate",
            extra={"value": traces_sample_rate_raw},
        )

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate,
            send_default_pii=False,
            before_send=_before_send,
        )
    except Exception:
        _SENTRY_ENABLED = False
        logger.exception("sentry_init_failed")
        return False
    _SENTRY_ENABLED = True
    logger.info(
        "sentry_initialized",
        extra={
            "environment": environment,
            "release": release,
            "traces_sample_rate": traces_sample_rate,
        },
    )
    return True


def set_request_context(
    *,
    request_id: str,
    path: str,
    method: str,
    business_id: str | None = None,
) -> None:
    if not _SENTRY_ENABLED:
        return
    try:
        sentry_sdk.set_tag("request_id", request_id)
        sentry_sdk.set_tag("http.method", method)
        sentry_sdk.set_tag("http.path", path)
        if business_id:
            sentry_sdk.set_tag("business_id", business_id)
            sentry_sdk.set_context("tenant", {"id": business_id})
    except Exception:
        logger.debug("sentry_set_request_context_failed", exc_info=True)


def capture_exception(exc: BaseException) -> None:
    if not _SENTRY_ENABLED:
        return
    try:
        sentry_sdk.capture_exception(exc)
    except Exception:
        logger.debug("sentry_capture_exception_failed", exc_info=True)


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = _scrub_headers(headers)
        if "cookies" in request:
            request["cookies"] = "[Filtered]"
        if "data" in request:
            request["data"] = "[Filtered]"
        if "query_string" in request:
            request["query_string"] = _scrub_query_string(request.get("query_string"))
        if "url" in request and isinstance(request.get("url"), str):
            request["url"] = _scrub_url(str(request["url"]))
    event.pop("user", None)
    return event


def _scrub_headers(headers: dict[str, Any]) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADERS:
            scrubbed[key] = "[Filtered]"
        else:
            scrubbed[key] = value
    return scrubbed


def _scrub_query_string(query_string: Any) -> str:
    if query_string is None:
        return ""
    if isinstance(query_string, bytes):
        raw = query_string.decode("utf-8", "ignore")
    else:
        raw = str(query_string)

    try:
        pairs = parse_qsl(raw, keep_blank_values=True)
    except Exception:
        return ""
    redacted: list[tuple[str, str]] = []
    for key, value in pairs:
        if key.lower() in _SENSITIVE_QUERY_KEYS:
            redacted.append((key, "[Filtered]"))
        else:
            redacted.append((key, value))
    return urlencode(redacted, doseq=True)


def _scrub_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    redacted_qs = _scrub_query_string(parts.query)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, redacted_qs, parts.fragment)
    )
