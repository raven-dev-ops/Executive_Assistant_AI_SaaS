import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.repositories import appointments_repo, customers_repo
from app.deps import DEFAULT_BUSINESS_ID
from app.services.calendar import calendar_service
from app.services.oauth_tokens import oauth_store


client = TestClient(app)


def test_calendar_webhook_updates_appointment():
    customers_repo._by_id.clear()
    appointments_repo._by_id.clear()
    appointments_repo._by_business.clear()
    appointments_repo._by_customer.clear()

    cust = customers_repo.upsert(
        name="Cal Tester",
        phone="+15550123456",
        business_id=DEFAULT_BUSINESS_ID,
    )
    start = datetime.now(UTC) + timedelta(days=1)
    end = start + timedelta(hours=1)
    appt = appointments_repo.create(
        customer_id=cust.id,
        start_time=start,
        end_time=end,
        service_type="Install",
        is_emergency=False,
        description="Install sink",
        business_id=DEFAULT_BUSINESS_ID,
        calendar_event_id="evt_123",
    )

    resp = client.post(
        "/v1/calendar/google/webhook",
        json={
            "business_id": DEFAULT_BUSINESS_ID,
            "event_id": "evt_123",
            "status": "cancelled",
            "start": (start + timedelta(hours=2)).isoformat(),
            "end": (end + timedelta(hours=2)).isoformat(),
            "summary": "Updated install",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["processed"] is True

    updated = appointments_repo.get(appt.id)
    assert updated is not None
    assert updated.status == "CANCELLED"
    assert updated.job_stage == "Cancelled"
    assert updated.start_time == start + timedelta(hours=2)
    assert updated.service_type == "Updated install"


def test_calendar_webhook_missing_event_returns_ok():
    resp = client.post(
        "/v1/calendar/google/webhook",
        json={
            "business_id": DEFAULT_BUSINESS_ID,
            "event_id": "unknown_evt",
            "status": "cancelled",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] is False


def test_find_slots_prefers_oauth_user_client(monkeypatch):
    oauth_store.save_tokens(
        "gcalendar",
        "biz_gcal",
        access_token="access",
        refresh_token="refresh",
        expires_in=3600,
    )
    original_use_stub = calendar_service._settings.use_stub
    calendar_service._settings.use_stub = False
    calendar_service._client = None

    calls = []

    class DummyClient:
        def freebusy(self):
            return self

        def query(self, body=None):
            return self

        def execute(self):
            return {"calendars": {"primary": {"busy": []}}}

    def fake_user_client(business_id):
        calls.append(business_id)
        return DummyClient()

    monkeypatch.setattr(calendar_service, "_build_user_client", fake_user_client)
    monkeypatch.setattr(calendar_service, "_resolve_calendar_id", lambda *a, **k: "primary")

    slots = asyncio.run(
        calendar_service.find_slots(
            duration_minutes=60,
            calendar_id=None,
            business_id="biz_gcal",
        )
    )
    assert calls == ["biz_gcal"]
    assert slots

    calendar_service._settings.use_stub = original_use_stub
