from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.metrics import BusinessSmsMetrics, metrics
from app.repositories import appointments_repo, conversations_repo, customers_repo


client = TestClient(app)


def _reset_repos_and_metrics() -> None:
    appointments_repo._by_id.clear()  # type: ignore[attr-defined]
    appointments_repo._by_customer.clear()  # type: ignore[attr-defined]
    appointments_repo._by_business.clear()  # type: ignore[attr-defined]
    customers_repo._by_id.clear()  # type: ignore[attr-defined]
    customers_repo._by_phone.clear()  # type: ignore[attr-defined]
    customers_repo._by_business.clear()  # type: ignore[attr-defined]
    conversations_repo._by_id.clear()  # type: ignore[attr-defined]
    conversations_repo._by_business.clear()  # type: ignore[attr-defined]
    metrics.sms_by_business.clear()
    metrics.retention_by_business.clear()  # type: ignore[attr-defined]


def test_owner_segments_combines_customer_and_appointment_tags() -> None:
    _reset_repos_and_metrics()

    # Customers with overlapping and distinct tags.
    cust1 = customers_repo.upsert(
        name="Segment Customer 1",
        phone="+15550100001",
        business_id="default_business",
        tags=["vip", "maintenance"],
    )
    cust2 = customers_repo.upsert(
        name="Segment Customer 2",
        phone="+15550100002",
        business_id="default_business",
        tags=["vip", "new"],
    )

    # Appointments that contribute appointment and emergency counts.
    now = datetime.now(UTC)
    start1 = now + timedelta(days=1)
    end1 = start1 + timedelta(hours=1)
    appointments_repo.create(
        customer_id=cust1.id,
        start_time=start1,
        end_time=end1,
        service_type="Inspection",
        is_emergency=True,
        description="Emergency maintenance",
        business_id="default_business",
        calendar_event_id=None,
        tags=["maintenance", "urgent"],
        estimated_value=200,
    )

    start2 = now + timedelta(days=2)
    end2 = start2 + timedelta(hours=1)
    appointments_repo.create(
        customer_id=cust2.id,
        start_time=start2,
        end_time=end2,
        service_type="Tune-up",
        is_emergency=False,
        description="Routine tune-up",
        business_id="default_business",
        calendar_event_id=None,
        tags=["maintenance"],
        estimated_value=150,
    )

    resp = client.get("/v1/owner/segments")
    assert resp.status_code == 200
    body = resp.json()
    items = {item["tag"]: item for item in body["items"]}

    # Customer tag counts.
    assert items["vip"]["customers"] == 2
    assert items["maintenance"]["customers"] == 1
    assert items["new"]["customers"] == 1

    # Appointment tag counts and emergency counts.
    assert items["maintenance"]["appointments"] == 2
    assert items["maintenance"]["emergency_appointments"] == 1
    # "urgent" only appears on the emergency appointment.
    assert items["urgent"]["appointments"] == 1
    assert items["urgent"]["emergency_appointments"] == 1

    # Estimated value totals should accumulate per tag.
    assert items["maintenance"]["estimated_value_total"] == 350.0
    assert items["urgent"]["estimated_value_total"] == 200.0


def test_owner_followup_summary_uses_conversations_and_metrics() -> None:
    _reset_repos_and_metrics()

    now = datetime.now(UTC)

    # Recent lead with no appointment -> counted as recent_leads_without_appointments.
    lead_no_appt = customers_repo.upsert(
        name="Lead No Appt",
        phone="+15550110001",
        business_id="default_business",
    )
    conv1 = conversations_repo.create(
        business_id="default_business",
        channel="sms",
        customer_id=lead_no_appt.id,
        session_id="sess-no-appt",
    )
    conv1.created_at = now - timedelta(days=2)

    # Recent lead with an active appointment -> counted as recent_leads_with_appointments.
    lead_with_appt = customers_repo.upsert(
        name="Lead With Appt",
        phone="+15550110002",
        business_id="default_business",
    )
    conv2 = conversations_repo.create(
        business_id="default_business",
        channel="sms",
        customer_id=lead_with_appt.id,
        session_id="sess-with-appt",
    )
    conv2.created_at = now - timedelta(days=3)
    appt = appointments_repo.create(
        customer_id=lead_with_appt.id,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        service_type="Estimate",
        is_emergency=False,
        description="Follow-up test",
        business_id="default_business",
        calendar_event_id=None,
    )
    appt.status = "SCHEDULED"

    # Old conversation outside window -> ignored.
    old_lead = customers_repo.upsert(
        name="Old Lead",
        phone="+15550110003",
        business_id="default_business",
    )
    conv_old = conversations_repo.create(
        business_id="default_business",
        channel="sms",
        customer_id=old_lead.id,
        session_id="sess-old",
    )
    conv_old.created_at = now - timedelta(days=10)

    # Seed per-tenant SMS metrics for followups and retention.
    per_sms = BusinessSmsMetrics(
        sms_sent_total=3,
        sms_sent_owner=0,
        sms_sent_customer=3,
        lead_followups_sent=2,
        retention_messages_sent=1,
    )
    metrics.sms_by_business["default_business"] = per_sms

    resp = client.get("/v1/owner/followups", params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()

    assert body["window_days"] == 7
    assert body["followups_sent"] == 2
    assert body["retention_messages_sent"] == 1
    assert body["recent_leads_without_appointments"] == 1
    assert body["recent_leads_with_appointments"] == 1


def test_owner_retention_summary_aggregates_campaigns() -> None:
    _reset_repos_and_metrics()

    # Seed SMS metrics and per-campaign retention counts.
    metrics.sms_by_business["default_business"] = BusinessSmsMetrics(
        sms_sent_total=5,
        sms_sent_owner=0,
        sms_sent_customer=5,
        lead_followups_sent=0,
        retention_messages_sent=5,
    )
    metrics.retention_by_business["default_business"] = {  # type: ignore[attr-defined]
        "winback": 3,
        "annual_checkup": 2,
    }

    resp = client.get("/v1/owner/retention")
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_messages_sent"] == 5
    campaigns = {c["campaign_type"]: c for c in body["campaigns"]}
    assert campaigns["winback"]["messages_sent"] == 3
    assert campaigns["annual_checkup"]["messages_sent"] == 2
