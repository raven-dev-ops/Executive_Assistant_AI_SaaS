from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..db import SQLALCHEMY_AVAILABLE, SessionLocal
from ..db_models import BusinessDB
from ..services.zip_enrichment import fetch_zip_income


logger = logging.getLogger(__name__)
router = APIRouter()


class SignupRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    vertical: str | None = Field(
        default=None,
        description="Optional business vertical (e.g. plumbing, hvac, electrical).",
    )
    owner_phone: str | None = Field(
        default=None,
        description="Owner phone number for alerts and onboarding contact.",
    )
    zip_code: str | None = Field(
        default=None,
        description="Business ZIP/postal code used for market enrichment.",
    )
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    website_url: str | None = None


class SignupResponse(BaseModel):
    business_id: str
    name: str
    vertical: str | None
    api_key: str
    widget_token: str
    status: str
    owner_phone: str | None
    zip_code: str | None = None
    median_household_income: int | None = None
    service_tier: str | None = None


def _get_db_session():
    if not SQLALCHEMY_AVAILABLE or SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database support is not available",
        )
    return SessionLocal()


@router.post(
    "/v1/public/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def public_signup(payload: SignupRequest) -> SignupResponse:
    """Public self-service signup for new service businesses.

    When ALLOW_SELF_SIGNUP=true is set in the environment, this endpoint
    creates a new Business row, generates an API key and widget token, and
    returns them to the caller so they can configure dashboards and widgets.
    """
    allow = os.getenv("ALLOW_SELF_SIGNUP", "false").lower() == "true"
    if not allow:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-service signup is disabled for this deployment.",
        )

    settings = get_settings()
    session = _get_db_session()
    try:
        existing = (
            session.query(BusinessDB)
            .filter(BusinessDB.name == payload.business_name)
            .one_or_none()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A business with this name already exists.",
            )

        business_id = secrets.token_hex(8)
        api_key = secrets.token_hex(16)
        widget_token = secrets.token_hex(16)
        now = datetime.now(UTC)
        vertical = payload.vertical or getattr(settings, "default_vertical", "plumbing")
        calendar_id = settings.calendar.calendar_id
        # Default new tenants to the entry-level tier; owners can upgrade
        # later from the onboarding flow or admin tools.
        default_service_tier = os.getenv("DEFAULT_SERVICE_TIER", "20")

        income_profile = None
        if payload.zip_code:
            income_profile = fetch_zip_income(payload.zip_code)

        row = BusinessDB(  # type: ignore[arg-type]
            id=business_id,
            name=payload.business_name,
            vertical=vertical,
            api_key=api_key,
            widget_token=widget_token,
            calendar_id=calendar_id,
            status="ACTIVE",
            owner_name=payload.contact_name,
            owner_email=str(payload.contact_email) if payload.contact_email else None,
            owner_phone=payload.owner_phone,
            zip_code=payload.zip_code,
            emergency_keywords=None,
            default_reminder_hours=None,
            service_duration_config=None,
            open_hour=None,
            close_hour=None,
            closed_days=None,
            appointment_retention_days=None,
            conversation_retention_days=None,
            language_code=getattr(settings, "default_language_code", "en"),
            max_jobs_per_day=None,
            reserve_mornings_for_emergencies=False,
            travel_buffer_minutes=None,
            twilio_missed_statuses=None,
            retention_enabled=True,
            retention_sms_template=None,
            created_at=now,
            median_household_income=(
                income_profile.median_household_income if income_profile else None
            ),
            service_tier=default_service_tier,
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        logger.info(
            "public_signup_created_business",
            extra={
                "business_id": row.id,
                "business_name": row.name,
                "vertical": row.vertical,
                "owner_phone": row.owner_phone,
                "zip_code": getattr(row, "zip_code", None),
                "median_household_income": getattr(
                    row, "median_household_income", None
                ),
                "contact_name": payload.contact_name,
                "contact_email": payload.contact_email,
                "website_url": payload.website_url,
            },
        )

        return SignupResponse(
            business_id=row.id,
            name=row.name,
            vertical=row.vertical,
            api_key=row.api_key or api_key,
            widget_token=row.widget_token or widget_token,
            status=row.status,
            owner_phone=row.owner_phone,
            zip_code=getattr(row, "zip_code", None),
            median_household_income=getattr(row, "median_household_income", None),
            service_tier=getattr(row, "service_tier", None),
        )
    finally:
        session.close()
