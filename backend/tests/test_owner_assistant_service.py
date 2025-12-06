import pytest

from app.services import owner_assistant


@pytest.mark.anyio
async def test_owner_assistant_prompts_on_empty_question() -> None:
    result = await owner_assistant.owner_assistant_service.answer("")
    assert "Please type a question" in result.answer


@pytest.mark.anyio
async def test_owner_assistant_returns_not_configured_message_when_stub_provider() -> None:
    # Ensure the service is in its default "stub" configuration.
    owner_assistant.owner_assistant_service._speech.provider = "stub"  # type: ignore[attr-defined]
    owner_assistant.owner_assistant_service._speech.openai_api_key = None  # type: ignore[attr-defined]

    result = await owner_assistant.owner_assistant_service.answer(
        "What does the dashboard show?"
    )
    assert "not fully configured yet" in result.answer


@pytest.mark.anyio
async def test_owner_assistant_falls_back_when_openai_call_fails(monkeypatch) -> None:
    # Simulate a configured OpenAI provider.
    speech = owner_assistant.owner_assistant_service._speech
    speech.provider = "openai"  # type: ignore[attr-defined]
    speech.openai_api_key = "test-key"  # type: ignore[attr-defined]

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FailingAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise RuntimeError("upstream error")

    monkeypatch.setattr(
        owner_assistant.httpx,
        "AsyncClient",
        FailingAsyncClient,
    )

    result = await owner_assistant.owner_assistant_service.answer(
        "Explain my owner metrics"
    )
    assert "wasn't able to reach the AI assistant service" in result.answer


@pytest.mark.anyio
async def test_owner_assistant_uses_openai_response_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Configure the service to use OpenAI and a test model.
    speech = owner_assistant.owner_assistant_service._speech
    speech.provider = "openai"  # type: ignore[attr-defined]
    speech.openai_api_key = "test-key"  # type: ignore[attr-defined]
    speech.openai_chat_model = "gpt-4o-mini-owner"  # type: ignore[attr-defined]

    class DummyResponse:
        def __init__(self) -> None:
            self._data = {
                "model": "gpt-4o-mini-owner",
                "choices": [
                    {
                        "message": {
                            "content": "Here is a concise answer about your metrics."
                        }
                    }
                ],
            }

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._data

    class SuccessfulAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "SuccessfulAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            return DummyResponse()

    monkeypatch.setattr(
        owner_assistant.httpx,
        "AsyncClient",
        SuccessfulAsyncClient,
    )

    result = await owner_assistant.owner_assistant_service.answer(
        "What does the 'today summary' card show?"
    )
    assert "concise answer about your metrics" in result.answer
    assert result.used_model == "gpt-4o-mini-owner"
