from __future__ import annotations

import contextvars

# Request-scoped correlation id
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# Additional request-scoped correlation fields for centralized logging.
trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)
business_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "business_id", default=None
)
call_sid_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "call_sid", default=None
)
message_sid_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "message_sid", default=None
)
