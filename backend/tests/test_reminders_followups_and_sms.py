from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.metrics import metrics
from app.repositories import appointments_repo, conversations_repo, customers_repo
from app.services.sms import sms_service
from app.services.twilio_state import (
    CallSessionLink,
    InMemoryTwilioStateStore,
    RedisTwilioStateStore,
    SmsConversationLink,
    _create_twilio_state_store,
)


client = TestClient(app)


def _reset_repos_and_metrics() -> None:
    appointments_repo._by_id.clear()
    appointments_repo._by_customer.clear()
    appointments_repo._by_business.clear()
    conversations_repo._by_id.clear()
    conversations_repo._by_business.clear()
    customers_repo._by_id.clear()
    customers_repo._by_phone.clear()
    customers_repo._by_business.clear()
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_by_business.clear()
    metrics.lead_followups_sent = 0


@pytest.mark.anyio
async def test_send_unbooked_lead_followups_targets_recent_conversations(monkeypatch) -> None:
    _reset_repos_and_metrics()

    now = datetime.now(UTC)

    # Customer with a recent conversation and no appointment -> should get follow-up.
    lead = customers_repo.upsert(name="Recent Lead", phone="+15550006001")
    conv = conversations_repo.create(
        business_id="default_business",
        channel="sms",
        customer_id=lead.id,
        session_id="sess-1",
    )
    conv.created_at = now - timedelta(days=2)

    # Customer with recent conversation but an active appointment -> skipped.
    with_appt = customers_repo.upsert(name="Booked Lead", phone="+15550006002")
    conv2 = conversations_repo.create(
        business_id="default_business",
        channel="sms",
        customer_id=with_appt.id,
        session_id="sess-2",
    )
    conv2.created_at = now - timedelta(days=3)
    appt = appointments_repo.create(
        customer_id=with_appt.id,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        service_type="Install",
        is_emergency=False,
        description="Future appointment",
    )
    appt.status = "SCHEDULED"

    # Customer with old conversation outside the 7-day window -> skipped.
    old_lead = customers_repo.upsert(name="Old Lead", phone="+15550006003")
    old_conv = conversations_repo.create(
        business_id="default_business",
        channel="sms",
        customer_id=old_lead.id,
        session_id="sess-3",
    )
    old_conv.created_at = now - timedelta(days=10)

    resp = client.post("/v1/reminders/send-followups")
    assert resp.status_code == 200
    body = resp.json()
    assert body["followups_sent"] == 1

    sent = sms_service.sent_messages
    assert len(sent) == 1
    assert sent[0].to == lead.phone

    per_tenant = metrics.sms_by_business.get("default_business")
    assert per_tenant is not None
    assert per_tenant.lead_followups_sent == 1
    assert per_tenant.sms_sent_customer == 1
    assert metrics.lead_followups_sent == 1


@pytest.mark.anyio
async def test_sms_service_records_metrics_and_respects_owner_override(monkeypatch) -> None:
    # Force stub mode to avoid real Twilio calls.
    sms_service._settings.provider = "stub"  # type: ignore[attr-defined]
    sms_service._settings.owner_number = "+15550007000"  # type: ignore[attr-defined]

    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_by_business.clear()
    metrics.sms_sent_total = 0
    metrics.sms_sent_owner = 0
    metrics.sms_sent_customer = 0

    # Notify a customer.
    await sms_service.notify_customer(
        "+15550007001",
        "Customer message",
        business_id="default_business",
    )
    # Notify owner using global owner_number.
    await sms_service.notify_owner(
        "Owner alert",
        business_id="default_business",
    )

    sent = sms_service.sent_messages
    assert {m.to for m in sent} == {"+15550007001", "+15550007000"}

    assert metrics.sms_sent_total == 2
    assert metrics.sms_sent_customer == 1
    assert metrics.sms_sent_owner == 1

    per_tenant = metrics.sms_by_business.get("default_business")
    assert per_tenant is not None
    assert per_tenant.sms_sent_total == 2
    assert per_tenant.sms_sent_customer == 1
    assert per_tenant.sms_sent_owner == 1


def test_twilio_state_store_factory_and_inmemory_behavior(monkeypatch) -> None:
    # Ensure factory defaults to in-memory when backend is memory or Redis missing.
    monkeypatch.delenv("TWILIO_STATE_BACKEND", raising=False)
    store = _create_twilio_state_store()
    assert isinstance(store, InMemoryTwilioStateStore)

    # Exercise in-memory call/session and SMS conversation flows.
    store.set_call_session("CA123", "sess-1")
    link = store.get_call_session("CA123")
    assert link is not None and link.session_id == "sess-1"
    cleared = store.clear_call_session("CA123")
    assert cleared is not None and cleared.session_id == "sess-1"
    assert store.get_call_session("CA123") is None

    store.set_sms_conversation("biz1", "+15550008001", "conv-1")
    sms_link = store.get_sms_conversation("biz1", "+15550008001")
    assert sms_link is not None and sms_link.conversation_id == "conv-1"
    cleared_sms = store.clear_sms_conversation("biz1", "+15550008001")
    assert cleared_sms is not None and cleared_sms.conversation_id == "conv-1"
    assert store.get_sms_conversation("biz1", "+15550008001") is None


def test_twilio_state_store_uses_redis_when_configured(monkeypatch) -> None:
    class DummyRedisClient:
        def __init__(self) -> None:
            self._data: dict[str, str] = {}

        def setex(self, key: str, ttl: int, value: str) -> None:
            self._data[key] = value

        def get(self, key: str) -> str | None:
            return self._data.get(key)

        def delete(self, key: str) -> None:
            self._data.pop(key, None)

    class DummyRedisModule:
        def __init__(self) -> None:
            self.last_url: str | None = None

        def from_url(self, url: str) -> DummyRedisClient:
            self.last_url = url
            return DummyRedisClient()

    dummy_module = DummyRedisModule()
    monkeypatch.setenv("TWILIO_STATE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://twilio-state:6379/2")
    monkeypatch.setattr("app.services.twilio_state.redis", dummy_module)

    store = _create_twilio_state_store()
    assert isinstance(store, RedisTwilioStateStore)

    store.set_call_session("CA456", "sess-2")
    link = store.get_call_session("CA456")
    assert link is not None and link.session_id == "sess-2"

    store.set_sms_conversation("biz2", "+15550008002", "conv-2")
    sms_link = store.get_sms_conversation("biz2", "+15550008002")
    assert sms_link is not None and sms_link.conversation_id == "conv-2"


def test_inmemory_twilio_state_prunes_expired_entries() -> None:
    store = InMemoryTwilioStateStore()

    # Seed call and SMS links that are older than their TTLs.
    old_call_created = datetime.now(UTC) - timedelta(hours=2)
    old_sms_created = datetime.now(UTC) - timedelta(days=10)

    store._call_map["CA_OLD"] = CallSessionLink(  # type: ignore[attr-defined]
        session_id="old-session",
        created_at=old_call_created,
    )
    store._sms_map[("biz-old", "+15550009999")] = SmsConversationLink(  # type: ignore[attr-defined]
        conversation_id="old-conv",
        created_at=old_sms_created,
    )

    # Accessing or clearing should trigger pruning of expired entries.
    assert store.get_call_session("CA_OLD") is None
    assert store.clear_call_session("CA_OLD") is None

    assert (
        store.get_sms_conversation("biz-old", "+15550009999") is None
    )
    assert (
        store.clear_sms_conversation("biz-old", "+15550009999") is None
    )


def test_redis_twilio_state_handles_set_and_delete_errors(monkeypatch) -> None:
    class FailingRedisClient:
        def setex(self, key: str, ttl: int, value: str) -> None:
            raise RuntimeError("setex failed")

        def get(self, key: str) -> str:
            # Return invalid JSON to exercise the decode error path.
            return "not-json"

        def delete(self, key: str) -> None:
            raise RuntimeError("delete failed")

    client = FailingRedisClient()
    store = RedisTwilioStateStore(client)  # type: ignore[arg-type]

    # set_call_session should swallow Redis errors and not raise.
    store.set_call_session("CA_FAIL", "sess-fail")

    # get_call_session should handle invalid JSON and return None.
    assert store.get_call_session("CA_FAIL") is None

    # clear_call_session should swallow delete errors and still return None.
    assert store.clear_call_session("CA_FAIL") is None
