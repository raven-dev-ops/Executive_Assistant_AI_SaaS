from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import appointments_repo, customers_repo


client = TestClient(app)


def _reset_repos() -> None:
    appointments_repo._by_id.clear()  # type: ignore[attr-defined]
    appointments_repo._by_customer.clear()  # type: ignore[attr-defined]
    appointments_repo._by_business.clear()  # type: ignore[attr-defined]
    customers_repo._by_id.clear()  # type: ignore[attr-defined]
    customers_repo._by_phone.clear()  # type: ignore[attr-defined]
    customers_repo._by_business.clear()  # type: ignore[attr-defined]


def test_owner_quotes_summarizes_quote_stages_and_conversions() -> None:
    _reset_repos()

    now = datetime.now(UTC)

    # Customer 1: has a quote-stage appointment and a later booked job.
    c1_resp = client.post(
        "/v1/crm/customers",
        json={"name": "Quote Customer 1", "phone": "555-7001"},
    )
    c1_id = c1_resp.json()["id"]

    start_quote1 = now - timedelta(days=5)
    end_quote1 = start_quote1 + timedelta(hours=1)
    client.post(
        "/v1/crm/appointments",
        json={
            "customer_id": c1_id,
            "start_time": start_quote1.isoformat(),
            "end_time": end_quote1.isoformat(),
            "service_type": "tankless_water_heater",
            "is_emergency": False,
            "description": "Estimate sent",
            "estimated_value": 500.0,
            "job_stage": "Estimate Sent",
            "quoted_value": 600.0,
            "quote_status": "PRESENTED",
        },
    )

    start_booked1 = now - timedelta(days=3)
    end_booked1 = start_booked1 + timedelta(hours=2)
    client.post(
        "/v1/crm/appointments",
        json={
            "customer_id": c1_id,
            "start_time": start_booked1.isoformat(),
            "end_time": end_booked1.isoformat(),
            "service_type": "tankless_water_heater",
            "is_emergency": True,
            "description": "Booked job after quote",
            "estimated_value": 700.0,
            "job_stage": "Booked Job",
        },
    )

    # Customer 2: quote-stage appointment only, no booked job yet.
    c2_resp = client.post(
        "/v1/crm/customers",
        json={"name": "Quote Customer 2", "phone": "555-7002"},
    )
    c2_id = c2_resp.json()["id"]

    start_quote2 = now - timedelta(days=4)
    end_quote2 = start_quote2 + timedelta(hours=1)
    client.post(
        "/v1/crm/appointments",
        json={
            "customer_id": c2_id,
            "start_time": start_quote2.isoformat(),
            "end_time": end_quote2.isoformat(),
            "service_type": "drain_or_sewer",
            "is_emergency": False,
            "description": "Lead proposal",
            "estimated_value": 400.0,
            "job_stage": "Lead - Proposal",
        },
    )

    resp = client.get("/v1/owner/quotes", params={"days": 30})
    assert resp.status_code == 200
    body = resp.json()

    # Two quote-stage appointments across two customers; one converted.
    assert body["total_quotes"] == 2
    assert body["quote_customers"] == 2
    assert body["quote_customers_converted"] == 1

    # Estimated and quoted totals should reflect both quote-stage appointments.
    assert body["total_quote_value"] == pytest.approx(500.0 + 400.0)
    # For the second quote, quoted_value falls back to estimated_value.
    assert body["total_quoted_value"] == pytest.approx(600.0 + 400.0)

    # Stage buckets should include both quote stages with appropriate values.
    stage_map = {s["stage"]: s for s in body["stages"]}
    est_stage = stage_map["Estimate Sent"]
    lead_stage = stage_map["Lead - Proposal"]

    assert est_stage["count"] == 1
    assert est_stage["estimated_value_total"] == pytest.approx(500.0)
    assert est_stage["quoted_value_total"] == pytest.approx(600.0)

    assert lead_stage["count"] == 1
    assert lead_stage["estimated_value_total"] == pytest.approx(400.0)
    assert lead_stage["quoted_value_total"] == pytest.approx(400.0)

    # Status buckets should include explicit quote_status and the default QUOTED.
    status_map = {b["status"]: b for b in body["by_status"]}
    presented = status_map["PRESENTED"]
    quoted = status_map["QUOTED"]

    assert presented["count"] == 1
    assert presented["quoted_value_total"] == pytest.approx(600.0)

    assert quoted["count"] == 1
    assert quoted["quoted_value_total"] == pytest.approx(400.0)

