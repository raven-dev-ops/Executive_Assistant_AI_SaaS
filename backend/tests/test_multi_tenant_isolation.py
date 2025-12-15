import os

import pytest
from fastapi.testclient import TestClient

from app import config, deps, main
from app.db import SessionLocal, SQLALCHEMY_AVAILABLE
from app.db_models import BusinessDB


def _ensure_business(business_id: str, name: str = "Test Biz") -> None:
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        pytest.skip("Database support is required for multi-tenant isolation tests")
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, business_id)
        if row is None:
            row = BusinessDB(id=business_id, name=name, status="ACTIVE")  # type: ignore[arg-type]
            session.add(row)
            session.commit()
    finally:
        session.close()


def _delete_business(business_id: str) -> None:
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        return
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, business_id)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()


def test_startup_fails_when_multi_tenant_without_require_flag(monkeypatch):
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        pytest.skip("Database support is required for multi-tenant isolation tests")
    # Seed two tenants to simulate multi-tenant mode.
    _ensure_business("default_business", "Default")
    extra_id = "second_business_for_test"
    _ensure_business(extra_id, "Second")

    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("REQUIRE_BUSINESS_API_KEY", "false")
    config.get_settings.cache_clear()
    deps.get_settings.cache_clear()

    try:
        with pytest.raises(RuntimeError):
            main.create_app()
    finally:
        # Cleanup to avoid impacting other tests.
        _delete_business(extra_id)


def test_missing_credentials_rejected_when_multi_tenant(monkeypatch):
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        pytest.skip("Database support is required for multi-tenant isolation tests")
    _ensure_business("default_business", "Default")
    extra_id = "second_business_for_test2"
    _ensure_business(extra_id, "Second")

    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("REQUIRE_BUSINESS_API_KEY", "true")
    config.get_settings.cache_clear()
    deps.get_settings.cache_clear()

    try:
        app = main.create_app()
        client = TestClient(app)
        resp = client.get("/v1/widget/business")
        assert resp.status_code == 401
        assert "Missing tenant credentials" in resp.text
    finally:
        _delete_business(extra_id)


def test_unknown_business_rejected_in_multi_tenant(monkeypatch):
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        pytest.skip("Database support is required for multi-tenant isolation tests")
    _ensure_business("default_business", "Default")
    extra_id = "second_business_for_test3"
    _ensure_business(extra_id, "Second")

    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("REQUIRE_BUSINESS_API_KEY", "true")
    config.get_settings.cache_clear()
    deps.get_settings.cache_clear()

    try:
        app = main.create_app()
        client = TestClient(app)
        resp = client.get(
            "/v1/widget/business",
            headers={"X-Business-ID": "nonexistent", "X-Owner-Token": "owner"},
        )
        assert resp.status_code == 404
    finally:
        _delete_business(extra_id)


def test_owner_token_requires_explicit_business_in_multi_tenant(monkeypatch):
    if not (SQLALCHEMY_AVAILABLE and SessionLocal is not None):
        pytest.skip("Database support is required for multi-tenant isolation tests")
    _ensure_business("default_business", "Default")
    extra_id = "second_business_owner_token"
    _ensure_business(extra_id, "Second")

    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("REQUIRE_BUSINESS_API_KEY", "false")
    monkeypatch.setenv("OWNER_DASHBOARD_TOKEN", "owner-secret")
    config.get_settings.cache_clear()
    deps.get_settings.cache_clear()

    try:
        app = main.create_app()
        client = TestClient(app)
        # Missing X-Business-ID should be rejected in multi-tenant mode.
        resp = client.get(
            "/v1/owner/business",
            headers={"X-Owner-Token": "owner-secret"},
        )
        assert resp.status_code == 401
        # Providing explicit tenant should succeed.
        ok = client.get(
            "/v1/owner/business",
            headers={"X-Owner-Token": "owner-secret", "X-Business-ID": "default_business"},
        )
        assert ok.status_code == 200
    finally:
        _delete_business(extra_id)
