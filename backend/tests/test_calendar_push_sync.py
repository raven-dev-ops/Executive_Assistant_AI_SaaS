from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB
from app.main import app
from app.repositories import appointments_repo, customers_repo
from app.services.calendar import calendar_service


client = TestClient(app)


def _require_db() -> None:
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        pytest.skip("Database not available for calendar push sync tests")


def _reset_inmemory_repos() -> None:
    for repo in (appointments_repo, customers_repo):
        for attr in ("_by_id", "_by_business", "_by_customer", "_by_phone"):
            if hasattr(repo, attr):
                getattr(repo, attr).clear()  # type: ignore[attr-defined]


def _upsert_business(business_id: str, **fields: object) -> None:
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, business_id)
        if row is None:
            row = BusinessDB(  # type: ignore[call-arg]
                id=business_id,
                name=f"Test {business_id}",
                status="ACTIVE",
            )
            session.add(row)
        for key, val in fields.items():
            setattr(row, key, val)
        session.add(row)
        session.commit()
    finally:
        session.close()


def _delete_business(business_id: str) -> None:
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        return
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, business_id)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()


def test_calendar_webhook_naive_timestamps_use_tenant_timezone() -> None:
    _require_db()
    _reset_inmemory_repos()
    business_id = "tz_business_test"
    _upsert_business(business_id, time_zone="-06:00")

    cust = customers_repo.upsert(
        name="Tenant TZ Customer",
        phone="+15550123456",
        business_id=business_id,
    )
    appt = appointments_repo.create(
        customer_id=cust.id,
        start_time=datetime(2025, 12, 1, 16, 0, tzinfo=UTC),  # 10:00 at -06:00
        end_time=datetime(2025, 12, 1, 17, 0, tzinfo=UTC),
        service_type="Repair",
        is_emergency=False,
        business_id=business_id,
        calendar_event_id="evt_tz_naive",
    )

    try:
        resp = client.post(
            "/v1/calendar/google/webhook",
            json={
                "business_id": business_id,
                "event_id": "evt_tz_naive",
                # Naive timestamps should be interpreted in the tenant timezone.
                "start": "2025-12-01T10:00:00",
                "end": "2025-12-01T11:00:00",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["processed"] is True

        updated = appointments_repo.get(appt.id)
        assert updated is not None
        assert updated.start_time == datetime(2025, 12, 1, 16, 0, tzinfo=UTC)
        assert updated.end_time == datetime(2025, 12, 1, 17, 0, tzinfo=UTC)
    finally:
        _delete_business(business_id)


def test_google_calendar_push_sync_updates_appointments(monkeypatch) -> None:
    _require_db()
    _reset_inmemory_repos()
    business_id = "calendar_push_sync_test"
    _upsert_business(business_id)

    cust = customers_repo.upsert(
        name="Push Sync Customer",
        phone="+15550987654",
        business_id=business_id,
    )
    appt = appointments_repo.create(
        customer_id=cust.id,
        start_time=datetime(2025, 12, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2025, 12, 1, 11, 0, tzinfo=UTC),
        service_type="Repair",
        is_emergency=False,
        business_id=business_id,
        calendar_event_id="evt_push_1",
    )

    class _DummyList:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def execute(self) -> dict:
            return self._payload

    class _DummyWatch:
        def execute(self) -> dict:
            # Expiration is milliseconds since epoch.
            return {
                "resourceId": "resource-123",
                "expiration": str(int((datetime.now(UTC).timestamp() + 3600) * 1000)),
            }

    class _DummyEvents:
        def __init__(self) -> None:
            self._incremental_sent = False

        def watch(self, calendarId: str, body: dict) -> _DummyWatch:  # type: ignore[no-untyped-def]
            return _DummyWatch()

        def list(self, **kwargs):  # type: ignore[no-untyped-def]
            # Full sync (no syncToken): return nextSyncToken.
            if not kwargs.get("syncToken"):
                return _DummyList(
                    {
                        "items": [
                            {
                                "id": "evt_push_1",
                                "status": "confirmed",
                                "start": {
                                    "dateTime": "2025-12-01T10:00:00+00:00",
                                },
                                "end": {
                                    "dateTime": "2025-12-01T11:00:00+00:00",
                                },
                                "summary": "Repair",
                                "description": "Initial",
                            }
                        ],
                        "nextSyncToken": "sync-1",
                    }
                )

            # Incremental sync: move the event.
            if not self._incremental_sent:
                self._incremental_sent = True
                return _DummyList(
                    {
                        "items": [
                            {
                                "id": "evt_push_1",
                                "status": "confirmed",
                                "start": {
                                    "dateTime": "2025-12-01T12:00:00+00:00",
                                },
                                "end": {
                                    "dateTime": "2025-12-01T13:00:00+00:00",
                                },
                                "summary": "Repair",
                                "description": "Moved",
                            }
                        ],
                        "nextSyncToken": "sync-2",
                    }
                )

            return _DummyList({"items": [], "nextSyncToken": "sync-3"})

    class _DummyClient:
        def __init__(self) -> None:
            self._events = _DummyEvents()

        def events(self) -> _DummyEvents:  # type: ignore[override]
            return self._events

    dummy_client = _DummyClient()
    monkeypatch.setattr(calendar_service._settings, "use_stub", False)
    monkeypatch.setattr(calendar_service, "_client", None)
    monkeypatch.setattr(
        calendar_service, "_build_user_client", lambda _biz: dummy_client
    )

    try:
        watch = client.post(
            "/v1/calendar/google/watch",
            json={"webhook_url": "https://example.test/v1/calendar/google/push"},
            headers={"X-Business-ID": business_id},
        )
        assert watch.status_code == 200
        watch_body = watch.json()
        assert watch_body["created"] is True
        assert watch_body["sync_token_stored"] is True

        channel_id = watch_body["channel_id"]
        channel_token = watch_body["channel_token"]

        push = client.post(
            "/v1/calendar/google/push",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Channel-Token": channel_token,
                "X-Goog-Resource-State": "exists",
            },
        )
        assert push.status_code == 200
        push_body = push.json()
        assert push_body["synced"] is True
        assert push_body["processed"] >= 1

        updated = appointments_repo.get(appt.id)
        assert updated is not None
        assert updated.start_time == datetime(2025, 12, 1, 12, 0, tzinfo=UTC)
        assert updated.end_time == datetime(2025, 12, 1, 13, 0, tzinfo=UTC)
        assert updated.job_stage == "Rescheduled"
    finally:
        _delete_business(business_id)
