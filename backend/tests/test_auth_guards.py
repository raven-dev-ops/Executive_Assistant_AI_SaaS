import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app import deps
from app.main import app


client = TestClient(app)


class _DummySettings:
    def __init__(
        self,
        admin_api_key: str | None = None,
        owner_dashboard_token: str | None = None,
    ) -> None:
        self.admin_api_key = admin_api_key
        self.owner_dashboard_token = owner_dashboard_token


@pytest.mark.anyio
async def test_require_admin_auth_enforces_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: _DummySettings(admin_api_key="test-admin-key"),
    )

    # Without header, dependency rejects the request.
    with pytest.raises(HTTPException) as exc_info:
        await deps.require_admin_auth(x_admin_api_key=None)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    # With incorrect key, still rejected.
    with pytest.raises(HTTPException) as exc_info:
        await deps.require_admin_auth(x_admin_api_key="wrong-key")
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    # With correct key, passes without raising.
    await deps.require_admin_auth(x_admin_api_key="test-admin-key")


@pytest.mark.anyio
async def test_require_owner_dashboard_auth_enforces_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: _DummySettings(owner_dashboard_token="owner-secret-token"),
    )

    # Without header, dependency rejects the request.
    with pytest.raises(HTTPException) as exc_info:
        await deps.require_owner_dashboard_auth(x_owner_token=None)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    # With incorrect token, still rejected.
    with pytest.raises(HTTPException) as exc_info:
        await deps.require_owner_dashboard_auth(x_owner_token="wrong-token")
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    # With correct token, passes without raising.
    await deps.require_owner_dashboard_auth(x_owner_token="owner-secret-token")


def test_admin_routes_enforce_header_when_key_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: _DummySettings(admin_api_key="test-admin-key"),
    )

    # Without header, admin endpoint should be unauthorized.
    resp = client.get("/v1/admin/environment")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    # With incorrect key, still unauthorized.
    resp = client.get(
        "/v1/admin/environment",
        headers={"X-Admin-API-Key": "wrong-key"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    # With correct key, request is allowed.
    resp = client.get(
        "/v1/admin/environment",
        headers={"X-Admin-API-Key": "test-admin-key"},
    )
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert "environment" in body


def test_owner_and_crm_routes_enforce_header_when_token_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: _DummySettings(owner_dashboard_token="owner-secret-token"),
    )

    # Without header, CRM endpoint should be unauthorized.
    resp = client.get("/v1/crm/customers")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    # With incorrect token, still unauthorized.
    resp = client.get(
        "/v1/crm/customers",
        headers={"X-Owner-Token": "wrong-token"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    # With correct token, request is allowed and returns a list.
    resp = client.get(
        "/v1/crm/customers",
        headers={"X-Owner-Token": "owner-secret-token"},
    )
    assert resp.status_code == status.HTTP_200_OK
    customers = resp.json()
    assert isinstance(customers, list)
