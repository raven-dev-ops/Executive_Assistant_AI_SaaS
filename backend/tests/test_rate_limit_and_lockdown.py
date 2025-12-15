import os

import pytest
from fastapi.testclient import TestClient

from app import config, deps, main
from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB


def _fresh_client(env: dict[str, str]) -> TestClient:
    for k, v in env.items():
        os.environ[k] = v
    config.get_settings.cache_clear()
    deps.get_settings.cache_clear()
    app = main.create_app()
    return TestClient(app)


def _ensure_business():
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        return
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, "default_business")
        if row is None:
            row = BusinessDB(  # type: ignore[call-arg]
                id="default_business", name="Default", status="ACTIVE"
            )
            session.add(row)
        session.commit()
    finally:
        session.close()


def test_rate_limit_blocks_after_burst(monkeypatch):
    client = _fresh_client(
        {
            "RATE_LIMIT_PER_MINUTE": "1",
            "RATE_LIMIT_BURST": "1",
            "RATE_LIMIT_DISABLED": "false",
        }
    )
    _ensure_business()
    first = client.post("/v1/widget/start", json={})
    assert first.status_code == 200

    second = client.post("/v1/widget/start", json={})
    assert second.status_code == 429
    assert "Retry-After" in second.headers
    from app.metrics import metrics

    assert metrics.security_events.get("rate_limit_block", 0) >= 1


def test_rate_limit_still_applies_when_ip_whitelisted(monkeypatch):
    # When IP is whitelisted, we still enforce per-tenant/token buckets.
    client = _fresh_client(
        {
            "RATE_LIMIT_PER_MINUTE": "1",
            "RATE_LIMIT_BURST": "1",
            "RATE_LIMIT_DISABLED": "false",
            "RATE_LIMIT_WHITELIST_IPS": "testclient",
        }
    )
    _ensure_business()
    first = client.post("/v1/widget/start", json={})
    assert first.status_code == 200

    second = client.post("/v1/widget/start", json={})
    assert second.status_code == 429
    assert "Retry-After" in second.headers


@pytest.mark.skipif(
    not (SQLALCHEMY_AVAILABLE and SessionLocal is not None),
    reason="Lockdown flag requires database support",
)
def test_lockdown_blocks_widget_requests(monkeypatch):
    client = _fresh_client(
        {
            "RATE_LIMIT_PER_MINUTE": "120",
            "RATE_LIMIT_BURST": "20",
            "RATE_LIMIT_DISABLED": "false",
            "ADMIN_API_KEY": "adminkey",
        }
    )
    _ensure_business()
    # Toggle lockdown via admin API to mirror operator workflow.
    lock_resp = client.patch(
        "/v1/admin/businesses/default_business",
        json={"lockdown_mode": True},
        headers={"X-Admin-API-Key": "adminkey"},
    )
    assert lock_resp.status_code == 200
    assert lock_resp.json().get("lockdown_mode") is True

    resp = client.post("/v1/widget/start", json={})
    assert resp.status_code == 423
    assert "lockdown" in resp.text.lower()

    # Reset lockdown to avoid affecting other tests.
    unlock_resp = client.patch(
        "/v1/admin/businesses/default_business",
        json={"lockdown_mode": False},
        headers={"X-Admin-API-Key": "adminkey"},
    )
    assert unlock_resp.status_code == 200


@pytest.mark.skipif(
    not (SQLALCHEMY_AVAILABLE and SessionLocal is not None),
    reason="Lockdown flag requires database support",
)
def test_admin_can_toggle_lockdown_and_usage_reflects(monkeypatch):
    client = _fresh_client(
        {
            "ADMIN_API_KEY": "adminkey",
            "RATE_LIMIT_DISABLED": "true",
        }
    )
    _ensure_business()

    enable = client.patch(
        "/v1/admin/businesses/default_business",
        json={"lockdown_mode": True},
        headers={"X-Admin-API-Key": "adminkey"},
    )
    assert enable.status_code == 200
    assert enable.json().get("lockdown_mode") is True

    usage_resp = client.get("/v1/admin/businesses/usage", headers={"X-Admin-API-Key": "adminkey"})
    assert usage_resp.status_code == 200
    usage_data = usage_resp.json()
    assert any(u.get("id") == "default_business" and u.get("lockdown_mode") is True for u in usage_data)

    disable = client.patch(
        "/v1/admin/businesses/default_business",
        json={"lockdown_mode": False},
        headers={"X-Admin-API-Key": "adminkey"},
    )
    assert disable.status_code == 200
    assert disable.json().get("lockdown_mode") is False


def test_per_number_sms_rate_limit(monkeypatch):
    client = _fresh_client(
        {
            "SMS_PER_NUMBER_PER_MINUTE": "1",
            "SMS_PER_NUMBER_BURST": "1",
            "SMS_PROVIDER": "stub",
            "RATE_LIMIT_DISABLED": "true",
            "RATE_LIMIT_ANOMALY_THRESHOLD_BUSINESS": "1",
        }
    )
    # Reset per-number limiter globals to pick up fresh settings.
    from app.routers import twilio_integration

    twilio_integration._per_number_rate_limiter = None  # type: ignore[attr-defined]
    twilio_integration._per_number_limits_loaded_at = None  # type: ignore[attr-defined]

    _ensure_business()

    first = client.post(
        "/twilio/sms",
        data={"From": "+15550001111", "Body": "Hello"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert first.status_code == 200

    second = client.post(
        "/twilio/sms",
        data={"From": "+15550001111", "Body": "Hello again"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert second.status_code == 429
    assert "Retry-After" in second.headers
    # Ensure anomaly alert recorded for rate-limit spike.
    from app.metrics import metrics

    assert metrics.alerts_open.get("rate_limit_spike_phone") is not None
    assert metrics.security_events.get("rate_limit_phone_block", 0) >= 1


def test_chat_widget_flow_not_rate_limited_under_normal_load(monkeypatch):
    client = _fresh_client(
        {
            "RATE_LIMIT_PER_MINUTE": "2",
            "RATE_LIMIT_BURST": "2",
            "RATE_LIMIT_DISABLED": "false",
        }
    )
    _ensure_business()
    from app.metrics import metrics

    metrics.rate_limit_blocks_total = 0
    metrics.security_events.clear()

    start = client.post("/v1/widget/start", json={})
    assert start.status_code == 200
    conv_id = start.json().get("conversation_id")
    assert conv_id

    message = client.post(f"/v1/widget/{conv_id}/message", json={"text": "Hi"})
    assert message.status_code == 200
    assert metrics.rate_limit_blocks_total == 0
    assert metrics.security_events.get("rate_limit_block", 0) == 0
