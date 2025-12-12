from __future__ import annotations

import contextvars

# Request-scoped correlation id
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
