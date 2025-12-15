import os
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services.security_events import record_security_event, security_event_log


client = TestClient(app)


def test_security_events_list_filters_by_business(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-key")
    # Clear existing events
    security_event_log._events.clear()  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    record_security_event("invalid_auth", detail="auth fail", metadata={"business_id": "biz-a"})
    record_security_event("rate_limit_block", detail="blocked", metadata={"business_id": "biz-b"})

    resp = client.get(
        "/v1/admin/security/events?business_id=biz-a&limit=10",
        headers={"X-Admin-API-Key": "admin-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    events = data.get("events", [])
    assert len(events) == 1
    assert events[0]["business_id"] == "biz-a"
    assert events[0]["event"] == "invalid_auth"


def test_security_events_list_since(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-key")
    security_event_log._events.clear()  # type: ignore[attr-defined]
    old_time = datetime.now(UTC) - timedelta(hours=2)
    # Manually append an old event
    security_event_log.append(
        {
            "event": "twilio_replay_detected",
            "detail": "old",
            "business_id": "biz-old",
            "call_sid": None,
            "message_sid": None,
            "metadata": {},
            "created_at": old_time.isoformat(),
            "created_at_dt": old_time,
        }
    )
    record_security_event("stripe_signature_invalid", detail="new", metadata={"business_id": "biz-new"})

    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    resp = client.get(
        "/v1/admin/security/events",
        headers={"X-Admin-API-Key": "admin-key"},
        params={"since": cutoff.isoformat()},
    )
    assert resp.status_code == 200
    events = resp.json().get("events", [])
    assert any(e["event"] == "stripe_signature_invalid" for e in events)
    assert all(e["event"] != "twilio_replay_detected" for e in events)


def _fresh_client(env: dict[str, str]) -> TestClient:
    for k, v in env.items():
        os.environ[k] = v
    from app import config, deps, main

    config.get_settings.cache_clear()
    deps.get_settings.cache_clear()
    app_instance = main.create_app()
    return TestClient(app_instance)


def test_alert_triggers_on_twilio_webhook_failure(monkeypatch):
    client = _fresh_client(
        {
            "VERIFY_TWILIO_SIGNATURES": "true",
            "SMS_PROVIDER": "twilio",
            "TWILIO_AUTH_TOKEN": "",
            "TWILIO_WEBHOOK_FAILURE_ALERT_THRESHOLD": "1",
            "ADMIN_API_KEY": "admin-key",
            "RATE_LIMIT_DISABLED": "true",
        }
    )
    # Reset alert counters
    from app.metrics import metrics

    metrics.alerts_open.clear()
    metrics.twilio_webhook_failures = 0

    resp = client.post(
        "/twilio/sms",
        data={"From": "+15550001111", "Body": "hi"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code in (401, 503)
    assert metrics.alerts_open.get("twilio_webhook_failure") is not None
