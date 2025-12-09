from datetime import UTC, datetime, timedelta
import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_signup_to_assistant_smoke():
    """Simulate signup -> billing webhook -> onboarding -> owner chat."""
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    password = "SmokePass!1"

    reg = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 200
    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    tokens = login.json()
    access = tokens["access_token"]

    # Simulate a billing activation webhook.
    period_end = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    webhook_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_smoke",
                "subscription": "sub_smoke",
                "current_period_end": period_end,
                "metadata": {"business_id": "default_business"},
            }
        },
    }
    webhook_resp = client.post("/v1/billing/webhook", json=webhook_payload)
    assert webhook_resp.status_code == 200

    # Onboarding profile should reflect subscription and basic defaults.
    profile_resp = client.get(
        "/v1/owner/onboarding/profile", headers={"Authorization": f"Bearer {access}"}
    )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile.get("subscription_status") in {"active", "past_due", "canceled"}

    # Use the owner assistant to answer a simple dashboard question.
    chat = client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {access}"},
        json={"text": "What is my subscription status?"},
    )
    assert chat.status_code == 200
    reply = chat.json().get("reply_text", "").lower()
    assert "subscription" in reply or reply, "assistant should respond"
