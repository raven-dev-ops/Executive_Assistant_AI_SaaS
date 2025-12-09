import asyncio
import types

from app.services.email_service import email_service, EmailResult
from app.services.oauth_tokens import oauth_store


class DummyResponse:
    def __init__(self, status_code: int = 200, text: str = "{}"):
        self.status_code = status_code
        self.text = text

    def json(self):
        return {"id": "msg_123"}


class DummyClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None, data=None):
        return DummyResponse()


def test_send_email_without_tokens_uses_stub(monkeypatch):
    # No tokens stored for this tenant.
    result = asyncio.run(
        email_service.send_email(
            to="owner@example.com",
            subject="Test",
            body="Hello",
            business_id="biz_none",
        )
    )
    assert isinstance(result, EmailResult)
    assert result.sent is False
    assert result.provider == "stub"


def test_send_email_with_tokens(monkeypatch):
    # Seed tokens for this tenant.
    oauth_store.save_tokens(
        "gmail",
        "biz1",
        access_token="access",
        refresh_token="refresh",
        expires_in=3600,
    )

    # Monkeypatch httpx.AsyncClient to avoid real network calls.
    import app.services.email_service as email_mod

    monkeypatch.setattr(email_mod, "httpx", types.SimpleNamespace(AsyncClient=DummyClient))

    result = asyncio.run(
        email_service.send_email(
            to="owner@example.com",
            subject="Test Send",
            body="Hello world",
            business_id="biz1",
            from_email="owner@example.com",
        )
    )
    assert result.sent is True
    assert result.provider == "gmail"
