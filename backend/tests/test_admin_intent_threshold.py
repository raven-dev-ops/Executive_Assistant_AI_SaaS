from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.db_models import BusinessDB


client = TestClient(app)


def test_admin_sets_intent_threshold():
    session = SessionLocal()
    try:
        row = session.get(BusinessDB, "default_business")
        row.intent_threshold = None
        session.add(row)
        session.commit()
    finally:
        session.close()

    resp = client.patch(
        "/v1/admin/businesses/default_business",
        json={"intent_threshold": 0.6},
        headers={"X-Admin-API-Key": "dev-admin-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["intent_threshold"] - 0.6) < 1e-3

    session = SessionLocal()
    try:
        row = session.get(BusinessDB, "default_business")
        assert row.intent_threshold == 60
    finally:
        session.close()
