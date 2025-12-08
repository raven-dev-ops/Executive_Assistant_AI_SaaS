import pytest
from fastapi.testclient import TestClient

from app.db import SQLALCHEMY_AVAILABLE, SessionLocal
from app.db_models import BusinessUserDB
from app.main import app, get_settings

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE, reason="RBAC enforcement requires database support"
)


def _upsert_membership(user_id: str, role: str, business_id: str = "default_business"):
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        existing = (
            session.query(BusinessUserDB)
            .filter(
                BusinessUserDB.user_id == user_id,
                BusinessUserDB.business_id == business_id,
            )
            .one_or_none()
        )
        if existing:
            existing.role = role
            session.add(existing)
        else:
            session.add(
                BusinessUserDB(
                    id=f"bu-{user_id}",
                    business_id=business_id,
                    user_id=user_id,
                    role=role,
                )
            )
        session.commit()
    finally:
        session.close()


def test_staff_can_write_viewer_is_read_only(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "owner_dashboard_token", "dashboard-secret")

    _upsert_membership("viewer-1", "viewer")
    _upsert_membership("staff-1", "staff")

    # Missing credentials rejected when dashboard token is configured.
    resp_missing = client.get("/v1/crm/customers")
    assert resp_missing.status_code == 401

    # Viewer can read but cannot write.
    resp_view_read = client.get(
        "/v1/crm/customers",
        headers={"X-User-ID": "viewer-1", "X-Owner-Token": "dashboard-secret"},
    )
    assert resp_view_read.status_code == 200

    resp_view_write = client.post(
        "/v1/crm/customers",
        json={"name": "V Test", "phone": "+19999999"},
        headers={"X-User-ID": "viewer-1", "X-Owner-Token": "dashboard-secret"},
    )
    assert resp_view_write.status_code == 403

    # Staff can write.
    resp_staff = client.post(
        "/v1/crm/customers",
        json={"name": "S Test", "phone": "+18888888"},
        headers={"X-User-ID": "staff-1", "X-Owner-Token": "dashboard-secret"},
    )
    assert resp_staff.status_code == 200


def test_admin_api_key_allows_dashboard_access(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "owner_dashboard_token", "dashboard-secret")
    monkeypatch.setattr(settings, "admin_api_key", "admin-key")

    resp = client.get(
        "/v1/crm/customers",
        headers={"X-Admin-API-Key": "admin-key", "X-Owner-Token": "dashboard-secret"},
    )
    assert resp.status_code == 200
