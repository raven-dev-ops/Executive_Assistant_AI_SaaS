import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB


client = TestClient(app)


def metric_snapshot() -> dict:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    return resp.json()


def test_event_counters_increment_on_core_flows(tmp_path):
    before = metric_snapshot()

    # 1) User registration
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    resp_reg = client.post(
        "/v1/auth/register",
        params={"email": email, "password": "pw123"},
    )
    assert resp_reg.status_code == 200

    # 2) Chat message
    resp_chat = client.post("/v1/chat", json={"text": "Hello metrics?"})
    assert resp_chat.status_code == 200

    # 3) Contacts import
    csv_content = "Name,Phone,Email,Address\nTest User,5551239999,test@example.com,123 St\n"
    csv_path = tmp_path / "import.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    with csv_path.open("rb") as f:
        resp_import = client.post(
            "/v1/contacts/import",
            files={"file": ("import.csv", f, "text/csv")},
        )
    assert resp_import.status_code == 200

    # 4) QBO sync error (not connected) then connect callback
    if SQLALCHEMY_AVAILABLE and SessionLocal is not None:
        session = SessionLocal()
        try:
            row = session.get(BusinessDB, "default_business")
            if row:
                row.integration_qbo_status = None
                session.add(row)
                session.commit()
        finally:
            session.close()
    resp_sync_fail = client.post("/v1/integrations/qbo/sync")
    assert resp_sync_fail.status_code == 400
    resp_cb = client.get(
        "/v1/integrations/qbo/callback",
        params={"code": "abc123", "state": "default_business"},
    )
    assert resp_cb.status_code == 200

    # 5) Billing webhook success
    now = datetime.now(UTC)
    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_test",
                "subscription": "sub_test",
                "current_period_end": int((now + timedelta(days=30)).timestamp()),
                "metadata": {"business_id": "default_business"},
            }
        },
    }
    resp_webhook = client.post("/v1/billing/webhook", json=payload)
    assert resp_webhook.status_code == 200

    after = metric_snapshot()

    assert after["users_registered"] >= before.get("users_registered", 0) + 1
    assert after["chat_messages"] >= before.get("chat_messages", 0) + 1
    assert after["contacts_imported"] >= before.get("contacts_imported", 0) + 1
    assert after["qbo_sync_errors"] >= before.get("qbo_sync_errors", 0) + 1
    assert after["qbo_connections"] >= before.get("qbo_connections", 0) + 1
    assert after["subscription_activations"] >= before.get("subscription_activations", 0) + 1
