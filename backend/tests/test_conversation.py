import asyncio

import pytest

from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB
from app.services.conversation import (
    ConversationManager,
    _get_emergency_keywords_for_business,
    _get_service_duration_overrides,
    _infer_duration_minutes,
    _infer_quote_for_service_type,
    _infer_service_type,
    _normalize_lead_source,
)
from app.services.sessions import CallSession
from app.repositories import customers_repo


def run(coro):
    return asyncio.run(coro)


def test_conversation_happy_path_standard_job():
    session = CallSession(id="test", caller_phone="555-0000")
    manager = ConversationManager()

    # Initial prompt with no text.
    result = run(manager.handle_input(session, None))
    assert "assistant" in result.reply_text.lower()
    assert result.new_state["stage"] == "ASK_NAME"

    # Provide name.
    result = run(manager.handle_input(session, "John Smith"))
    assert "what is the service address" in result.reply_text.lower()
    assert result.new_state["caller_name"] == "John Smith"

    # Provide address.
    result = run(manager.handle_input(session, "123 Main St, Merriam KS"))
    assert "briefly describe what's going on" in result.reply_text.lower()
    assert result.new_state["address"].startswith("123 Main St")

    # Provide problem summary.
    result = run(manager.handle_input(session, "Leaking faucet in the kitchen"))
    assert "thanks for the details" in result.reply_text.lower()
    assert result.new_state["stage"] == "ASK_SCHEDULE"
    assert result.new_state["is_emergency"] is False

    # Accept scheduling.
    result = run(manager.handle_input(session, "yes that works"))
    assert "does that time work for you" in result.reply_text.lower()
    assert result.new_state["stage"] == "CONFIRM_SLOT"
    assert "proposed_slot" in result.new_state

    # Confirm slot.
    result = run(manager.handle_input(session, "yes"))
    assert "you're all set" in result.reply_text.lower()
    assert result.new_state["status"] == "SCHEDULED"


def test_conversation_emergency_flag_and_followup():
    session = CallSession(id="test2", caller_phone="555-1111")
    manager = ConversationManager()

    # Move to problem description quickly.
    run(manager.handle_input(session, None))  # greeting
    run(manager.handle_input(session, "Jane Doe"))  # name
    run(manager.handle_input(session, "456 Elm St, KC MO"))  # address

    # Emergency description.
    result = run(
        manager.handle_input(session, "Basement is flooding and sewage backing up")
    )
    assert result.new_state["is_emergency"] is True
    assert result.new_state["stage"] == "ASK_SCHEDULE"

    # Decline scheduling now.
    result = run(manager.handle_input(session, "no, just take my info"))
    assert "won't schedule anything right now" in result.reply_text.lower()
    assert result.new_state["status"] == "PENDING_FOLLOWUP"


def test_conversation_greets_returning_customer():
    # Seed an existing customer for the default business.
    customers_repo.upsert(
        name="Existing Customer",
        phone="555-9999",
        email=None,
        address="789 Oak St, KC MO",
        business_id="default_business",
    )
    session = CallSession(
        id="test3", caller_phone="555-9999", business_id="default_business"
    )
    manager = ConversationManager()

    result = run(manager.handle_input(session, None))
    text = result.reply_text.lower()
    assert "assistant" in text
    assert "worked with you before" in text
    assert result.new_state["stage"] == "ASK_NAME"


def test_conversation_reuses_address_for_returning_customer():
    # Seed an existing customer with a known address.
    customers_repo.upsert(
        name="Returning Customer",
        phone="555-2222",
        email=None,
        address="1010 Cedar St, Merriam KS",
        business_id="default_business",
    )
    session = CallSession(
        id="addr1", caller_phone="555-2222", business_id="default_business"
    )
    manager = ConversationManager()

    # Greeting (no text).
    run(manager.handle_input(session, None))
    # Provide name to advance to ASK_ADDRESS.
    run(manager.handle_input(session, "Returning Customer"))
    # At ASK_ADDRESS with no new text, the assistant should offer the known address.
    result = run(manager.handle_input(session, None))
    text = result.reply_text.lower()
    assert "have your address as" in text
    assert result.new_state["stage"] == "CONFIRM_ADDRESS"
    assert "1010 cedar st" in text

    # Confirm use of the stored address.
    result = run(manager.handle_input(session, "yes that works"))
    assert result.new_state["stage"] == "ASK_PROBLEM"
    # Session state should carry the stored address forward.
    assert result.new_state["address"].startswith("1010 Cedar St")


def test_infer_service_type_basic_keywords():
    # Tankless specialization.
    assert (
        _infer_service_type("Navien tankless water heater install")
        == "tankless_water_heater"
    )

    # General water heater.
    assert _infer_service_type("replace old water heater") == "water_heater"

    # Drain/sewer issues.
    assert _infer_service_type("main sewer line backing up") == "drain_or_sewer"

    # Fixtures/leaks.
    assert _infer_service_type("kitchen faucet is leaking") == "fixture_or_leak_repair"

    # Gas line.
    assert _infer_service_type("suspected gas leak by stove") == "gas_line"


def test_infer_duration_minutes_defaults_reasonable():
    # Tankless jobs should block a larger window.
    assert (
        _infer_duration_minutes(
            "Navien tankless water heater install",
            False,
            None,
        )
        >= 180
    )
    # Simple fixture/leak repair should stay around an hour.
    assert (
        45
        <= _infer_duration_minutes(
            "kitchen faucet is leaking",
            False,
            None,
        )
        <= 90
    )


@pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE or SessionLocal is None,
    reason="Emergency keyword and duration overrides require database support",
)
def test_emergency_keywords_and_duration_overrides_use_business_settings() -> None:
    # Configure a tenant-specific emergency keyword list and service duration overrides.
    session = SessionLocal()
    try:
        biz_id = "conversation_config_test"
        row = session.get(BusinessDB, biz_id)
        if row is None:
            row = BusinessDB(  # type: ignore[call-arg]
                id=biz_id,
                name="Conversation Config Test",
                emergency_keywords="overflow, backup",
                service_duration_config="drain_or_sewer=45,general_plumbing=30,bad=abc,negative=-5",
            )
            session.add(row)
        else:
            row.emergency_keywords = "overflow, backup"
            row.service_duration_config = (
                "drain_or_sewer=45,general_plumbing=30,bad=abc,negative=-5"
            )
        session.commit()
    finally:
        session.close()

    keywords = _get_emergency_keywords_for_business(biz_id)
    assert "overflow" in keywords
    assert "backup" in keywords

    overrides = _get_service_duration_overrides(biz_id)
    assert overrides["drain_or_sewer"] == 45
    assert overrides["general_plumbing"] == 30
    # Invalid entries should be ignored.
    assert "bad" not in overrides
    assert "negative" not in overrides

    # Duration inference should respect overrides and emergency floor.
    normal_duration = _infer_duration_minutes(
        "main sewer line backing up", False, biz_id
    )
    assert normal_duration == 45

    emergency_duration = _infer_duration_minutes(
        "kitchen faucet is leaking", True, biz_id
    )
    # Override is 30, but emergencies should be at least 60 minutes.
    assert emergency_duration >= 60


def test_infer_quote_for_service_type_ranges_and_emergency_markup() -> None:
    low, high = _infer_quote_for_service_type("drain_or_sewer", is_emergency=False)
    assert low is not None and high is not None
    assert low < high

    # Unknown service type should return (None, None).
    none_low, none_high = _infer_quote_for_service_type("unknown_type", False)
    assert none_low is None and none_high is None

    # Emergency markup should increase the range.
    em_low, em_high = _infer_quote_for_service_type("drain_or_sewer", True)
    assert em_low is not None and low is not None
    assert em_low > low
    assert em_high > high


def test_normalize_lead_source_labels_and_campaign() -> None:
    assert _normalize_lead_source("phone") == "Phone"
    assert _normalize_lead_source("web", "Google Ads - KS") == "Web ? Google Ads - KS"
    # Unknown channels should be title-cased.
    assert _normalize_lead_source("facebook") == "Facebook"
