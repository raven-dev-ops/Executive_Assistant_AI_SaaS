import logging

from fastapi.testclient import TestClient

import app.main as main
from app import config, deps
from app.context import business_id_ctx, request_id_ctx, trace_id_ctx
from app.logging_config import configure_logging


def test_business_id_hint_propagates_to_context_and_logs(caplog) -> None:
    app = main.create_app()
    logger = logging.getLogger("biz-correlation-test")

    @app.get("/_biz")
    async def _biz():
        logger.info("biz-log-test")
        return {"business_id": business_id_ctx.get(), "rid": request_id_ctx.get()}

    client = TestClient(app)
    caplog.set_level(logging.INFO)
    configure_logging()

    resp = client.get("/_biz", headers={"X-Business-ID": "biz_123"})
    assert resp.status_code == 200
    assert resp.json()["business_id"] == "biz_123"
    assert resp.json()["rid"]

    records = [rec for rec in caplog.records if rec.getMessage() == "biz-log-test"]
    assert records
    assert any(getattr(rec, "business_id", None) == "biz_123" for rec in records)


def test_trace_id_from_cloud_trace_context_header(caplog) -> None:
    app = main.create_app()
    logger = logging.getLogger("trace-correlation-test")

    @app.get("/_trace")
    async def _trace():
        logger.info("trace-log-test")
        return {"trace_id": trace_id_ctx.get()}

    client = TestClient(app)
    caplog.set_level(logging.INFO)
    configure_logging()

    trace_id = "105445aa7843bc8bf206b120001000"
    resp = client.get(
        "/_trace",
        headers={"X-Cloud-Trace-Context": f"{trace_id}/1;o=1"},
    )
    assert resp.status_code == 200
    assert resp.json()["trace_id"] == trace_id

    records = [rec for rec in caplog.records if rec.getMessage() == "trace-log-test"]
    assert records
    assert any(getattr(rec, "trace_id", None) == trace_id for rec in records)


def test_twilio_sms_message_sid_is_logged(caplog, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("SMS_PROVIDER", "stub")
    monkeypatch.setenv("VERIFY_TWILIO_SIGNATURES", "false")
    config.get_settings.cache_clear()
    deps.get_settings.cache_clear()

    app = main.create_app()
    client = TestClient(app)
    caplog.set_level(logging.INFO)
    configure_logging()

    resp = client.post(
        "/twilio/sms?business_id=default_business",
        data={"From": "+15550001111", "Body": "Hello", "MessageSid": "SM123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200

    records = [
        rec for rec in caplog.records if rec.getMessage() == "twilio_sms_webhook"
    ]
    assert records
    assert any(getattr(rec, "message_sid", None) == "SM123" for rec in records)
