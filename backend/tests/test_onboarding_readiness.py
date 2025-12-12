from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB


client = TestClient(app)


def _get_default_business():
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        return None
    session = SessionLocal()
    try:
        return session.get(BusinessDB, "default_business")
    finally:
        session.close()


def test_onboarding_readiness_reports_missing_and_ready_states():
    row = _get_default_business()
    if row is None:
        return
    session = SessionLocal()
    try:
        row.onboarding_completed = False
        row.owner_name = None
        row.owner_email = None
        row.owner_phone = None
        row.service_tier = None
        row.calendar_id = None
        row.integration_gcalendar_status = None
        row.twilio_phone_number = None
        row.open_hour = None
        row.close_hour = None
        row.terms_accepted_at = None
        row.privacy_accepted_at = None
        session.add(row)
        session.commit()
    finally:
        session.close()

    resp_missing = client.get("/v1/owner/onboarding/readiness")
    assert resp_missing.status_code == 200
    data = resp_missing.json()
    assert data["ready"] is False
    assert "calendar_connected" in data["missing"]
    assert "business_hours" in data["missing"]

    patch = client.patch(
        "/v1/owner/onboarding/profile",
        json={
            "owner_name": "Test Owner",
            "owner_email": "owner@example.com",
            "owner_phone": "+15550001111",
            "service_tier": "20",
            "accept_terms": True,
            "accept_privacy": True,
            "calendar_id": "cal-123",
            "twilio_phone_number": "+15550009999",
            "open_hour": 8,
            "close_hour": 17,
            "onboarding_completed": True,
        },
    )
    assert patch.status_code == 200

    resp_ready = client.get("/v1/owner/onboarding/readiness")
    assert resp_ready.status_code == 200
    ready = resp_ready.json()
    assert ready["ready"] is True
    assert ready["missing"] == []


def test_onboarding_test_sms_and_call_endpoints():
    row = _get_default_business()
    if row is None:
        return
    session = SessionLocal()
    try:
        row.owner_phone = "+15550002222"
        row.twilio_phone_number = "+15550003333"
        row.terms_accepted_at = row.terms_accepted_at or datetime.now(UTC)
        row.privacy_accepted_at = row.privacy_accepted_at or datetime.now(UTC)
        session.add(row)
        session.commit()
    finally:
        session.close()

    sms_resp = client.post("/v1/owner/onboarding/test-sms")
    assert sms_resp.status_code == 200
    assert sms_resp.json()["success"] is True

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, "default_business")
        row.twilio_phone_number = None
        session.add(row)
        session.commit()
    finally:
        session.close()

    call_fail = client.post("/v1/owner/onboarding/test-call")
    assert call_fail.status_code == 400

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, "default_business")
        row.twilio_phone_number = "+15550004444"
        session.add(row)
        session.commit()
    finally:
        session.close()

    call_ok = client.post("/v1/owner/onboarding/test-call")
    assert call_ok.status_code == 200
    assert call_ok.json()["success"] is True
