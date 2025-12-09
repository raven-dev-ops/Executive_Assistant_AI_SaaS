from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.metrics import metrics
from app.routers import billing

client = TestClient(app)


def test_list_plans_and_checkout_stub(monkeypatch):
    resp = client.get("/v1/billing/plans")
    assert resp.status_code == 200
    plans = resp.json()
    assert any(p["id"] == "basic" for p in plans)

    checkout = client.post(
        "/v1/billing/create-checkout-session", params={"plan_id": "basic"}
    )
    assert checkout.status_code == 200
    data = checkout.json()
    assert data["url"]
    assert data["session_id"]


def test_webhook_updates_subscription(monkeypatch):
    # Prepare a fake event
    now = datetime.now(UTC)
    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_123",
                "subscription": "sub_123",
                "current_period_end": int((now + timedelta(days=30)).timestamp()),
                "metadata": {"business_id": "default_business"},
            }
        },
    }
    resp = client.post("/v1/billing/webhook", json=payload)
    assert resp.status_code == 200

    # Verify via owner onboarding profile
    status = client.get("/v1/owner/onboarding/profile").json()
    assert status.get("subscription_status") in {"active", "past_due", "canceled"}
    assert status.get("subscription_current_period_end") is not None


def test_webhook_marks_payment_failed(monkeypatch):
    now = datetime.now(UTC)
    payload = {
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "customer": "cus_999",
                "subscription": "sub_999",
                "current_period_end": int((now + timedelta(days=10)).timestamp()),
                "metadata": {"business_id": "default_business"},
            }
        },
    }
    resp = client.post("/v1/billing/webhook", json=payload)
    assert resp.status_code == 200


def test_create_checkout_session_invalid_plan_returns_404():
    resp = client.post(
        "/v1/billing/create-checkout-session", params={"plan_id": "nonexistent"}
    )
    assert resp.status_code == 404


def test_webhook_invalid_payload_increments_failure(monkeypatch):
    metrics.billing_webhook_failures = 0
    resp = client.post(
        "/v1/billing/webhook",
        data="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert metrics.billing_webhook_failures >= 1


def test_require_db_raises_when_unavailable(monkeypatch):
    monkeypatch.setattr(billing, "SQLALCHEMY_AVAILABLE", False)
    monkeypatch.setattr(billing, "SessionLocal", None)
    with pytest.raises(HTTPException) as exc:
        billing._require_db()
    assert exc.value.status_code == 503


def test_update_subscription_missing_business(monkeypatch):
    class DummySession:
        def __init__(self) -> None:
            self.closed = False

        def get(self, model, key):
            return None

        def close(self):
            self.closed = True

    monkeypatch.setattr(billing, "SQLALCHEMY_AVAILABLE", True)
    monkeypatch.setattr(billing, "SessionLocal", lambda: DummySession())
    with pytest.raises(HTTPException) as exc:
        billing._update_subscription(
            business_id="missing",
            status="active",
            customer_id=None,
            subscription_id=None,
            current_period_end=None,
        )
    assert exc.value.status_code == 404


def test_live_checkout_requires_price(monkeypatch):
    class FakeStripeSettings:
        payment_link_url = None
        use_stub = False
        api_key = "sk_test"
        checkout_success_url = "https://example.com/success"
        checkout_cancel_url = "https://example.com/cancel"

    class FakeSettings:
        stripe = FakeStripeSettings()

    # Force plans without price IDs to trigger the config error path when live mode is requested.
    monkeypatch.setattr(billing, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        billing,
        "_plans_from_settings",
        lambda: [
            billing.Plan(
                id="basic",
                name="Basic",
                interval="month",
                price_cents=1000,
                stripe_price_id=None,
                features=[],
            )
        ],
    )
    resp = client.post(
        "/v1/billing/create-checkout-session", params={"plan_id": "basic"}
    )
    assert resp.status_code == 503
