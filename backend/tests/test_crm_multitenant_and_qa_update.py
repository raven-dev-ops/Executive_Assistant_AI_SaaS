from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.repositories import appointments_repo, conversations_repo, customers_repo
from app.routers import crm as crm_module


client = TestClient(app)


def test_crm_customers_and_conversations_are_tenant_isolated() -> None:
    # Create customers for two different tenants.
    cust_default = customers_repo.upsert(
        name="Default Tenant Customer",
        phone="+15550001001",
        business_id="default_business",
    )
    cust_other = customers_repo.upsert(
        name="Other Tenant Customer",
        phone="+15550001002",
        business_id="biz-other",
    )

    # Default tenant view should only see the default customer.
    resp_default = client.get("/v1/crm/customers")
    assert resp_default.status_code == 200
    ids_default = {c["id"] for c in resp_default.json()}
    assert cust_default.id in ids_default
    assert cust_other.id not in ids_default

    # Explicit other-tenant view via X-Business-ID should not see default customer.
    resp_other = client.get(
        "/v1/crm/customers",
        headers={"X-Business-ID": "biz-other"},
    )
    assert resp_other.status_code == 200
    ids_other = {c["id"] for c in resp_other.json()}
    assert cust_other.id in ids_other
    assert cust_default.id not in ids_other


def test_update_conversation_qa_persists_flags_tags_outcome_and_notes() -> None:
    # Seed a customer, appointment, and conversation.
    customer = customers_repo.upsert(
        name="QA Update Customer",
        phone="+15550002001",
        business_id="default_business",
    )
    now = datetime.now(UTC)
    appointments_repo.create(
        customer_id=customer.id,
        start_time=now,
        end_time=now + timedelta(hours=1),
        service_type="Inspection",
        is_emergency=False,
        description="QA update appointment",
        business_id="default_business",
        calendar_event_id=None,
    )

    conv = conversations_repo.create(
        channel="sms",
        customer_id=customer.id,
        business_id="default_business",
        session_id="sess-qa-update",
    )
    conversations_repo.append_message(conv.id, role="user", text="How much does this cost?")
    conversations_repo.append_message(
        conv.id, role="assistant", text="We will send you a quote."
    )

    # Apply QA updates via PATCH.
    patch_resp = client.patch(
        f"/v1/crm/conversations/{conv.id}/qa",
        json={
            "flagged_for_review": True,
            "tags": ["pricing", "followup"],
            "outcome": "Quote requested",
            "notes": "Customer requested detailed price breakdown.",
        },
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()

    assert body["id"] == conv.id
    assert body["flagged_for_review"] is True
    assert body["tags"] == ["pricing", "followup"]
    assert body["outcome"] == "Quote requested"
    assert body["notes"] == "Customer requested detailed price breakdown."

    # QA suggestions should still be present and derived from the updated outcome.
    qa = body.get("qa_suggestions")
    assert qa is not None
    normalize = crm_module._normalize_outcome_label  # type: ignore[attr-defined]
    expected_label = normalize("Quote requested")
    assert qa["likely_outcome"] == expected_label

