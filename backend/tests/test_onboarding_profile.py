from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _get_profile():
    resp = client.get("/v1/owner/onboarding/profile")
    assert resp.status_code == 200
    return resp.json()


def test_onboarding_profile_requirements_and_completion():
    profile = _get_profile()
    assert profile["profile_complete"] is False
    missing = set(profile["requirements_missing"])
    assert "terms_of_service" in missing
    assert "privacy_policy" in missing
    # service_tier may be pre-seeded in fixtures; ensure at least one required field is missing.
    assert missing  # should not be empty initially

    # Fill required fields.
    payload = {
        "accept_terms": True,
        "accept_privacy": True,
        "service_tier": "20",
        "owner_name": "Owner Example",
        "owner_email": "owner@example.com",
    }
    patch = client.patch("/v1/owner/onboarding/profile", json=payload)
    assert patch.status_code == 200
    updated = patch.json()
    assert updated["profile_complete"] is True
    assert updated["requirements_missing"] == []


def test_oauth_callback_error_then_success_marks_status():
    # Mark error on gcalendar callback.
    err_resp = client.get(
        "/auth/gcalendar/callback",
        params={"state": "default_business", "error": "access_denied"},
    )
    assert err_resp.status_code == 200
    err_body = err_resp.json()
    assert err_body["connected"] is False
    assert "access_denied" in (err_body.get("message") or "")

    profile_after_error = _get_profile()
    gcal = next(
        (
            i
            for i in profile_after_error["integrations"]
            if i["provider"] == "gcalendar"
        ),
        None,
    )
    assert gcal is not None
    assert gcal["status"] == "error"
    assert gcal["connected"] is False

    # Retry callback without error should mark connected (stub flow in dev).
    ok_resp = client.get(
        "/auth/gcalendar/callback",
        params={"state": "default_business", "code": "stubcode"},
    )
    assert ok_resp.status_code == 200
    ok_body = ok_resp.json()
    assert ok_body["connected"] is True

    profile_after_success = _get_profile()
    gcal_ok = next(
        (
            i
            for i in profile_after_success["integrations"]
            if i["provider"] == "gcalendar"
        ),
        None,
    )
    assert gcal_ok is not None
    assert gcal_ok["status"] == "connected"
    assert gcal_ok["connected"] is True
