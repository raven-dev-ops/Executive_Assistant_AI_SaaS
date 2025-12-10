import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB


client = TestClient(app)


def _reset_business_defaults():
    if SQLALCHEMY_AVAILABLE and SessionLocal is not None:
        session = SessionLocal()
        try:
            row = session.get(BusinessDB, "default_business")
            if row:
                row.terms_accepted_at = None
                row.privacy_accepted_at = None
                row.owner_name = None
                row.owner_email = None
                row.service_tier = None
                row.onboarding_completed = False
                session.add(row)
                session.commit()
        finally:
            session.close()


@pytest.mark.anyio
async def test_onboarding_required_for_voice(monkeypatch):
    _reset_business_defaults()
    monkeypatch.setenv("ENFORCE_ONBOARDING", "true")
    monkeypatch.setenv("ONBOARDING_ENFORCE_IN_TESTS", "true")
    config.get_settings.cache_clear()

    # Voice session should be blocked before onboarding completion.
    resp = client.post(
        "/v1/voice/session/start",
        json={"caller_phone": "+15550001111"},
        headers={"X-Business-ID": "default_business"},
    )
    assert resp.status_code == 403

    # Complete onboarding requirements.
    patch = client.patch(
        "/v1/owner/onboarding/profile",
        headers={"X-Business-ID": "default_business"},
        json={
            "accept_terms": True,
            "accept_privacy": True,
            "owner_name": "Owner",
            "owner_email": "owner@example.com",
            "service_tier": "20",
            "onboarding_completed": True,
        },
    )
    assert patch.status_code == 200

    resp_ok = client.post(
        "/v1/voice/session/start",
        json={"caller_phone": "+15550001111"},
        headers={"X-Business-ID": "default_business"},
    )
    assert resp_ok.status_code == 200


def test_auth_integration_error_then_success(monkeypatch):
    _reset_business_defaults()
    # Use stub settings but enforce onboarding env flags for clarity.
    monkeypatch.setenv("ENFORCE_ONBOARDING", "false")
    config.get_settings.cache_clear()

    # Simulate OAuth error.
    err_resp = client.get(
        "/auth/gcalendar/callback",
        params={"state": "default_business", "error": "access_denied"},
    )
    assert err_resp.status_code == 200
    prof_err = client.get("/v1/owner/onboarding/profile")
    integration_err = next(
        i for i in prof_err.json()["integrations"] if i["provider"] == "gcalendar"
    )
    assert integration_err["status"] == "error"

    # Now simulate success.
    ok_resp = client.get(
        "/auth/gcalendar/callback",
        params={"state": "default_business", "code": "okcode"},
    )
    assert ok_resp.status_code == 200
    prof_ok = client.get("/v1/owner/onboarding/profile")
    integration_ok = next(
        i for i in prof_ok.json()["integrations"] if i["provider"] == "gcalendar"
    )
    assert integration_ok["connected"] is True
    assert integration_ok["status"] == "connected"
