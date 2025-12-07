from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app import deps
from app.main import app
from app.metrics import CallbackItem, metrics


client = TestClient(app)


def _apply_owner_overrides(business_id: str = "biz-callbacks") -> None:
    app.dependency_overrides[deps.require_owner_dashboard_auth] = lambda: None
    app.dependency_overrides[deps.ensure_business_active] = lambda: business_id


def test_owner_callbacks_queue_and_summary(monkeypatch):
    _apply_owner_overrides()
    biz_id = "biz-callbacks"
    now = datetime.now(UTC)
    metrics.callbacks_by_business[biz_id] = {
        "+15550000001": CallbackItem(
            phone="+15550000001",
            first_seen=now - timedelta(minutes=30),
            last_seen=now - timedelta(minutes=5),
            count=2,
            channel="phone",
            lead_source="web",
            status="PENDING",
            last_result=None,
            reason="MISSED_CALL",
        ),
        "+15550000002": CallbackItem(
            phone="+15550000002",
            first_seen=now - timedelta(minutes=15),
            last_seen=now - timedelta(minutes=2),
            count=1,
            channel="sms",
            lead_source="adwords",
            status="COMPLETED",
            last_result="contacted",
            reason="PARTIAL_INTAKE",
        ),
    }

    try:
        resp = client.get("/v1/owner/callbacks")
        assert resp.status_code == 200
        data = resp.json()
        # Only pending items should be listed.
        assert len(data["items"]) == 1
        assert data["items"][0]["phone"] == "+15550000001"

        summary = client.get("/v1/owner/callbacks/summary").json()
        assert summary["total_callbacks"] == 2
        assert summary["pending"] == 1
        assert summary["completed"] == 1
        assert summary["missed_callbacks"] == 1
        assert summary["partial_intake_callbacks"] == 1
    finally:
        app.dependency_overrides.clear()
        metrics.callbacks_by_business.clear()


def test_owner_callbacks_delete_and_patch(monkeypatch):
    _apply_owner_overrides()
    biz_id = "biz-callbacks"
    now = datetime.now(UTC)
    metrics.callbacks_by_business[biz_id] = {
        "+15550000003": CallbackItem(
            phone="+15550000003",
            first_seen=now - timedelta(minutes=10),
            last_seen=now - timedelta(minutes=1),
            count=1,
            channel="phone",
            lead_source=None,
            status="PENDING",
            last_result=None,
            reason="MISSED_CALL",
        ),
    }

    try:
        resp_patch = client.patch(
            "/v1/owner/callbacks/%2B15550000003",
            json={"status": "COMPLETED", "result": "done"},
        )
        assert resp_patch.status_code == 200
        data = resp_patch.json()
        assert data["status"] == "COMPLETED"
        assert data["last_result"] == "done"

        resp_delete = client.delete("/v1/owner/callbacks/%2B15550000003")
        assert resp_delete.status_code == 204

        # Subsequent delete should no-op gracefully.
        resp_delete_again = client.delete("/v1/owner/callbacks/%2B15550000003")
        assert resp_delete_again.status_code == 204
    finally:
        app.dependency_overrides.clear()
        metrics.callbacks_by_business.clear()
