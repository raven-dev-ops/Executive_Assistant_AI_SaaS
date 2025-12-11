from __future__ import annotations

import pytest

from app import repositories as repo
from app.metrics import BusinessSmsMetrics, BusinessTwilioMetrics, metrics
from app.services import nlu
from app.services.owner_assistant import OwnerAssistantService


class _FakeSpeech:
    provider = "openai"
    openai_api_key = "test-key"
    openai_chat_model = "gpt-4o-mini"
    openai_api_base = "https://api.openai.com/v1"


class _FakeNlu:
    intent_provider = "openai"
    intent_confidence_threshold = 0.35


class _FakeSettings:
    speech = _FakeSpeech()
    nlu = _FakeNlu()


@pytest.mark.asyncio
async def test_intent_heuristic_wins_for_emergencies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(nlu, "get_settings", lambda: _FakeSettings())

    async def _fake_llm(text, history=None):
        return "faq"

    monkeypatch.setattr(nlu, "_classify_with_llm", _fake_llm)
    result = await nlu.classify_intent_with_metadata("burst pipe in basement")
    assert result["intent"] == "emergency"
    assert result["provider"] == "heuristic"


@pytest.mark.asyncio
async def test_intent_llm_used_when_low_confidence(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(nlu, "get_settings", lambda: _FakeSettings())

    async def _fake_llm(text, history=None):
        return "faq"

    monkeypatch.setattr(nlu, "_classify_with_llm", _fake_llm)
    result = await nlu.classify_intent_with_metadata(
        "maybe you can help?", history=["hi"]
    )
    assert result["intent"] == "faq"
    assert result["provider"] == "openai"


def test_transcript_capture_opt_out(monkeypatch: pytest.MonkeyPatch):
    class _FakeSettingsCapture:
        capture_transcripts = False

    monkeypatch.setattr(repo, "get_settings", lambda: _FakeSettingsCapture())
    conv = repo.conversations_repo.create(channel="voice", business_id="tenant-1")
    repo.conversations_repo.append_message(conv.id, role="user", text="hello world")
    conv_after = repo.conversations_repo.get(conv.id)
    assert not getattr(conv_after, "messages", [])


@pytest.mark.asyncio
async def test_owner_assistant_includes_metrics(monkeypatch: pytest.MonkeyPatch):
    class _FakeSpeechStub:
        provider = "stub"
        openai_api_key = None
        openai_chat_model = "gpt-4o-mini"
        openai_api_base = "https://api.openai.com/v1"

    class _FakeSettingsOA:
        speech = _FakeSpeechStub()

    monkeypatch.setattr(
        "app.services.owner_assistant.get_settings", lambda: _FakeSettingsOA()
    )
    # Populate a small metrics snapshot.
    metrics.twilio_by_business["biz-1"] = BusinessTwilioMetrics(
        voice_requests=3, voice_errors=1, sms_requests=2, sms_errors=0
    )
    metrics.sms_by_business["biz-1"] = BusinessSmsMetrics(
        sms_sent_owner=1,
        sms_sent_customer=2,
        lead_followups_sent=1,
        retention_messages_sent=2,
        sms_opt_out_events=1,
    )

    service = OwnerAssistantService()
    reply = await service.answer("how are we doing?", business_id="biz-1")
    lower = reply.answer.lower()
    assert "voice requests" in lower
    assert "sms sent" in lower
