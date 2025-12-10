from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dashboard_index_served() -> None:
    resp = client.get("/dashboard/index.html")
    assert resp.status_code == 200
    assert "AI Telephony" in resp.text


def test_admin_dashboard_served() -> None:
    resp = client.get("/dashboard/admin.html")
    assert resp.status_code == 200
    assert "Admin Dashboard" in resp.text


def test_planner_dashboard_served() -> None:
    resp = client.get("/dashboard/planner.html")
    assert resp.status_code == 200
    assert "Investor Planner" in resp.text


def test_root_redirects_to_dashboard() -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers["location"].endswith("/dashboard/index.html")
