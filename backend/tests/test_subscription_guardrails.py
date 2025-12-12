from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from fastapi import status

from app import config
from app.main import app
from app.deps import DEFAULT_BUSINESS_ID
from app.db_models import BusinessDB
from app.db import SessionLocal
from app.services import subscription as subscription_service


client = TestClient(app)


@pytest.mark.anyio
async def test_subscription_enforced_blocks_access(monkeypatch):
    from app.services import subscription as subscription_service

    monkeypatch.setenv("ENFORCE_SUBSCRIPTION", "true")
    config.get_settings.cache_clear()

    # Force compute_state to report a canceled subscription.
    def fake_state(business_id: str):
        return subscription_service.SubscriptionState(
            status="canceled", blocked=False, in_grace=False
        )

    monkeypatch.setattr(subscription_service, "compute_state", fake_state)

    with pytest.raises(Exception):
        await subscription_service.check_access(
            DEFAULT_BUSINESS_ID, feature="appointments", upcoming_appointments=1
        )
    config.get_settings.cache_clear()


@pytest.mark.anyio
async def test_voice_start_blocks_when_subscription_inactive(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIPTION", "true")
    config.get_settings.cache_clear()
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, DEFAULT_BUSINESS_ID)
        row.subscription_status = "past_due"
        row.subscription_current_period_end = datetime.now(UTC) - timedelta(days=10)
        session.add(row)
        session.commit()
    finally:
        session.close()

    resp = client.post(
        "/v1/voice/session/start",
        json={"caller_phone": "+15550001234"},
        headers={"X-Business-ID": DEFAULT_BUSINESS_ID},
    )
    assert resp.status_code == 402

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, DEFAULT_BUSINESS_ID)
        row.subscription_status = "active"
        session.add(row)
        session.commit()
    finally:
        session.close()

    resp_ok = client.post(
        "/v1/voice/session/start",
        json={"caller_phone": "+15550001234"},
        headers={"X-Business-ID": DEFAULT_BUSINESS_ID},
    )
    assert resp_ok.status_code == 200
    config.get_settings.cache_clear()


@pytest.mark.anyio
async def test_telephony_inbound_degrades_instead_of_blocking(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIPTION", "true")
    config.get_settings.cache_clear()

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, DEFAULT_BUSINESS_ID)
        row.subscription_status = "canceled"
        row.subscription_current_period_end = datetime.now(UTC) - timedelta(days=5)
        session.add(row)
        session.commit()
    finally:
        session.close()

    resp = client.post(
        "/telephony/inbound",
        json={"caller_phone": "+15551234567"},
        headers={"X-Business-ID": DEFAULT_BUSINESS_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "subscription_blocked"
    assert "subscription" in data["reply_text"].lower()
    config.get_settings.cache_clear()


@pytest.mark.anyio
async def test_subscription_warns_on_usage_and_expiry(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIPTION", "true")
    config.get_settings.cache_clear()
    subscription_service._reminder_cache.clear()

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, DEFAULT_BUSINESS_ID)
        row.subscription_status = "active"
        row.service_tier = "starter"
        row.owner_email = "owner@example.com"
        row.subscription_current_period_end = datetime.now(UTC) + timedelta(days=1)
        session.add(row)
        session.commit()
    finally:
        session.close()

    monkeypatch.setattr(
        subscription_service,
        "_usage_snapshot",
        lambda business_id: subscription_service.UsageSnapshot(
            calls=195, appointments=49
        ),
    )

    sent: list[tuple[str, str]] = []

    async def fake_notify(subject, body, business_id, owner_email):
        sent.append((subject, body))

    monkeypatch.setattr(subscription_service.email_service, "notify_owner", fake_notify)

    # Trigger check_access to send expiring reminders.
    state = await subscription_service.check_access(DEFAULT_BUSINESS_ID)
    assert not state.blocked
    assert state.usage_warnings

    resp = client.get(
        "/v1/billing/subscription/status",
        headers={"X-Business-ID": DEFAULT_BUSINESS_ID},
    )
    data = resp.json()
    assert data["status"] == "active"
    assert data["usage_warnings"]
    assert data["calls_used"] == 195
    assert sent  # reminder sent once

    config.get_settings.cache_clear()
    subscription_service._reminder_cache.clear()


@pytest.mark.anyio
async def test_subscription_grace_notifies_but_allows(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIPTION", "true")
    config.get_settings.cache_clear()
    subscription_service._reminder_cache.clear()

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, DEFAULT_BUSINESS_ID)
        row.subscription_status = "past_due"
        row.service_tier = "starter"
        row.owner_email = "owner@example.com"
        row.subscription_current_period_end = datetime.now(UTC) - timedelta(days=1)
        session.add(row)
        session.commit()
    finally:
        session.close()

    sent: list[tuple[str, str]] = []

    async def fake_notify(subject, body, business_id, owner_email):
        sent.append((subject, body))

    monkeypatch.setattr(subscription_service.email_service, "notify_owner", fake_notify)
    state = await subscription_service.check_access(DEFAULT_BUSINESS_ID)

    assert state.in_grace
    assert state.blocked is False
    assert sent  # reminder sent

    config.get_settings.cache_clear()
    subscription_service._reminder_cache.clear()


@pytest.mark.anyio
async def test_subscription_blocks_when_plan_limits_exceeded(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIPTION", "true")
    config.get_settings.cache_clear()

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, DEFAULT_BUSINESS_ID)
        row.subscription_status = "active"
        row.service_tier = "starter"
        session.add(row)
        session.commit()
    finally:
        session.close()

    monkeypatch.setattr(
        subscription_service,
        "_usage_snapshot",
        lambda business_id: subscription_service.UsageSnapshot(
            calls=200, appointments=50
        ),
    )

    with pytest.raises(Exception) as excinfo:
        await subscription_service.check_access(
            DEFAULT_BUSINESS_ID, upcoming_calls=1, upcoming_appointments=0
        )

    assert (
        getattr(excinfo.value, "status_code", None) == status.HTTP_402_PAYMENT_REQUIRED
    )
    config.get_settings.cache_clear()
