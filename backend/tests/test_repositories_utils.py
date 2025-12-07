from datetime import UTC, datetime, timedelta

from app import repositories


def test_split_and_join_tags_round_trip_and_cleaning() -> None:
    raw = " emergency , high value , , repeat "
    tags = repositories._split_tags(raw)  # type: ignore[attr-defined]
    assert tags == ["emergency", "high value", "repeat"]

    joined = repositories._join_tags(tags)  # type: ignore[attr-defined]
    assert joined == "emergency,high value,repeat"

    assert repositories._split_tags(None) == []  # type: ignore[attr-defined]
    assert repositories._join_tags([]) is None  # type: ignore[attr-defined]


def test_inmemory_conversation_repository_get_by_session() -> None:
    repo = repositories.InMemoryConversationRepository()
    conv = repo.create(
        channel="sms",
        customer_id="cust-1",
        session_id="sess-abc",
        business_id="biz-1",
    )

    by_id = repo.get(conv.id)
    assert by_id is not None and by_id.session_id == "sess-abc"

    by_session = repo.get_by_session("sess-abc")
    assert by_session is not None and by_session.id == conv.id

    assert repo.get_by_session("missing") is None


def test_inmemory_appointment_repository_update_fields() -> None:
    repo = repositories.InMemoryAppointmentRepository()
    now = datetime.now(UTC)
    end = now + timedelta(hours=1)

    appt = repo.create(
        customer_id="cust-1",
        start_time=now,
        end_time=end,
        service_type="Install",
        is_emergency=False,
        description="Initial",
        estimated_value=100,
        business_id="biz-1",
        tags=["tag1"],
    )

    updated = repo.update(
        appt.id,
        description="Updated description",
        is_emergency=True,
        status="CONFIRMED",
        tags=["tag2", "tag3"],
        quoted_value=250,
        quote_status="PROPOSED",
        technician_id="tech-1",
    )
    assert updated is not None
    assert updated.description == "Updated description"
    assert updated.is_emergency is True
    assert updated.status == "CONFIRMED"
    assert updated.tags == ["tag2", "tag3"]
    assert updated.quoted_value == 250.0
    assert updated.quote_status == "PROPOSED"
    assert updated.technician_id == "tech-1"


def test_inmemory_customer_repository_get_by_phone_scopes_business() -> None:
    repo = repositories.InMemoryCustomerRepository()
    # Same phone, different tenants.
    cust_a = repo.upsert(name="A", phone="555", business_id="biz-1")
    cust_b = repo.upsert(name="B", phone="555", business_id="biz-2")

    assert repo.get_by_phone("555", business_id="biz-1") == cust_a
    assert repo.get_by_phone("555", business_id="biz-2") == cust_b
    # Fallback across tenants returns last inserted when no business specified.
    assert repo.get_by_phone("555").id == cust_b.id

    # Opt-out flag toggles only for matching business.
    repo.set_sms_opt_out("555", business_id="biz-1", opt_out=True)
    assert repo.get_by_phone("555", business_id="biz-1").sms_opt_out is True
    assert repo.get_by_phone("555", business_id="biz-2").sms_opt_out is False


def test_inmemory_customer_repository_upsert_updates_existing() -> None:
    repo = repositories.InMemoryCustomerRepository()
    original = repo.upsert(
        name="Original",
        phone="123",
        email="orig@example.com",
        address=None,
        tags=["one", "two"],
    )
    updated = repo.upsert(
        name="Updated",
        phone="123",
        email="new@example.com",
        address="123 Main",
        tags=["three"],
    )
    assert updated.id == original.id
    assert updated.name == "Updated"
    assert updated.email == "new@example.com"
    assert updated.address == "123 Main"
    assert updated.tags == ["three"]


def test_inmemory_customer_repository_get_by_phone_missing_returns_none() -> None:
    repo = repositories.InMemoryCustomerRepository()
    assert repo.get_by_phone("missing") is None
    repo.set_sms_opt_out("missing", business_id="biz-1", opt_out=True)


def test_inmemory_conversation_repository_append_and_list() -> None:
    repo = repositories.InMemoryConversationRepository()
    conv1 = repo.create(channel="sms", business_id="biz-1")
    conv2 = repo.create(channel="voice", business_id="biz-1")
    conv_other = repo.create(channel="sms", business_id="biz-2")

    repo.append_message(conv1.id, role="user", text="Hello")
    repo.append_message(conv1.id, role="assistant", text="Hi!")
    repo.append_message("missing", role="user", text="ignore")

    listed = repo.list_for_business("biz-1")
    assert {c.id for c in listed} == {conv1.id, conv2.id}
    assert len(conv1.messages) == 2
    assert conv1.messages[0].text == "Hello"
    assert conv1.messages[1].role == "assistant"

    # Ensure other tenant conversations are not mixed.
    assert {c.id for c in repo.list_for_business("biz-2")} == {conv_other.id}
