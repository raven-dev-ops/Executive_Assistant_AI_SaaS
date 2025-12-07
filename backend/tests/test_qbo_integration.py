from fastapi.testclient import TestClient

from app.main import app
from app.repositories import customers_repo


client = TestClient(app)


class DummyQuickBooks:
    def __init__(self) -> None:
        self.client_id = "dummy"
        self.client_secret = "secret"
        self.redirect_uri = "https://example.com/callback"
        self.scopes = "com.intuit.quickbooks.accounting"
        self.sandbox = True
        self.authorize_base = "https://sandbox.qbo.intuit.com/connect/oauth2"


class DummySettings:
    def __init__(self) -> None:
        self.quickbooks = DummyQuickBooks()


def test_qbo_authorize_and_sync(monkeypatch):
    # Ensure clean customer repo for deterministic asserts.
    if hasattr(customers_repo, "_by_id"):
        customers_repo._by_id.clear()  # type: ignore[attr-defined]
        customers_repo._by_phone.clear()  # type: ignore[attr-defined]
        customers_repo._by_business.clear()  # type: ignore[attr-defined]

    # Force router to use dummy QuickBooks config.
    from app.routers import qbo_integration

    monkeypatch.setattr(qbo_integration, "get_settings", lambda: DummySettings())

    auth_resp = client.get("/v1/integrations/qbo/authorize")
    assert auth_resp.status_code == 200
    auth_data = auth_resp.json()
    assert "authorization_url" in auth_data
    assert auth_data["state"] == "default_business"

    cb_resp = client.get(
        "/v1/integrations/qbo/callback",
        params={"code": "abc123", "realmId": "realm-1", "state": "default_business"},
    )
    assert cb_resp.status_code == 200

    status_resp = client.get("/v1/integrations/qbo/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["connected"] is True

    sync_resp = client.post("/v1/integrations/qbo/sync")
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["imported"] >= 1
    customers = customers_repo.list_for_business("default_business")
    assert len(customers) >= 1
