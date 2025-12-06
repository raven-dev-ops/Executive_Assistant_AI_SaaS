import base64

import pytest

from app.services import stt_tts


@pytest.mark.anyio
async def test_transcribe_returns_empty_for_placeholder_audio() -> None:
    result = await stt_tts.speech_service.transcribe("audio://placeholder")
    assert result == ""


@pytest.mark.anyio
async def test_transcribe_returns_empty_when_not_configured() -> None:
    stt_tts.speech_service._settings.provider = "stub"  # type: ignore[attr-defined]
    stt_tts.speech_service._settings.openai_api_key = None  # type: ignore[attr-defined]

    result = await stt_tts.speech_service.transcribe(
        base64.b64encode(b"audio-bytes").decode("ascii")
    )
    assert result == ""


@pytest.mark.anyio
async def test_transcribe_handles_invalid_base64(monkeypatch) -> None:
    stt_tts.speech_service._settings.provider = "openai"  # type: ignore[attr-defined]
    stt_tts.speech_service._settings.openai_api_key = "test-key"  # type: ignore[attr-defined]

    result = await stt_tts.speech_service.transcribe("not-valid-base64")
    assert result == ""


@pytest.mark.anyio
async def test_transcribe_returns_text_on_success(monkeypatch) -> None:
    stt_tts.speech_service._settings.provider = "openai"  # type: ignore[attr-defined]
    stt_tts.speech_service._settings.openai_api_key = "test-key"  # type: ignore[attr-defined]

    class FakeResponse:
        def __init__(self) -> None:
            self._data = {"text": "hello world"}

        def raise_for_status(self) -> None:  # pragma: no cover - trivial
            return None

        def json(self) -> dict:
            return self._data

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(stt_tts.httpx, "AsyncClient", FakeClient)

    audio_b64 = base64.b64encode(b"audio-bytes").decode("ascii")
    result = await stt_tts.speech_service.transcribe(audio_b64)
    assert result == "hello world"


@pytest.mark.anyio
async def test_synthesize_returns_placeholder_when_not_configured() -> None:
    stt_tts.speech_service._settings.provider = "stub"  # type: ignore[attr-defined]
    stt_tts.speech_service._settings.openai_api_key = None  # type: ignore[attr-defined]

    result = await stt_tts.speech_service.synthesize("Hello world")
    assert result == "audio://placeholder"


@pytest.mark.anyio
async def test_synthesize_returns_placeholder_on_error(monkeypatch) -> None:
    stt_tts.speech_service._settings.provider = "openai"  # type: ignore[attr-defined]
    stt_tts.speech_service._settings.openai_api_key = "test-key"  # type: ignore[attr-defined]

    class FailingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FailingClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise RuntimeError("network error")

    monkeypatch.setattr(stt_tts.httpx, "AsyncClient", FailingClient)

    result = await stt_tts.speech_service.synthesize("Hello world")
    assert result == "audio://placeholder"


@pytest.mark.anyio
async def test_synthesize_returns_base64_audio_on_success(monkeypatch) -> None:
    stt_tts.speech_service._settings.provider = "openai"  # type: ignore[attr-defined]
    stt_tts.speech_service._settings.openai_api_key = "test-key"  # type: ignore[attr-defined]

    class FakeResponse:
        def __init__(self) -> None:
            self.content = b"binary-audio"

        def raise_for_status(self) -> None:  # pragma: no cover - trivial
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(stt_tts.httpx, "AsyncClient", FakeClient)

    result = await stt_tts.speech_service.synthesize("Hello world")
    decoded = base64.b64decode(result.encode("ascii"))
    assert decoded == b"binary-audio"

