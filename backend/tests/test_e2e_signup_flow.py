from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.repositories import appointments_repo


client = TestClient(app)


@pytest.mark.anyio
async def test_signup_to_scheduled_appointment(monkeypatch):
    # Enable self-signup for this test run.
    monkeypatch.setenv("ALLOW_SELF_SIGNUP", "true")
    config.get_settings.cache_clear()

    business_name = f"TestBiz-{datetime.now(UTC).timestamp()}"
    signup = client.post(
        "/v1/public/signup",
        json={
            "business_name": business_name,
            "vertical": "plumbing",
            "owner_phone": "+15551230000",
            "zip_code": "94105",
        },
    )
    assert signup.status_code == 201
    data = signup.json()
    business_id = data["business_id"]
    api_key = data["api_key"]

    # Start a voice session for the new tenant.
    start = client.post(
        "/v1/voice/session/start",
        json={"caller_phone": "+15551234567"},
        headers={"X-API-Key": api_key},
    )
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    # Walk through the scheduling dialog.
    steps = [
        "Hi this is John",  # name
        "123 Main St 94105",  # address
        "Sink is leaking",  # problem
        "yes",  # ask schedule
        "yes",  # confirm slot
    ]
    last_reply = ""
    for step in steps:
        resp = client.post(
            f"/v1/voice/session/{session_id}/input",
            json={"text": step},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        last_reply = body["reply_text"]
    assert "scheduled" in last_reply.lower()

    # Appointment should be created for this tenant.
    appts = appointments_repo.list_for_business(business_id)
    assert appts
    latest = appts[-1]
    assert latest.status == "SCHEDULED"
