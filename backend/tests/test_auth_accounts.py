import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_register_and_set_active_business():
    resp = client.post(
        "/v1/auth/register",
        params={"email": f"user-{uuid.uuid4().hex[:8]}@example.com", "password": "pw123"},
    )
    assert resp.status_code == 200
    user = resp.json()
    user_id = user["id"]
    assert user["active_business_id"] == "default_business"

    me_resp = client.get("/v1/auth/me", headers={"X-User-ID": user_id})
    assert me_resp.status_code == 200

    change = client.patch(
        "/v1/auth/active-business",
        headers={"X-User-ID": user_id},
        json={"business_id": "default_business"},
    )
    assert change.status_code == 200
    assert change.json()["active_business_id"] == "default_business"
