from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_admin_metrics_and_audit_listing():
    # Audit listing should return a list rather than erroring.
    audits = client.get("/v1/admin/audit")
    assert audits.status_code == 200
    assert isinstance(audits.json(), list)


def test_admin_business_listing_and_export():
    resp = client.get("/v1/admin/businesses")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

    # CSV export should return 200 and CSV content-type (usage export)
    export = client.get("/v1/admin/businesses/usage.csv")
    assert export.status_code == 200
    assert "text/csv" in export.headers.get("content-type", "")
