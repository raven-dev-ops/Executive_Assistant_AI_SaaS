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

