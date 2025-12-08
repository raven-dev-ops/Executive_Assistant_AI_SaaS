import hmac
import json
from hashlib import sha256
from datetime import UTC, datetime
from fastapi.testclient import TestClient

from app.main import app, get_settings
from app.metrics import metrics


client = TestClient(app, raise_server_exceptions=False)


def _stripe_sig(payload: dict, secret: str, ts: int) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signed = f"{ts}.{raw.decode()}".encode()
    sig = hmac.new(secret.encode(), signed, sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_webhook_rejects_missing_signature(monkeypatch):
    settings = get_settings()
    settings.stripe.use_stub = False
    settings.stripe.verify_signatures = True
    settings.stripe.webhook_secret = "whsec_test"

    payload = {"id": "evt_1", "type": "invoice.payment_failed", "data": {"object": {}}}
    resp = client.post("/v1/billing/webhook", json=payload)
    assert resp.status_code == 400


def test_webhook_accepts_valid_signature_and_prevents_replay(monkeypatch):
    settings = get_settings()
    settings.stripe.use_stub = False
    settings.stripe.verify_signatures = True
    settings.stripe.webhook_secret = "whsec_test"
    settings.stripe.replay_protection_seconds = 300

    payload = {
        "id": "evt_valid",
        "type": "invoice.payment_failed",
        "data": {"object": {"metadata": {"business_id": "default_business"}}},
    }
    ts = int(datetime.now(UTC).timestamp())
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = _stripe_sig(payload, settings.stripe.webhook_secret, ts)
    metrics.billing_webhook_failures = 0

    resp1 = client.post(
        "/v1/billing/webhook",
        content=raw,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp1.status_code == 200
    assert metrics.billing_webhook_failures == 0

    # Replay same event should be blocked.
    resp2 = client.post(
        "/v1/billing/webhook",
        content=raw,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp2.status_code == 400
