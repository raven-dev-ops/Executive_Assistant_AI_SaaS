from datetime import UTC, datetime, timedelta

import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import (
    USE_DB_CONVERSATIONS,
    appointments_repo,
    conversations_repo,
    customers_repo,
)
from app.routers import crm as crm_module


client = TestClient(app)


def test_normalize_outcome_label_maps_common_cases() -> None:
    normalize = crm_module._normalize_outcome_label  # type: ignore[attr-defined]

    assert normalize("Booked – confirmed") == "booked"
    assert normalize("Cancelled / no show") == "lost"
    assert normalize("Quote requested, still shopping") == "price_shopper"
    assert normalize("") is None
    assert normalize("   ") is None
    # Unrecognized labels are normalized to lowercase but kept as-is.
    assert normalize("Needs follow-up") == "needs follow-up"


def test_build_heuristic_qa_suggestions_emergency_paths() -> None:
    class DummyConv:
        def __init__(self, outcome: str, tags: list[str] | None = None) -> None:
            self.outcome = outcome
            self.tags = tags or []

    build = crm_module._build_heuristic_qa_suggestions  # type: ignore[attr-defined]

    # Emergency booked: should be treated as handled correctly.
    conv_booked = DummyConv("Booked emergency job", tags=["emergency"])
    suggestion_booked = build(conv_booked, service_type="emergency_repair", has_appointments=True)
    assert suggestion_booked.likely_outcome == "booked"
    assert suggestion_booked.followup_needed is None
    assert suggestion_booked.emergency_handled_ok == "yes"
    assert suggestion_booked.source == "heuristic"

    # Emergency lost with no appointment: should be flagged as not handled.
    conv_lost = DummyConv("Lost emergency call", tags=[])
    suggestion_lost = build(conv_lost, service_type=None, has_appointments=False)
    assert suggestion_lost.likely_outcome == "lost"
    assert suggestion_lost.followup_needed is False
    assert suggestion_lost.emergency_handled_ok == "no"


@pytest.mark.skipif(
    USE_DB_CONVERSATIONS,
    reason="Conversation QA test currently assumes in-memory conversations repository",
)
def test_get_conversation_includes_heuristic_qa_suggestions() -> None:
    # Seed a customer, an appointment, and a conversation with emergency context.
    customer = customers_repo.upsert(
        name="QA Customer",
        phone="+15550001234",
        business_id="default_business",
    )
    now = datetime.now(UTC)
    appointments_repo.create(
        customer_id=customer.id,
        start_time=now,
        end_time=now + timedelta(hours=1),
        service_type="Emergency repair",
        is_emergency=True,
        description="Emergency booking",
        business_id="default_business",
        calendar_event_id=None,
    )

    conv = conversations_repo.create(
        channel="phone",
        customer_id=customer.id,
        business_id="default_business",
    )
    # In the in-memory repository, this object is stored by reference, so
    # updating attributes here will be visible to get_conversation.
    conv.tags = ["emergency"]  # type: ignore[attr-defined]
    conv.outcome = "Booked emergency job"  # type: ignore[attr-defined]
    conversations_repo.append_message(conv.id, role="user", text="My basement is flooded")
    conversations_repo.append_message(
        conv.id, role="assistant", text="We booked an emergency visit for you."
    )

    resp = client.get(f"/v1/crm/conversations/{conv.id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["id"] == conv.id
    assert body["service_type"] in (None, "Emergency repair")
    assert body["has_appointments"] is True
    assert len(body["messages"]) >= 2

    qa = body.get("qa_suggestions")
    assert qa is not None
    assert qa["likely_outcome"] == "booked"
    assert qa["emergency_handled_ok"] == "yes"
    # Heuristic source should be preserved when no LLM provider is configured.
    assert qa["source"] == "heuristic"


@pytest.mark.skipif(
    USE_DB_CONVERSATIONS,
    reason="Conversation QA test currently assumes in-memory conversations repository",
)
def test_maybe_llm_enrich_qa_suggestions_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # Configure speech provider to use OpenAI so the LLM enrichment path is exercised.
    class DummySpeechCfg:
        def __init__(self) -> None:
            self.provider = "openai"
            self.openai_api_key = "test-key"
            self.openai_api_base = "https://example.com/v1"
            self.openai_tts_model = "gpt-4o-mini"

    class DummySettings:
        def __init__(self) -> None:
            self.speech = DummySpeechCfg()

    monkeypatch.setattr(crm_module, "get_settings", lambda: DummySettings())

    # Build a dummy conversation-like object with a small transcript.
    class DummyMessage:
        def __init__(self, role: str, text: str) -> None:
            self.role = role
            self.text = text

    class DummyConv:
        def __init__(self) -> None:
            self.messages = [
                DummyMessage("user", "Hi, I would like a quote."),
                DummyMessage("assistant", "Sure, we can provide an estimate."),
            ]
            self.flagged_for_review = True
            self.outcome = "Quote requested"

    conv = DummyConv()
    heuristic = crm_module.ConversationQaSuggestion(  # type: ignore[attr-defined]
        likely_outcome="price_shopper",
        followup_needed=True,
        emergency_handled_ok="not_emergency",
        source="heuristic",
    )

    # Dummy HTTPX client that returns a structured JSON completion.
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"likely_outcome": "booked", "followup_needed": false, "emergency_handled_ok": "not_emergency"}'  # noqa: E501
                        }
                    }
                ]
            }

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def __aenter__(self) -> "DummyAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        async def post(self, url, headers=None, json=None):  # type: ignore[no-untyped-def]
            return DummyResponse()

    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)

    # Run the async enrichment helper via anyio to avoid depending on pytest-asyncio.
    import anyio

    async def _run() -> crm_module.ConversationQaSuggestion:  # type: ignore[attr-defined]
        return await crm_module._maybe_llm_enrich_qa_suggestions(  # type: ignore[attr-defined]
            conv,
            heuristic,
            service_type=None,
            has_appointments=False,
        )

    enriched = anyio.run(_run)

    assert enriched.likely_outcome == "booked"
    assert enriched.followup_needed is False
    assert enriched.emergency_handled_ok == "not_emergency"
    assert enriched.source == "llm"
