import logging

from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as main
from app.context import request_id_ctx
from app.logging_config import configure_logging


def test_request_id_generated_and_returned_in_response_header() -> None:
    app = main.create_app()

    @app.get("/_rid")
    async def _rid():
        return {"rid": request_id_ctx.get()}

    client = TestClient(app)
    resp = client.get("/_rid")
    assert resp.status_code == 200
    rid = resp.json().get("rid")
    assert rid
    assert resp.headers.get("X-Request-ID") == rid


def test_request_id_reused_and_logged_when_provided(caplog) -> None:
    app = main.create_app()
    logger = logging.getLogger("request-id-test")

    @app.get("/_rid_log")
    async def _rid_log():
        logger.info("rid-log-test")
        return {"rid": request_id_ctx.get()}

    client = TestClient(app)
    caplog.set_level(logging.INFO)
    configure_logging()

    custom_rid = "rid-1234"
    resp = client.get("/_rid_log", headers={"X-Request-ID": custom_rid})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_rid
    assert resp.json().get("rid") == custom_rid

    records = [rec for rec in caplog.records if rec.getMessage() == "rid-log-test"]
    assert records
    assert all(getattr(rec, "request_id", None) == custom_rid for rec in records)


def test_request_id_header_returned_on_http_exception() -> None:
    app = main.create_app()

    @app.get("/_rid_http_exception")
    async def _rid_http_exception():
        raise HTTPException(status_code=403, detail="forbidden")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/_rid_http_exception")
    assert resp.status_code == 403
    assert resp.headers.get("X-Request-ID")
