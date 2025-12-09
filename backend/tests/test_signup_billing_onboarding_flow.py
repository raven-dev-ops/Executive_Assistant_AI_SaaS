from datetime import UTC, datetime, timedelta
import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_signup_billing_webhook_and_onboarding_resume():
    email = f"flow-{uuid.uuid4().hex[:8]}@example.com"
    resp_reg = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "pw123456!"},
    )
    assert resp_reg.status_code == 200
    user = resp_reg.json()
    assert user["active_business_id"] == "default_business"

    plans_resp = client.get("/v1/billing/plans")
    assert plans_resp.status_code == 200
    plans = plans_resp.json()
    assert plans, "expected at least one plan from /plans"
    plan_id = plans[0]["id"]

    checkout_resp = client.post(
        "/v1/billing/create-checkout-session",
        params={"plan_id": plan_id, "customer_email": email},
    )
    assert checkout_resp.status_code == 200
    checkout = checkout_resp.json()
    assert checkout["session_id"]
    assert plan_id in checkout["url"]

    period_end = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    webhook_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_flow",
                "subscription": "sub_flow",
                "current_period_end": period_end,
                "metadata": {"business_id": "default_business"},
            }
        },
    }
    webhook_resp = client.post("/v1/billing/webhook", json=webhook_payload)
    assert webhook_resp.status_code == 200

    # Mark onboarding progress and ensure it persists after webhook update.
    patch_resp = client.patch(
        "/v1/owner/onboarding/profile",
        json={"onboarding_step": "plan"},
    )
    assert patch_resp.status_code == 200

    profile = client.get("/v1/owner/onboarding/profile").json()
    assert profile["onboarding_step"] in {"plan", "integrations", "complete"}
    assert profile.get("subscription_status") in {"active", "past_due", "canceled"}
    assert profile.get("subscription_current_period_end") is not None
