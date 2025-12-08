from fastapi import Response
from fastapi.testclient import TestClient

import app.main as main
from app.metrics import metrics


def _reset_metrics() -> None:
    metrics.total_requests = 0
    metrics.total_errors = 0
    metrics.route_metrics.clear()
    metrics.retention_purge_runs = 0
    metrics.retention_appointments_deleted = 0
    metrics.retention_conversations_deleted = 0
    metrics.retention_messages_deleted = 0


def test_create_app_handles_session_failure(monkeypatch) -> None:
    class FailingSessionFactory:
        def __call__(self):  # pragma: no cover - invoked by create_app
            raise RuntimeError("boom")

    monkeypatch.setattr(main, "SessionLocal", FailingSessionFactory())
    app = main.create_app()
    assert app.title == "AI Telephony Backend"


def test_metrics_middleware_counts_server_error_response(monkeypatch) -> None:
    _reset_metrics()
    app = main.create_app()

    @app.get("/_server_error")
    async def _server_error():
        return Response(status_code=503)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/_server_error")
    assert resp.status_code == 503
    rm = metrics.route_metrics["/_server_error"]
    assert rm.error_count == 1
    assert metrics.total_errors >= 1


def test_metrics_middleware_records_unhandled_exception(monkeypatch) -> None:
    _reset_metrics()
    app = main.create_app()

    @app.get("/_boom")
    async def _boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/_boom")
    assert resp.status_code == 500
    rm = metrics.route_metrics["/_boom"]
    assert rm.error_count == 1
    assert metrics.total_errors >= 1


def test_rate_limit_returns_429_with_retry_after(monkeypatch) -> None:
    _reset_metrics()
    settings = main.get_settings()
    settings.rate_limit_per_minute = 2
    settings.rate_limit_burst = 1
    settings.rate_limit_whitelist_ips = []
    app = main.create_app()

    client = TestClient(app)
    resp1 = client.post("/telephony/inbound", json={})
    assert resp1.status_code != 429

    resp2 = client.post("/telephony/inbound", json={})
    assert resp2.status_code == 429
    assert resp2.headers.get("Retry-After")
