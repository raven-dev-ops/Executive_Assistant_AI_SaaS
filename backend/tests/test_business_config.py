from datetime import UTC, datetime

import pytest

from app import business_config
from app.config import get_settings
from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessDB


@pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE or SessionLocal is None,
    reason="Business configuration tests require database support",
)
def test_get_calendar_id_for_business_uses_db_override() -> None:
    settings = get_settings()
    default_id = settings.calendar.calendar_id

    session = SessionLocal()
    try:
        biz_id = "config_calendar_test"
        row = session.get(BusinessDB, biz_id)
        if row is None:
            row = BusinessDB(  # type: ignore[call-arg]
                id=biz_id,
                name="Config Calendar Test",
                calendar_id="tenant-calendar-id",
                created_at=datetime.now(UTC),
            )
            session.add(row)
        else:
            row.calendar_id = "tenant-calendar-id"
        session.commit()
    finally:
        session.close()

    # DB row with calendar_id should override the default setting.
    overridden = business_config.get_calendar_id_for_business(biz_id)
    assert overridden == "tenant-calendar-id"

    # Unknown tenant should fall back to the global default.
    assert (
        business_config.get_calendar_id_for_business("unknown-business") == default_id
    )


def test_get_calendar_id_for_business_falls_back_when_db_unavailable(monkeypatch) -> None:
    settings = get_settings()
    default_id = settings.calendar.calendar_id

    monkeypatch.setattr(business_config, "SQLALCHEMY_AVAILABLE", False)
    monkeypatch.setattr(business_config, "SessionLocal", None)

    # When DB support is disabled, function should always return the default.
    assert business_config.get_calendar_id_for_business("any-business") == default_id


@pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE or SessionLocal is None,
    reason="Business configuration tests require database support",
)
def test_language_vertical_and_voice_overrides_and_defaults() -> None:
    settings = get_settings()
    default_language = getattr(settings, "default_language_code", "en")
    default_vertical = getattr(settings, "default_vertical", "plumbing")
    default_voice = settings.speech.openai_tts_voice

    session = SessionLocal()
    try:
        biz_id = "config_language_vertical_voice"
        row = session.get(BusinessDB, biz_id)
        if row is None:
            row = BusinessDB(  # type: ignore[call-arg]
                id=biz_id,
                name="Config Language Vertical Voice",
                language_code="es",
                vertical="hvac",
                tts_voice="novel-voice",
                created_at=datetime.now(UTC),
            )
            session.add(row)
        else:
            row.language_code = "es"
            row.vertical = "hvac"
            row.tts_voice = "novel-voice"
        session.commit()
    finally:
        session.close()

    # Per-tenant overrides.
    assert business_config.get_language_for_business(biz_id) == "es"
    assert business_config.get_vertical_for_business(biz_id) == "hvac"
    assert business_config.get_voice_for_business(biz_id) == "novel-voice"

    # Missing business_id or unknown tenant falls back to defaults.
    assert business_config.get_language_for_business(None) == default_language
    assert (
        business_config.get_language_for_business("unknown-business")
        == default_language
    )
    assert business_config.get_vertical_for_business(None) == default_vertical
    assert (
        business_config.get_vertical_for_business("unknown-business")
        == default_vertical
    )
    assert business_config.get_voice_for_business(None) == default_voice
    assert (
        business_config.get_voice_for_business("unknown-business") == default_voice
    )

