from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.repositories import appointments_repo, conversations_repo, customers_repo


client = TestClient(app)


def _reset_repos() -> None:
    appointments_repo._by_id.clear()  # type: ignore[attr-defined]
    appointments_repo._by_customer.clear()  # type: ignore[attr-defined]
    appointments_repo._by_business.clear()  # type: ignore[attr-defined]
    conversations_repo._by_id.clear()  # type: ignore[attr-defined]
    conversations_repo._by_business.clear()  # type: ignore[attr-defined]
    customers_repo._by_id.clear()  # type: ignore[attr-defined]
    customers_repo._by_phone.clear()  # type: ignore[attr-defined]
    customers_repo._by_business.clear()  # type: ignore[attr-defined]


def test_list_conversations_maps_service_type_and_has_appointments_per_customer() -> None:
    _reset_repos()

    # Customer with an active appointment and multiple conversations.
    customer = customers_repo.upsert(
        name="Conv Customer",
        phone="+15550300001",
        business_id="default_business",
    )
    now = datetime.now(UTC)
    start = now + timedelta(days=1)
    end = start + timedelta(hours=1)
    appt = appointments_repo.create(
        customer_id=customer.id,
        start_time=start,
        end_time=end,
        service_type="Water heater install",
        is_emergency=False,
        description="Install job",
        business_id="default_business",
        calendar_event_id=None,
    )
    appt.status = "SCHEDULED"

    conv1 = conversations_repo.create(
        channel="sms",
        customer_id=customer.id,
        business_id="default_business",
        session_id="sess-1",
    )
    conv2 = conversations_repo.create(
        channel="phone",
        customer_id=customer.id,
        business_id="default_business",
        session_id="sess-2",
    )
    conversations_repo.append_message(conv1.id, role="user", text="Hi")
    conversations_repo.append_message(conv2.id, role="assistant", text="Hello")

    resp = client.get("/v1/crm/conversations")
    assert resp.status_code == 200
    body = resp.json()
    by_id = {c["id"]: c for c in body}

    # All conversations for the customer should reflect aggregated service_type and has_appointments.
    for cid in (conv1.id, conv2.id):
        item = by_id[cid]
        assert item["customer_id"] == customer.id
        assert item["service_type"] == "Water heater install"
        assert item["has_appointments"] is True
        # message_count should match the number of messages appended.
        assert item["message_count"] == 1


def test_customer_timeline_interleaves_appointments_and_conversations_per_tenant() -> None:
    _reset_repos()

    # Customer in default tenant with one appointment and one conversation.
    customer = customers_repo.upsert(
        name="Timeline Customer",
        phone="+15550300002",
        business_id="default_business",
    )
    now = datetime.now(UTC)
    appt_time = now + timedelta(hours=1)
    appt = appointments_repo.create(
        customer_id=customer.id,
        start_time=appt_time,
        end_time=appt_time + timedelta(hours=1),
        service_type="Leak repair",
        is_emergency=False,
        description="Timeline job",
        business_id="default_business",
        calendar_event_id=None,
    )
    conv = conversations_repo.create(
        channel="sms",
        customer_id=customer.id,
        business_id="default_business",
        session_id="sess-tl",
    )
    conv.created_at = now

    # Another tenant's appointment and conversation for the same customer ID should be ignored.
    appointments_repo.create(
        customer_id=customer.id,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        service_type="Other tenant job",
        is_emergency=False,
        description="Other tenant",
        business_id="other_business",
        calendar_event_id=None,
    )
    conv_other = conversations_repo.create(
        channel="sms",
        customer_id=customer.id,
        business_id="other_business",
        session_id="sess-other",
    )
    conv_other.created_at = now + timedelta(minutes=30)

    resp = client.get(
        f"/v1/crm/customers/{customer.id}/timeline",
        headers={"X-Business-ID": "default_business"},
    )
    assert resp.status_code == 200
    items = resp.json()

    # Only the default tenant's appointment and conversation should appear.
    types = [i["type"] for i in items]
    ids = {i["id"] for i in items}
    assert "appointment" in types
    assert "conversation" in types
    assert appt.id in ids
    assert conv.id in ids
    # Other-tenant conversation must not show up.
    assert conv_other.id not in ids

