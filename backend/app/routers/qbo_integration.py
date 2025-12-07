from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import logging

from ..config import get_settings
from ..deps import ensure_business_active, require_owner_dashboard_auth
from ..db import SQLALCHEMY_AVAILABLE, SessionLocal
from ..db_models import BusinessDB
from ..repositories import customers_repo
from ..metrics import metrics


router = APIRouter(dependencies=[Depends(require_owner_dashboard_auth)])
logger = logging.getLogger(__name__)


class QboAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class QboCallbackResponse(BaseModel):
    connected: bool
    business_id: str
    realm_id: Optional[str] = None


class QboStatusResponse(BaseModel):
    connected: bool
    realm_id: Optional[str] = None
    token_expires_at: Optional[datetime] = None


class QboSyncResponse(BaseModel):
    imported: int
    skipped: int
    note: str


def _require_db():
    if not SQLALCHEMY_AVAILABLE or SessionLocal is None:
        raise HTTPException(
            status_code=503, detail="Database support is required for QuickBooks."
        )
    return SessionLocal()


def _mark_connected(
    business_id: str, realm_id: str | None, access_token: str, refresh_token: str
) -> None:
    session = _require_db()
    try:
        row = session.get(BusinessDB, business_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Business not found")
        row.integration_qbo_status = "connected"
        row.qbo_realm_id = realm_id
        row.qbo_access_token = access_token
        row.qbo_refresh_token = refresh_token
        row.qbo_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        session.add(row)
        session.commit()
    finally:
        session.close()


def _get_status(business_id: str) -> QboStatusResponse:
    if SQLALCHEMY_AVAILABLE and SessionLocal is not None:
        session = SessionLocal()
        try:
            row = session.get(BusinessDB, business_id)
            if row:
                return QboStatusResponse(
                    connected=(getattr(row, "integration_qbo_status", "") == "connected"),
                    realm_id=getattr(row, "qbo_realm_id", None),
                    token_expires_at=getattr(row, "qbo_token_expires_at", None),
                )
        finally:
            session.close()
    return QboStatusResponse(connected=False, realm_id=None, token_expires_at=None)


@router.get("/authorize", response_model=QboAuthorizeResponse)
def authorize_qbo(
    business_id: str = Depends(ensure_business_active),
) -> QboAuthorizeResponse:
    """Return the QuickBooks Online authorization URL for this tenant."""
    settings = get_settings().quickbooks
    if not settings.client_id or not settings.redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="QuickBooks credentials are not configured.",
        )
    logger.info("qbo_authorize_start", extra={"business_id": business_id})
    params = {
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": settings.scopes,
        "state": business_id,
    }
    url = f"{settings.authorize_base}?{urlencode(params)}"
    return QboAuthorizeResponse(authorization_url=url, state=business_id)


@router.get("/callback", response_model=QboCallbackResponse)
def callback_qbo(
    code: str = Query(..., description="Authorization code from Intuit"),
    realmId: str | None = Query(default=None, description="QuickBooks company realm ID"),
    state: str = Query(..., description="Opaque state containing business_id"),
) -> QboCallbackResponse:
    """Handle the QuickBooks OAuth callback and store tokens (stubbed)."""
    business_id = state
    # In a real integration we would exchange the code for tokens via Intuit.
    fake_access = f"access_{code}"
    fake_refresh = f"refresh_{code}"
    _mark_connected(business_id, realmId, fake_access, fake_refresh)
    metrics.qbo_connections += 1
    logger.info(
        "qbo_connected",
        extra={
            "business_id": business_id,
            "realm_id": realmId,
        },
    )
    return QboCallbackResponse(
        connected=True,
        business_id=business_id,
        realm_id=realmId,
    )


@router.get("/status", response_model=QboStatusResponse)
def qbo_status(business_id: str = Depends(ensure_business_active)) -> QboStatusResponse:
    """Return current QuickBooks connection status for this tenant."""
    return _get_status(business_id)


@router.post("/sync", response_model=QboSyncResponse)
def qbo_sync_contacts(
    business_id: str = Depends(ensure_business_active),
) -> QboSyncResponse:
    """Stub: import a couple of sample contacts to show the flow."""
    status = _get_status(business_id)
    if not status.connected:
        metrics.qbo_sync_errors += 1
        logger.warning(
            "qbo_sync_attempt_without_connection",
            extra={"business_id": business_id},
        )
        raise HTTPException(status_code=400, detail="QuickBooks is not connected.")

    try:
        imported = 0
        skipped = 0
        sample_contacts = [
            ("QBO Sample One", "555-700-0101", "sample1@qbo.test"),
            ("QBO Sample Two", "555-700-0102", None),
        ]
        for name, phone, email in sample_contacts:
            existing = customers_repo.get_by_phone(phone, business_id=business_id)
            if existing:
                skipped += 1
                continue
            customers_repo.upsert(
                name=name,
                phone=phone,
                email=email,
                address=None,
                business_id=business_id,
            )
            imported += 1
        logger.info(
            "qbo_sync_completed",
            extra={
                "business_id": business_id,
                "imported": imported,
                "skipped": skipped,
            },
        )
        return QboSyncResponse(
            imported=imported,
            skipped=skipped,
            note="Stubbed sync. Replace with real QuickBooks customer import.",
        )
    except Exception as exc:
        metrics.qbo_sync_errors += 1
        metrics.background_job_errors += 1
        logger.exception(
            "qbo_sync_failed",
            extra={"business_id": business_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Sync failed unexpectedly.")
