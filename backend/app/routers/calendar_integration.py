from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..deps import ensure_business_active, require_owner_dashboard_auth
from ..services.calendar import calendar_service


router = APIRouter()


class CalendarWebhookPayload(BaseModel):
    business_id: str | None = None
    event_id: str
    status: str | None = None
    start: str | None = None
    end: str | None = None
    summary: str | None = None
    description: str | None = None
    updated_at: datetime | None = None


class CalendarWatchRequest(BaseModel):
    webhook_url: str | None = Field(
        default=None,
        description="Public URL Google should POST push notifications to.",
    )
    calendar_id: str | None = Field(
        default=None,
        description="Optional override calendar_id (defaults to tenant/calendar settings).",
    )
    ttl_seconds: int = Field(
        default=60 * 60 * 24 * 3,
        ge=60,
        le=60 * 60 * 24 * 7,
        description="Requested channel TTL (Google caps this; default 3 days).",
    )


@router.post("/google/watch")
async def google_calendar_watch(
    payload: CalendarWatchRequest,
    request: Request,
    business_id: str = Depends(ensure_business_active),
    _: None = Depends(require_owner_dashboard_auth),
) -> dict:
    webhook_url = payload.webhook_url or (
        f"{request.url.scheme}://{request.url.netloc}/v1/calendar/google/push"
    )
    return await calendar_service.create_google_calendar_watch(
        business_id=business_id,
        webhook_url=webhook_url,
        calendar_id=payload.calendar_id,
        ttl_seconds=payload.ttl_seconds,
    )


@router.post("/google/push")
async def google_calendar_push(request: Request) -> dict:
    """Receive Google Calendar push notifications and run an incremental sync.

    Google sends metadata in headers (X-Goog-Channel-*). We use the channel ID +
    token to resolve the tenant and then pull changes via syncToken.
    """
    result = await calendar_service.handle_google_push_notification(
        channel_id=request.headers.get("X-Goog-Channel-ID"),
        channel_token=request.headers.get("X-Goog-Channel-Token"),
        resource_state=request.headers.get("X-Goog-Resource-State"),
    )
    return {
        "processed": int(result.get("processed", 0) or 0),
        "synced": bool(result.get("synced", False)),
        "reason": result.get("reason"),
    }


@router.post("/google/webhook")
async def google_calendar_webhook(payload: CalendarWebhookPayload) -> dict:
    """Handle inbound Google Calendar notifications (best-effort sync).

    This endpoint is designed to be used with Google push notifications or
    other webhook relays. It updates matching appointments when a calendar
    event changes or is cancelled. When no matching appointment is found,
    the request succeeds with processed=False to avoid retries.
    """
    if not payload.event_id:
        raise HTTPException(status_code=400, detail="event_id is required")

    processed = await calendar_service.handle_inbound_update(
        business_id=payload.business_id,
        event_id=payload.event_id,
        status=payload.status,
        start=payload.start,
        end=payload.end,
        summary=payload.summary,
        description=payload.description,
    )
    return {"processed": bool(processed)}
