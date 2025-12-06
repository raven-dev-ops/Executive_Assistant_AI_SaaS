from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_metrics_json_reflects_new_requests() -> None:
    # Capture current metrics snapshot.
    before = client.get("/metrics")
    assert before.status_code == 200
    before_body = before.json()

    total_before = before_body["total_requests"]
    route_metrics_before = before_body.get("route_metrics", {})
    health_before = route_metrics_before.get("/healthz", {}).get("request_count", 0)
    ready_before = route_metrics_before.get("/readyz", {}).get("request_count", 0)

    # Issue a couple of requests that should be tracked by the middleware.
    resp_health = client.get("/healthz")
    assert resp_health.status_code == 200
    resp_ready = client.get("/readyz")
    assert resp_ready.status_code == 200

    # Fetch metrics again; this request is also counted.
    after = client.get("/metrics")
    assert after.status_code == 200
    after_body = after.json()

    total_after = after_body["total_requests"]
    route_metrics_after = after_body.get("route_metrics", {})
    health_after = route_metrics_after.get("/healthz", {}).get("request_count", 0)
    ready_after = route_metrics_after.get("/readyz", {}).get("request_count", 0)

    # Between the two snapshots we issued three requests: /healthz, /readyz, /metrics.
    assert total_after >= total_before + 3
    assert health_after == health_before + 1
    assert ready_after == ready_before + 1


def test_metrics_prometheus_exposes_core_counters_and_route_labels() -> None:
    resp = client.get("/metrics/prometheus")
    assert resp.status_code == 200
    text = resp.text

    # Core counters should be present.
    assert "ai_telephony_total_requests" in text
    assert "ai_telephony_twilio_voice_requests" in text
    assert "ai_telephony_voice_session_requests" in text

    # Per-route metrics should include a label with the path.
    assert 'ai_telephony_route_request_count{' in text
    assert 'path="/metrics/prometheus"' in text

