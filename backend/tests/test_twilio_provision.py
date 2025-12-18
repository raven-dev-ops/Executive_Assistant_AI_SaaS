from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app import config
from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB
from app.services import twilio_provision
from app.services.twilio_provision import provision_toll_free_number


pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not SQLALCHEMY_AVAILABLE,
        reason="Twilio provisioning tests require database support",
    ),
]


def _cleanup_business(business_id: str) -> None:
    if SessionLocal is None:
        return
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, business_id)
        if row:
            session.delete(row)
            session.commit()
    finally:
        session.close()


def _create_business(business_id: str) -> None:
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        session.add(
            BusinessDB(
                id=business_id,
                name="Provision Test",
                status="ACTIVE",
                created_at=datetime.now(UTC),
            )  # type: ignore[call-arg]
        )
        session.commit()
    finally:
        session.close()


async def test_provision_returns_error_when_db_support_missing(monkeypatch) -> None:
    monkeypatch.setattr(twilio_provision, "SQLALCHEMY_AVAILABLE", False)
    result = await provision_toll_free_number("any")
    assert result.status == "error"
    assert result.phone_number is None
    assert "Database support" in result.message


async def test_provision_returns_error_when_business_missing() -> None:
    result = await provision_toll_free_number(
        "does-not-exist", phone_number="+18005550100"
    )
    assert result.status == "error"
    assert "Business not found" in result.message


async def test_provision_attaches_existing_number() -> None:
    biz_id = "biz_twilio_provision_attach"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        result = await provision_toll_free_number(biz_id, phone_number="+18005550100")
        assert result.status == "attached"
        assert result.phone_number == "+18005550100"

        assert SessionLocal is not None
        session = SessionLocal()
        try:
            row = session.get(BusinessDB, biz_id)
            assert row is not None
            assert row.twilio_phone_number == "+18005550100"
            assert row.integration_twilio_status == "connected"
        finally:
            session.close()
    finally:
        _cleanup_business(biz_id)


async def test_provision_skips_when_purchase_new_false() -> None:
    biz_id = "biz_twilio_provision_skipped"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        result = await provision_toll_free_number(biz_id, purchase_new=False)
        assert result.status == "skipped"
    finally:
        _cleanup_business(biz_id)


async def test_provision_skips_when_provider_not_twilio(monkeypatch) -> None:
    biz_id = "biz_twilio_provision_provider"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        monkeypatch.setenv("SMS_PROVIDER", "stub")
        config.get_settings.cache_clear()
        result = await provision_toll_free_number(biz_id, purchase_new=True)
        assert result.status == "skipped"
        assert "SMS_PROVIDER is not 'twilio'" in result.message
    finally:
        config.get_settings.cache_clear()
        _cleanup_business(biz_id)


async def test_provision_errors_when_twilio_credentials_missing(monkeypatch) -> None:
    biz_id = "biz_twilio_provision_missing_creds"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        monkeypatch.setenv("SMS_PROVIDER", "twilio")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        config.get_settings.cache_clear()

        result = await provision_toll_free_number(biz_id, purchase_new=True)
        assert result.status == "error"
        assert "credentials missing" in result.message.lower()
    finally:
        config.get_settings.cache_clear()
        _cleanup_business(biz_id)


async def test_provision_skips_when_webhook_base_url_missing(monkeypatch) -> None:
    biz_id = "biz_twilio_provision_missing_base"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        monkeypatch.setenv("SMS_PROVIDER", "twilio")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        config.get_settings.cache_clear()

        result = await provision_toll_free_number(biz_id, purchase_new=True)
        assert result.status == "skipped"
        assert "webhook_base_url" in result.message
    finally:
        config.get_settings.cache_clear()
        _cleanup_business(biz_id)


class _DummyResp:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")

    def json(self) -> dict:
        return self._payload


class _DummyTwilioClient:
    def __init__(self, avail_payload: dict, purchase_payload: dict) -> None:
        self._avail_payload = avail_payload
        self._purchase_payload = purchase_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict) -> _DummyResp:
        return _DummyResp(self._avail_payload)

    async def post(self, url: str, data: dict) -> _DummyResp:
        return _DummyResp(self._purchase_payload)


async def test_provision_purchases_new_number_and_persists(monkeypatch) -> None:
    biz_id = "biz_twilio_provision_purchase"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        monkeypatch.setenv("SMS_PROVIDER", "twilio")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        config.get_settings.cache_clear()

        dummy_client = _DummyTwilioClient(
            avail_payload={
                "available_phone_numbers": [{"phone_number": "+18005550123"}]
            },
            purchase_payload={"phone_number": "+18005550123"},
        )

        monkeypatch.setattr(
            twilio_provision.httpx,
            "AsyncClient",
            lambda *args, **kwargs: dummy_client,
        )

        result = await provision_toll_free_number(
            biz_id,
            purchase_new=True,
            webhook_base_url="https://example.test",
        )
        assert result.status == "provisioned"
        assert result.phone_number == "+18005550123"

        assert SessionLocal is not None
        session = SessionLocal()
        try:
            row = session.get(BusinessDB, biz_id)
            assert row is not None
            assert row.twilio_phone_number == "+18005550123"
            assert row.integration_twilio_status == "connected"
        finally:
            session.close()
    finally:
        config.get_settings.cache_clear()
        _cleanup_business(biz_id)


async def test_provision_errors_when_no_numbers_available(monkeypatch) -> None:
    biz_id = "biz_twilio_provision_no_numbers"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        monkeypatch.setenv("SMS_PROVIDER", "twilio")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        config.get_settings.cache_clear()

        dummy_client = _DummyTwilioClient(
            avail_payload={"available_phone_numbers": []},
            purchase_payload={},
        )
        monkeypatch.setattr(
            twilio_provision.httpx,
            "AsyncClient",
            lambda *args, **kwargs: dummy_client,
        )

        result = await provision_toll_free_number(
            biz_id,
            purchase_new=True,
            webhook_base_url="https://example.test",
        )
        assert result.status == "error"
        assert "No toll-free numbers available" in result.message
    finally:
        config.get_settings.cache_clear()
        _cleanup_business(biz_id)


async def test_provision_errors_when_purchase_returns_no_phone_number(
    monkeypatch,
) -> None:
    biz_id = "biz_twilio_provision_blank_number"
    _cleanup_business(biz_id)
    _create_business(biz_id)
    try:
        monkeypatch.setenv("SMS_PROVIDER", "twilio")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
        config.get_settings.cache_clear()

        dummy_client = _DummyTwilioClient(
            avail_payload={"available_phone_numbers": [{"phone_number": None}]},
            purchase_payload={"phone_number": None},
        )
        monkeypatch.setattr(
            twilio_provision.httpx,
            "AsyncClient",
            lambda *args, **kwargs: dummy_client,
        )

        result = await provision_toll_free_number(
            biz_id,
            purchase_new=True,
            webhook_base_url="https://example.test",
        )
        assert result.status == "error"
        assert "did not return a phone number" in result.message
    finally:
        config.get_settings.cache_clear()
        _cleanup_business(biz_id)
