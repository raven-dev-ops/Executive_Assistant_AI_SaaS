import asyncio

import pytest

from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB
from app.metrics import BusinessSmsMetrics, metrics
from app.services.sms import sms_service


def run(coro):
    return asyncio.run(coro)


def test_sms_service_records_messages_in_stub_mode() -> None:
    sms_service._sent.clear()  # type: ignore[attr-defined]

    run(sms_service.send_sms("+15550001111", "Test message"))

    sent = sms_service.sent_messages
    assert len(sent) == 1
    assert sent[0].to == "+15550001111"
    assert sent[0].body == "Test message"


def test_send_sms_updates_global_and_per_tenant_metrics() -> None:
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_sent_total = 0
    metrics.sms_by_business.clear()

    run(sms_service.send_sms("+15550002222", "Per-tenant message", business_id="biz-1"))

    assert metrics.sms_sent_total == 1
    per_tenant = metrics.sms_by_business.get("biz-1")
    assert isinstance(per_tenant, BusinessSmsMetrics)
    assert per_tenant.sms_sent_total == 1


def test_notify_owner_uses_global_owner_number_when_no_business_override() -> None:
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_sent_owner = 0
    metrics.sms_sent_total = 0
    metrics.sms_by_business.clear()

    original_owner_number = sms_service._settings.owner_number  # type: ignore[attr-defined]
    try:
        sms_service._settings.owner_number = "+15550009999"  # type: ignore[attr-defined]

        run(sms_service.notify_owner("Owner alert"))

        sent = sms_service.sent_messages
        assert sent[-1].to == "+15550009999"
        assert sent[-1].category == "owner"
        assert metrics.sms_sent_owner == 1
        assert metrics.sms_sent_total == 1
        assert metrics.sms_by_business == {}
    finally:
        sms_service._settings.owner_number = original_owner_number  # type: ignore[attr-defined]


@pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE or SessionLocal is None,
    reason="Owner phone override requires database support",
)
def test_notify_owner_uses_business_owner_phone_override() -> None:
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_sent_owner = 0
    metrics.sms_sent_total = 0
    metrics.sms_by_business.clear()

    business_id = "owner_override_test"
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, business_id)
        if row is None:
            row = BusinessDB(  # type: ignore[call-arg]
                id=business_id,
                name="Owner Override",
                owner_phone="+15550001234",
            )
            session.add(row)
        else:
            row.owner_phone = "+15550001234"
        session.commit()
    finally:
        session.close()

    original_owner_number = sms_service._settings.owner_number  # type: ignore[attr-defined]
    try:
        sms_service._settings.owner_number = "+19999999999"  # type: ignore[attr-defined]

        run(sms_service.notify_owner("Tenant-specific owner alert", business_id=business_id))

        sent = sms_service.sent_messages
        assert sent[-1].to == "+15550001234"
        assert sent[-1].business_id == business_id
        assert sent[-1].category == "owner"

        assert metrics.sms_sent_owner == 1
        per_tenant = metrics.sms_by_business.get(business_id)
        assert isinstance(per_tenant, BusinessSmsMetrics)
        assert per_tenant.sms_sent_owner == 1
    finally:
        sms_service._settings.owner_number = original_owner_number  # type: ignore[attr-defined]


def test_notify_customer_sends_and_updates_metrics() -> None:
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_sent_customer = 0
    metrics.sms_sent_total = 0
    metrics.sms_by_business.clear()

    run(sms_service.notify_customer("+15550003333", "Customer message", business_id="biz-c"))

    sent = sms_service.sent_messages
    assert sent[-1].to == "+15550003333"
    assert sent[-1].category == "customer"
    assert sent[-1].business_id == "biz-c"

    assert metrics.sms_sent_total == 1
    assert metrics.sms_sent_customer == 1
    per_tenant = metrics.sms_by_business.get("biz-c")
    assert isinstance(per_tenant, BusinessSmsMetrics)
    assert per_tenant.sms_sent_customer == 1


def test_send_sms_twilio_missing_credentials_does_not_call_api(monkeypatch: pytest.MonkeyPatch) -> None:
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_sent_total = 0
    metrics.sms_by_business.clear()

    original_provider = sms_service._settings.provider  # type: ignore[attr-defined]
    original_sid = sms_service._settings.twilio_account_sid  # type: ignore[attr-defined]
    original_token = sms_service._settings.twilio_auth_token  # type: ignore[attr-defined]
    original_from = sms_service._settings.from_number  # type: ignore[attr-defined]

    # If AsyncClient is instantiated, this will raise and fail the test.
    def _failing_async_client(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Twilio AsyncClient should not be constructed when credentials are missing")

    monkeypatch.setattr("app.services.sms.httpx.AsyncClient", _failing_async_client)

    try:
        sms_service._settings.provider = "twilio"  # type: ignore[attr-defined]
        sms_service._settings.twilio_account_sid = None  # type: ignore[attr-defined]
        sms_service._settings.twilio_auth_token = None  # type: ignore[attr-defined]
        sms_service._settings.from_number = None  # type: ignore[attr-defined]

        run(sms_service.send_sms("+15550004444", "Twilio missing creds", business_id="biz-twilio"))

        sent = sms_service.sent_messages
        assert sent[-1].to == "+15550004444"
        assert metrics.sms_sent_total == 1
        per_tenant = metrics.sms_by_business.get("biz-twilio")
        assert isinstance(per_tenant, BusinessSmsMetrics)
        assert per_tenant.sms_sent_total == 1
    finally:
        sms_service._settings.provider = original_provider  # type: ignore[attr-defined]
        sms_service._settings.twilio_account_sid = original_sid  # type: ignore[attr-defined]
        sms_service._settings.twilio_auth_token = original_token  # type: ignore[attr-defined]
        sms_service._settings.from_number = original_from  # type: ignore[attr-defined]


def test_send_sms_twilio_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_sent_total = 0
    metrics.sms_by_business.clear()

    original_provider = sms_service._settings.provider  # type: ignore[attr-defined]
    original_sid = sms_service._settings.twilio_account_sid  # type: ignore[attr-defined]
    original_token = sms_service._settings.twilio_auth_token  # type: ignore[attr-defined]
    original_from = sms_service._settings.from_number  # type: ignore[attr-defined]

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FailingAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise RuntimeError("twilio upstream failure")

    monkeypatch.setattr(
        "app.services.sms.httpx.AsyncClient",
        FailingAsyncClient,
    )

    try:
        sms_service._settings.provider = "twilio"  # type: ignore[attr-defined]
        sms_service._settings.twilio_account_sid = "sid"  # type: ignore[attr-defined]
        sms_service._settings.twilio_auth_token = "token"  # type: ignore[attr-defined]
        sms_service._settings.from_number = "+15550005555"  # type: ignore[attr-defined]

        run(sms_service.send_sms("+15550006666", "Twilio failure path", business_id="biz-fail"))

        # Even though Twilio call fails, local recording and metrics should be updated.
        sent = sms_service.sent_messages
        assert sent[-1].to == "+15550006666"
        assert metrics.sms_sent_total == 1
        per_tenant = metrics.sms_by_business.get("biz-fail")
        assert isinstance(per_tenant, BusinessSmsMetrics)
        assert per_tenant.sms_sent_total == 1
    finally:
        sms_service._settings.provider = original_provider  # type: ignore[attr-defined]
        sms_service._settings.twilio_account_sid = original_sid  # type: ignore[attr-defined]
        sms_service._settings.twilio_auth_token = original_token  # type: ignore[attr-defined]
        sms_service._settings.from_number = original_from  # type: ignore[attr-defined]
