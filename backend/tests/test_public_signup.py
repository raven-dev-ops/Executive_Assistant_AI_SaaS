import secrets

from fastapi.testclient import TestClient

from app.main import app
from app.routers import public_signup


client = TestClient(app)


def test_public_signup_rejects_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_SELF_SIGNUP", "false")

    payload = {
        "business_name": "Signup Disabled Co",
        "vertical": "plumbing",
    }
    resp = client.post("/v1/public/signup", json=payload)
    assert resp.status_code == 403


def test_public_signup_creates_new_business_with_enrichment(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_SELF_SIGNUP", "true")
    monkeypatch.setenv("DEFAULT_SERVICE_TIER", "starter")

    class IncomeProfile:
        def __init__(self, median_household_income: int) -> None:
            self.median_household_income = median_household_income

    monkeypatch.setattr(
        public_signup,
        "fetch_zip_income",
        lambda zip_code: IncomeProfile(123456),
    )

    biz_name = f"Signup Test {secrets.token_hex(4)}"
    payload = {
        "business_name": biz_name,
        "vertical": "hvac",
        "owner_phone": "+15550005001",
        "zip_code": "94105",
        "contact_name": "Owner Name",
        "contact_email": "owner@example.com",
        "website_url": "https://example.com",
    }
    resp = client.post("/v1/public/signup", json=payload)
    assert resp.status_code == 201
    body = resp.json()

    assert body["business_id"]
    assert body["name"] == biz_name
    assert body["vertical"] == "hvac"
    assert body["api_key"]
    assert body["widget_token"]
    assert body["status"] == "ACTIVE"
    assert body["owner_phone"] == "+15550005001"
    assert body["zip_code"] == "94105"
    assert body["median_household_income"] == 123456
    assert body["service_tier"] == "starter"


def test_public_signup_conflict_on_duplicate_business_name(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_SELF_SIGNUP", "true")

    name = f"Duplicate Biz {secrets.token_hex(4)}"
    payload = {
        "business_name": name,
        "vertical": "plumbing",
    }

    first = client.post("/v1/public/signup", json=payload)
    assert first.status_code == 201

    second = client.post("/v1/public/signup", json=payload)
    assert second.status_code == 409
