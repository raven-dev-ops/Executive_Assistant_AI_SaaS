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
        self.token_base = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


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
    cb_data = cb_resp.json()
    assert cb_data["connected"] is True

    status_resp = client.get("/v1/integrations/qbo/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["connected"] is True

    sync_resp = client.post("/v1/integrations/qbo/sync")
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["imported"] >= 1
    customers = customers_repo.list_for_business("default_business")
    assert len(customers) >= 1


def test_qbo_sync_refreshes_expired_token(monkeypatch):
    from app.routers import qbo_integration

    # Use dummy settings to avoid real credentials.
    monkeypatch.setattr(qbo_integration, "get_settings", lambda: DummySettings())

    # Connect once to seed tokens.
    cb_resp = client.get(
        "/v1/integrations/qbo/callback",
        params={"code": "abc123", "realmId": "realm-1", "state": "default_business"},
    )
    assert cb_resp.status_code == 200

    # Expire token manually.
    if qbo_integration.SQLALCHEMY_AVAILABLE and qbo_integration.SessionLocal:
        session = qbo_integration.SessionLocal()
        try:
            row = session.get(qbo_integration.BusinessDB, "default_business")
            if row:
                row.qbo_token_expires_at = qbo_integration.datetime.now(
                    qbo_integration.UTC
                ) - qbo_integration.timedelta(minutes=1)
                session.add(row)
                session.commit()
        finally:
            session.close()

    sync_resp = client.post("/v1/integrations/qbo/sync")
    assert sync_resp.status_code == 200
    assert "Stubbed sync" in sync_resp.json()["note"]


def test_qbo_callback_stub_when_not_configured(monkeypatch):
    from app.routers import qbo_integration

    class NoCreds:
        def __init__(self) -> None:
            self.client_id = None
            self.client_secret = None
            self.redirect_uri = None
            self.scopes = "scope"
            self.sandbox = True
            self.authorize_base = "https://example.com/auth"
            self.token_base = "https://example.com/token"

    class SettingsNoCreds:
        def __init__(self) -> None:
            self.quickbooks = NoCreds()

    monkeypatch.setattr(qbo_integration, "get_settings", lambda: SettingsNoCreds())
    resp = client.get(
        "/v1/integrations/qbo/callback",
        params={"code": "stubcode", "state": "default_business"},
    )
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
