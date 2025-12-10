import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.db_models import BusinessDB, UserDB


client = TestClient(app)


def test_register_and_set_active_business():
    password = "pw123456!"
    resp = client.post(
        "/v1/auth/register",
        json={
            "email": f"user-{uuid.uuid4().hex[:8]}@example.com",
            "password": password,
        },
    )
    assert resp.status_code == 200
    user = resp.json()
    user_id = user["id"]
    assert user["active_business_id"] == "default_business"
    session = SessionLocal()
    try:
        db_user = session.get(UserDB, user_id)
        assert db_user is not None
        assert db_user.password_hash is not None
        assert db_user.password_hash != password
        assert db_user.password_hash.startswith("$2")
    finally:
        session.close()

    me_resp = client.get("/v1/auth/me", headers={"X-User-ID": user_id})
    assert me_resp.status_code == 200

    change = client.patch(
        "/v1/auth/active-business",
        headers={"X-User-ID": user_id},
        json={"business_id": "default_business"},
    )
    assert change.status_code == 200
    assert change.json()["active_business_id"] == "default_business"


def test_login_refresh_and_me_with_bearer_token():
    email = f"login-{uuid.uuid4().hex[:8]}@example.com"
    password = "Str0ngPass!"
    reg = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 200

    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    payload = login.json()
    access = payload["access_token"]
    refresh = payload["refresh_token"]
    assert payload["user"]["email"] == email
    assert payload["user"]["roles"] == ["owner"]

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["id"] == payload["user"]["id"]

    new_tokens = client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert new_tokens.status_code == 200
    refreshed = new_tokens.json()
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]


def test_login_lockout_after_failures():
    email = f"lockout-{uuid.uuid4().hex[:8]}@example.com"
    password = "LockPass!1"
    reg = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 200

    # Exhaust allowed attempts.
    for i in range(4):
        resp = client.post(
            "/v1/auth/login", json={"email": email, "password": "wrongpass"}
        )
        assert resp.status_code == 401

    final_attempt = client.post(
        "/v1/auth/login", json={"email": email, "password": "wrongpass"}
    )
    assert final_attempt.status_code == 423
    assert final_attempt.headers.get("Retry-After") is not None

    # Even correct password is blocked during lockout window.
    locked = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert locked.status_code == 423


def test_password_reset_flow_allows_new_login():
    email = f"reset-{uuid.uuid4().hex[:8]}@example.com"
    password = "OrigPass!1"
    new_password = "NewPass!2"
    reg = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 200

    init = client.post("/v1/auth/reset/init", json={"email": email})
    assert init.status_code == 200
    token = init.json().get("reset_token")
    assert token, "reset token should be returned in testing mode"

    confirm = client.post(
        "/v1/auth/reset/confirm",
        json={"token": token, "new_password": new_password},
    )
    assert confirm.status_code == 200

    old_login = client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/v1/auth/login", json={"email": email, "password": new_password}
    )
    assert new_login.status_code == 200


def test_dashboard_role_enforced_with_business_mismatch():
    email = f"multi-{uuid.uuid4().hex[:8]}@example.com"
    password = "Str0ngPass2!"
    reg = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 200

    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Create a second business the user does not belong to.
    session = SessionLocal()
    try:
        other_id = f"biz_{uuid.uuid4().hex[:6]}"
        session.add(
            BusinessDB(
                id=other_id,
                name="Other Biz",
                api_key="key",
                calendar_id="primary",
                status="ACTIVE",
            )
        )
        session.commit()
    finally:
        session.close()

    ok = client.get("/v1/crm/customers", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200

    forbidden = client.get(
        "/v1/crm/customers",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Business-ID": other_id,
        },
    )
    assert forbidden.status_code == 403
