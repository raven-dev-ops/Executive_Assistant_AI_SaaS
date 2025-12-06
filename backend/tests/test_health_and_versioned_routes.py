from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app


client = TestClient(app)


def test_readyz_reports_database_status() -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "database" in body
    db = body["database"]
    assert "available" in db and "healthy" in db


def test_readyz_status_ok_when_db_healthy(monkeypatch) -> None:
    """Ready when database connectivity check succeeds."""

    class DummySession:
        def execute(self, query: str) -> None:  # pragma: no cover - trivial
            return None

        def close(self) -> None:  # pragma: no cover - trivial
            return None

    def dummy_session_local() -> DummySession:
        return DummySession()

    monkeypatch.setattr(main_module, "SQLALCHEMY_AVAILABLE", True)
    monkeypatch.setattr(main_module, "SessionLocal", dummy_session_local)

    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == {"available": True, "healthy": True}


def test_readyz_status_degraded_when_db_unhealthy(monkeypatch) -> None:
    """Degraded when database connectivity check fails."""

    class FailingSession:
        def execute(self, query: str) -> None:  # pragma: no cover - trivial
            raise RuntimeError("db down")

        def close(self) -> None:  # pragma: no cover - trivial
            return None

    def failing_session_local() -> FailingSession:
        return FailingSession()

    monkeypatch.setattr(main_module, "SQLALCHEMY_AVAILABLE", True)
    monkeypatch.setattr(main_module, "SessionLocal", failing_session_local)

    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["database"] == {"available": True, "healthy": False}


def test_versioned_telephony_alias_flow_matches_legacy() -> None:
    inbound_resp = client.post(
        "/v1/telephony/inbound", json={"caller_phone": "555-3333"}
    )
    assert inbound_resp.status_code == 200
    inbound_body = inbound_resp.json()
    session_id = inbound_body["session_id"]
    assert session_id

    audio_resp = client.post(
        "/v1/telephony/audio",
        json={"session_id": session_id, "text": "Alias Caller"},
    )
    assert audio_resp.status_code == 200
    audio_body = audio_resp.json()
    assert audio_body["session_state"]["caller_name"] == "Alias Caller"

    end_resp = client.post("/v1/telephony/end", json={"session_id": session_id})
    assert end_resp.status_code == 200
    assert "ended" in end_resp.json()["status"]


def test_versioned_twilio_aliases_exist() -> None:
    # SMS alias
    sms_resp = client.post(
        "/v1/twilio/sms",
        data={"From": "+15550000000", "Body": "Hello"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert sms_resp.status_code == 200
    assert "<Response>" in sms_resp.text

    # Voice alias
    voice_resp = client.post(
        "/v1/twilio/voice",
        data={"CallSid": "CA-alias-1", "From": "+15550000001"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert voice_resp.status_code == 200
    assert "<Response>" in voice_resp.text
