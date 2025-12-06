import logging
from typing import Any, Dict, Iterable, Tuple

import anyio
import pytest
from fastapi import Request

from app.services import audit as audit_module


def _make_request(headers: Dict[str, str]) -> Request:
    raw_headers: Iterable[Tuple[bytes, bytes]] = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()
    ]
    scope: Dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/test-path",
        "raw_path": b"/test-path",
        "scheme": "http",
        "query_string": b"",
        "headers": list(raw_headers),
        "client": ("testclient", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_derive_actor_assigns_roles_and_business_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audit_module,
        "_resolve_business_id_from_headers",
        lambda request: "biz-123",
    )

    cases = [
        ("admin", {"X-Admin-API-Key": "k"}),
        ("owner_dashboard", {"X-Owner-Token": "t"}),
        ("tenant_api", {"X-API-Key": "tenant-key"}),
        ("widget", {"X-Widget-Token": "w"}),
        ("anonymous", {}),
    ]

    for expected_role, headers in cases:
        req = _make_request(headers)
        actor = audit_module._derive_actor(req)
        assert actor.role == expected_role
        assert actor.business_id == "biz-123"


def test_resolve_business_id_uses_explicit_header_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Even when SQLAlchemy is available, if there is no API key or widget token,
    # the resolver should return X-Business-ID directly without a DB lookup.
    monkeypatch.setattr(audit_module, "SQLALCHEMY_AVAILABLE", True)

    class DummySession:
        def close(self) -> None:  # pragma: no cover - trivial
            return None

    monkeypatch.setattr(audit_module, "SessionLocal", lambda: DummySession())

    req = _make_request({"X-Business-ID": "explicit-biz"})
    resolved = audit_module._resolve_business_id_from_headers(req)
    assert resolved == "explicit-biz"


def test_resolve_business_id_uses_db_for_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_module, "SQLALCHEMY_AVAILABLE", True)

    class DummyBusiness:
        def __init__(self) -> None:
            self.id = "biz-from-db"

    class DummyQuery:
        def __init__(self, key: str) -> None:
            self._key = key

        def filter(self, *args, **kwargs) -> "DummyQuery":  # type: ignore[no-untyped-def]
            return self

        def one_or_none(self) -> DummyBusiness | None:
            return DummyBusiness() if self._key == "good-key" else None

    class DummySession:
        def query(self, model):  # type: ignore[no-untyped-def]
            return DummyQuery(self._key)  # type: ignore[attr-defined]

        def close(self) -> None:  # pragma: no cover - trivial
            return None

        def __init__(self, key: str) -> None:
            self._key = key

    def session_local() -> DummySession:
        return DummySession("good-key")

    monkeypatch.setattr(audit_module, "SessionLocal", session_local)

    req = _make_request({"X-API-Key": "good-key", "X-Business-ID": "fallback"})
    resolved = audit_module._resolve_business_id_from_headers(req)
    assert resolved == "biz-from-db"


def test_record_audit_event_logs_when_db_unavailable(caplog, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the "DB unavailable" branch.
    monkeypatch.setattr(audit_module, "SQLALCHEMY_AVAILABLE", False)
    monkeypatch.setattr(audit_module, "SessionLocal", None)

    req = _make_request({"X-Business-ID": "log-biz"})

    with caplog.at_level(logging.INFO, logger=audit_module.__name__):
        anyio.run(audit_module.record_audit_event, req, 204)

    records = [r for r in caplog.records if r.message == "audit_event"]
    assert records, "Expected an audit_event log entry when DB is unavailable"
    rec = records[0]
    # extra fields should be attached to the log record.
    assert rec.actor_type == "anonymous"
    assert rec.business_id == "log-biz"
    assert rec.path == "/test-path"
    assert rec.method == "GET"
    assert rec.status_code == 204


def test_record_audit_event_handles_db_errors_gracefully(caplog, monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a real session factory wrapped with a failing commit to hit the exception branch.
    assert audit_module.SessionLocal is not None
    real_factory = audit_module.SessionLocal

    class FailingSession:
        def __init__(self) -> None:
            self._inner = real_factory()

        def add(self, obj) -> None:  # type: ignore[no-untyped-def]
            self._inner.add(obj)

        def commit(self) -> None:
            raise RuntimeError("forced commit failure")

        def close(self) -> None:
            self._inner.close()

    monkeypatch.setattr(audit_module, "SQLALCHEMY_AVAILABLE", True)
    monkeypatch.setattr(audit_module, "SessionLocal", lambda: FailingSession())

    req = _make_request({})

    with caplog.at_level(logging.ERROR, logger=audit_module.__name__):
        # Exceptions from commit should be swallowed and logged, not propagated.
        anyio.run(audit_module.record_audit_event, req, 500)

    assert any(
        "audit_event_persist_failed" in r.message for r in caplog.records
    ), "Expected a log entry when audit event persistence fails"

