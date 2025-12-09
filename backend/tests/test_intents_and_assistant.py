from datetime import UTC, datetime

from app.services.nlu import classify_intent
from app.routers.chat_api import _build_business_context
from app.metrics import metrics, BusinessTwilioMetrics, CallbackItem


import pytest
import anyio


@pytest.mark.anyio
async def test_classify_intent_heuristics():
    assert await classify_intent("burst pipe and flooding") == "emergency"
    assert await classify_intent("can you cancel my appointment") == "cancel"
    assert await classify_intent("i need to reschedule") == "reschedule"
    assert await classify_intent("book an appointment for tomorrow") == "schedule"
    assert await classify_intent("what are your hours?") == "faq"
    assert await classify_intent("hello") in {"greeting", "other"}


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
