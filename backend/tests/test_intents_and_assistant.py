from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.metrics import CallbackItem, BusinessTwilioMetrics, metrics
from app.routers.chat_api import _build_business_context
from app.services.nlu import classify_intent, classify_intent_with_metadata

client = TestClient(app)


@pytest.mark.anyio
async def test_classify_intent_heuristics():
    assert await classify_intent("burst pipe and flooding") == "emergency"
    assert await classify_intent("can you cancel my appointment") == "cancel"
    assert await classify_intent("i need to reschedule") == "reschedule"
    assert await classify_intent("book an appointment for tomorrow") == "schedule"
    assert await classify_intent("what are your hours?") == "faq"
    assert await classify_intent("hello") in {"greeting", "other"}


@pytest.mark.anyio
async def test_classify_intent_uses_history(monkeypatch):
    # Even with vague text, history should bias toward reschedule.
    meta = await classify_intent_with_metadata(
        "uhh",
        None,
        history=["I need to change my time", "tomorrow is bad"],
    )
    assert meta["intent"] == "reschedule"
    assert meta["provider"] == "heuristic"  # fallback when LLM not configured


@pytest.mark.anyio
async def test_classify_intent_llm_invalid_fallback(monkeypatch):
    from app import config as app_config
    from app.services import nlu as nlu_mod

    async def fake_llm(text, history=None):
        return "not_an_intent"

    monkeypatch.setattr(nlu_mod, "_classify_with_llm", fake_llm)
    monkeypatch.setenv("NLU_PROVIDER", "openai")
    app_config.get_settings.cache_clear()

    meta = await classify_intent_with_metadata("cancel my booking", None)
    assert meta["intent"] in {"cancel", "schedule", "other"}


def test_owner_assistant_voice_reply():
    resp = client.post(
        "/v1/owner/assistant/voice-reply",
        data={"Question": "What are my callback metrics?"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert "<Response>" in resp.text
    assert "<Say" in resp.text


def test_business_context_includes_usage():
    biz = "default_business"
    metrics.twilio_by_business[biz] = BusinessTwilioMetrics(
        voice_requests=3, sms_requests=5
    )
    now = datetime.now(UTC)
    metrics.callbacks_by_business[biz] = {
        "+15550001": CallbackItem(
            phone="+15550001",
            first_seen=now,
            last_seen=now,
            count=1,
            reason="MISSED_CALL",
        )
    }
    ctx = _build_business_context(biz)
    assert "Voice calls" in ctx
    assert "Callback queue size: 1" in ctx
