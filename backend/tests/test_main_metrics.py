from fastapi import HTTPException, Response
from fastapi.testclient import TestClient

import app.main as main
from app.metrics import metrics


def _reset_metrics() -> None:
    metrics.total_requests = 0
    metrics.total_errors = 0
    metrics.route_metrics.clear()


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

    client = TestClient(app)
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
