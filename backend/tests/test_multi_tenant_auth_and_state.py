import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app import deps
from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB
from app.main import app


client = TestClient(app)


class _RequireKeySettings:
    def __init__(self) -> None:
        self.require_business_api_key = True
        # Other settings attributes are not used by the deps under test.
        self.admin_api_key = None
        self.owner_dashboard_token = None


@pytest.mark.anyio
async def test_get_business_id_requires_tenant_credentials_when_flag_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps, "get_settings", lambda: _RequireKeySettings())

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_business_id(
            x_business_id=None,
            x_api_key=None,
            x_widget_token=None,
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing tenant credentials" in exc_info.value.detail


def test_telephony_inbound_rejects_when_require_business_key_and_no_tenant_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps, "get_settings", lambda: _RequireKeySettings())

    resp = client.post("/v1/telephony/inbound", json={"caller_phone": "555-1234"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    body = resp.json()
    assert body["detail"] == "Missing tenant credentials"


@pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE or SessionLocal is None,
    reason="Suspended tenant checks require database support",
)
def test_suspended_business_is_rejected_by_ensure_business_active() -> None:
    # Create a suspended business directly in the database.
    session = SessionLocal()
    try:
        business_id = "suspended_test_business"
        # Upsert-style create to keep the test idempotent.
        row = session.get(BusinessDB, business_id)
        if row is None:
            row = BusinessDB(  # type: ignore[call-arg]
                id=business_id,
                name="Suspended Test",
                api_key="suspended-api-key",
                status="SUSPENDED",
            )
            session.add(row)
        else:
            row.status = "SUSPENDED"
            row.api_key = "suspended-api-key"
        session.commit()
    finally:
        session.close()

    # Requests using this tenant's API key should be rejected with 403.
    resp = client.post(
        "/v1/telephony/inbound",
        json={"caller_phone": "555-3333"},
        headers={"X-API-Key": "suspended-api-key"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    body = resp.json()
    assert body["detail"] == "Business is suspended"


@pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE or SessionLocal is None,
    reason="Widget token validation requires database support",
)
def test_invalid_widget_token_is_rejected() -> None:
    # When a widget token is provided but does not match any Business row,
    # the tenant resolution dependency should reject the request.
    resp = client.get(
        "/v1/crm/customers",
        headers={"X-Widget-Token": "nonexistent-widget-token"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    body = resp.json()
    assert body["detail"] == "Invalid tenant credentials"
