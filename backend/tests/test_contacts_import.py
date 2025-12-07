from fastapi.testclient import TestClient

from app.main import app
from app.repositories import customers_repo


client = TestClient(app)


def test_contacts_import_happy_path(tmp_path):
    # Ensure clean slate for in-memory customers.
    if hasattr(customers_repo, "_by_id"):
        customers_repo._by_id.clear()  # type: ignore[attr-defined]
        customers_repo._by_phone.clear()  # type: ignore[attr-defined]
        customers_repo._by_business.clear()  # type: ignore[attr-defined]

    csv_content = "Name,Phone,Email,Address\nAlice,5551234567,alice@example.com,123 Main St\nBob,5551234568,,\n"
    path = tmp_path / "contacts.csv"
    path.write_text(csv_content, encoding="utf-8")

    with path.open("rb") as f:
        files = {"file": ("contacts.csv", f, "text/csv")}
        resp = client.post("/v1/contacts/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["skipped"] == 0
    assert data["errors"] == []

    customers = customers_repo.list_for_business("default_business")
    assert len(customers) == 2


def test_contacts_import_dedupes_and_reports_errors(tmp_path):
    if hasattr(customers_repo, "_by_id"):
        customers_repo._by_id.clear()  # type: ignore[attr-defined]
        customers_repo._by_phone.clear()  # type: ignore[attr-defined]
        customers_repo._by_business.clear()  # type: ignore[attr-defined]

    csv_content = (
        "Name,Phone,Email,Address\n"
        "Alice,5551234567,alice@example.com,123 Main St\n"
        "Duplicate,5551234567,dupe@example.com,456 Side St\n"
        ",5559990000,bad@example.com,No Name Lane\n"
    )
    path = tmp_path / "contacts.csv"
    path.write_text(csv_content, encoding="utf-8")

    with path.open("rb") as f:
        files = {"file": ("contacts.csv", f, "text/csv")}
        resp = client.post("/v1/contacts/import", files=files)
    assert resp.status_code == 200
    data = resp.json()

    # One valid import, one deduped, one invalid row.
    assert data["imported"] == 1
    assert data["skipped"] >= 1
    assert len(data["errors"]) == 1
