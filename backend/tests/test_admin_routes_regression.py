from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_admin_environment_and_governance_routes():
    env_resp = client.get("/v1/admin/environment")
    assert env_resp.status_code == 200
    env_body = env_resp.json()
    assert "environment" in env_body
    gov_resp = client.get("/v1/admin/governance")
    assert gov_resp.status_code == 200
    gov_body = gov_resp.json()
    assert "multi_tenant_mode" in gov_body
    audit_resp = client.get("/v1/admin/audit")
    assert audit_resp.status_code == 200
    assert isinstance(audit_resp.json(), list)
