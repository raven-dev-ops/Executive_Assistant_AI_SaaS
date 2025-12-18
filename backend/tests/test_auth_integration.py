import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db import SessionLocal, SQLALCHEMY_AVAILABLE
from app.db_models import BusinessDB
from app.main import app


client = TestClient(app)


def _get_default_business_id() -> str:
    if not SQLALCHEMY_AVAILABLE or SessionLocal is None:
        return "default_business"
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, "default_business")
        if row is not None:
            return row.id
    finally:
        session.close()
    return "default_business"


def test_auth_start_returns_stub_authorization_url() -> None:
    business_id = _get_default_business_id()
    resp = client.get(f"/auth/linkedin/start?business_id={business_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "linkedin"
    assert body["authorization_url"] == (
        f"https://example.com/oauth/linkedin?state={business_id}"
    )
    assert "Replace authorization_url" in body["note"]


def test_auth_start_rejects_unsupported_provider() -> None:
    business_id = _get_default_business_id()
    resp = client.get(f"/auth/unknown/start?business_id={business_id}")
    assert resp.status_code == 404


def test_auth_callback_marks_integration_connected() -> None:
    business_id = _get_default_business_id()

    resp = client.get(f"/auth/linkedin/callback?state={business_id}&code=dummy-code")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "linkedin"
    assert body["business_id"] == business_id
    assert body["connected"] is True
    assert body["redirect_url"] == "/dashboard/onboarding.html"

    if SQLALCHEMY_AVAILABLE and SessionLocal is not None:
        session = SessionLocal()
        try:
            row = session.get(BusinessDB, business_id)
            if row is not None:
                assert getattr(row, "integration_linkedin_status", None) == "connected"
        finally:
            session.close()


def test_auth_callback_returns_404_for_missing_business() -> None:
    resp = client.get("/auth/openai/callback?state=nonexistent-business&code=dummy")
    assert resp.status_code == 404


def test_auth_callback_rejects_unsupported_provider() -> None:
    resp = client.get("/auth/unknown/callback?state=default_business&code=dummy")
    assert resp.status_code == 404


def test_auth_start_uses_signed_state_when_not_testing(monkeypatch) -> None:
    from app.routers import auth_integration
    from app.services.oauth_state import decode_state
    from urllib.parse import parse_qs, urlparse

    monkeypatch.setattr(auth_integration, "_is_testing_mode", lambda: False)

    business_id = _get_default_business_id()
    resp = client.get(f"/auth/gcalendar/start?business_id={business_id}")
    assert resp.status_code == 200
    authorization_url = resp.json()["authorization_url"]
    parsed = urlparse(authorization_url)
    state = parse_qs(parsed.query).get("state", [None])[0]
    assert state
    assert state != business_id

    settings = auth_integration.get_settings()
    secret = getattr(settings.oauth, "state_secret", "") or ""
    decoded_business_id, decoded_provider = decode_state(state, secret)
    assert decoded_business_id == business_id
    assert decoded_provider == "gcalendar"


def test_auth_callback_rejects_invalid_state_when_not_testing(monkeypatch) -> None:
    from app.routers import auth_integration

    monkeypatch.setattr(auth_integration, "_is_testing_mode", lambda: False)

    resp = client.get("/auth/gcalendar/callback?state=invalid&code=dummy")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid state"


def test_auth_callback_rejects_provider_mismatch(monkeypatch) -> None:
    from app.routers import auth_integration
    from app.services.oauth_state import encode_state

    monkeypatch.setattr(auth_integration, "_is_testing_mode", lambda: False)

    business_id = _get_default_business_id()
    settings = auth_integration.get_settings()
    secret = getattr(settings.oauth, "state_secret", "") or ""
    state = encode_state(business_id, "gmail", secret)
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            auth_integration.auth_callback(
                provider="gcalendar",
                state=state,
                code="dummy",
                error=None,
            )
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "State provider mismatch"
