from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db import SQLALCHEMY_AVAILABLE, SessionLocal
from ..db_models import BusinessDB


router = APIRouter()


SUPPORTED_PROVIDERS = {"linkedin", "gmail", "gcalendar", "openai", "twilio"}


class AuthStartResponse(BaseModel):
    provider: str
    authorization_url: str
    note: str | None = None


class AuthCallbackResponse(BaseModel):
    provider: str
    business_id: str
    connected: bool
    redirect_url: str | None = None


def _ensure_db_session():
    if not SQLALCHEMY_AVAILABLE or SessionLocal is None:
        raise HTTPException(
            status_code=503,
            detail="Database support is not available for auth integrations.",
        )
    return SessionLocal()


@router.get("/{provider}/start", response_model=AuthStartResponse)
def auth_start(
    provider: str,
    business_id: str = Query(
        ..., description="Tenant business_id initiating the OAuth flow."
    ),
) -> AuthStartResponse:
    """Begin an OAuth-like flow for a business integration (stub).

    This endpoint is intentionally minimal and does not implement a real OAuth
    handshake. In a production deployment you would:

    - Construct the provider's authorization URL (LinkedIn, Google, OpenAI, Twilio).
    - Embed a signed state token that includes the business_id (and CSRF nonce).
    - Redirect the browser to that URL.

    For this proof-of-concept, we simply return a placeholder URL that encodes
    the provider and business_id in the query string so you can see the shape.
    """
    provider_norm = provider.lower()
    if provider_norm not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unsupported provider")

    # In a real implementation this would be the provider's authorize endpoint.
    authorization_url = f"https://example.com/oauth/{provider_norm}?state={business_id}"
    note = (
        "Replace authorization_url with the real provider authorize URL and a "
        "signed state token that encodes the business_id."
    )
    return AuthStartResponse(
        provider=provider_norm,
        authorization_url=authorization_url,
        note=note,
    )


@router.get("/{provider}/callback", response_model=AuthCallbackResponse)
def auth_callback(
    provider: str,
    state: str = Query(..., description="Opaque state that encodes the business_id."),
    code: str | None = Query(
        default=None,
        description="OAuth authorization code (unused in this stub implementation).",
    ),
) -> AuthCallbackResponse:
    """Handle a provider OAuth callback and mark the integration as connected (stub).

    In a production deployment this endpoint would:
    - Validate and decode `state` to recover the business_id.
    - Exchange `code` for access/refresh tokens using the provider SDK.
    - Persist those tokens in a secure secret store keyed by business_id.
    - Mark the integration as connected for this tenant.

    Here we treat `state` as the raw business_id and only flip the integration
    status flag to "connected" on the Business row so the onboarding dashboard
    can reflect that status.
    """
    provider_norm = provider.lower()
    if provider_norm not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unsupported provider")

    business_id = state
    session = _ensure_db_session()
    try:
        row = session.get(BusinessDB, business_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Business not found")

        attr_map = {
            "linkedin": "integration_linkedin_status",
            "gmail": "integration_gmail_status",
            "gcalendar": "integration_gcalendar_status",
            "openai": "integration_openai_status",
            "twilio": "integration_twilio_status",
        }
        attr = attr_map.get(provider_norm)
        if attr:
            setattr(row, attr, "connected")
            session.add(row)
            session.commit()

        redirect_url = "/dashboard/onboarding.html"
        return AuthCallbackResponse(
            provider=provider_norm,
            business_id=business_id,
            connected=True,
            redirect_url=redirect_url,
        )
    finally:
        session.close()
