from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.metrics import metrics
from app.repositories import appointments_repo, customers_repo
from app.services.sms import sms_service


client = TestClient(app)


def _reset_state() -> None:
    appointments_repo._by_id.clear()
    appointments_repo._by_customer.clear()
    appointments_repo._by_business.clear()
    customers_repo._by_id.clear()
    customers_repo._by_phone.clear()
    customers_repo._by_business.clear()
    sms_service._sent.clear()  # type: ignore[attr-defined]
    metrics.sms_by_business.clear()
    metrics.retention_by_business.clear()
    metrics.sms_sent_total = 0
    metrics.sms_sent_customer = 0


def test_send_retention_campaign_sends_for_eligible_customers() -> None:
    _reset_state()

    now = datetime.now(UTC)

    # Customer with last visit well before the cutoff and no future appointment.
    eligible = customers_repo.upsert(name="Eligible", phone="+15550004001")
    old_start = now - timedelta(days=60)
    old_end = old_start + timedelta(hours=1)
    appointments_repo.create(
        customer_id=eligible.id,
        start_time=old_start,
        end_time=old_end,
        service_type="Tune-up",
        is_emergency=False,
        description="Old job",
    )

    # Customer with old visit but a future appointment (should be skipped).
    future_cust = customers_repo.upsert(name="Has Future", phone="+15550004002")
    past_start = now - timedelta(days=90)
    past_end = past_start + timedelta(hours=1)
    appointments_repo.create(
        customer_id=future_cust.id,
        start_time=past_start,
        end_time=past_end,
        service_type="Install",
        is_emergency=False,
        description="Old job",
    )
    future_start = now + timedelta(days=10)
    future_end = future_start + timedelta(hours=1)
    appointments_repo.create(
        customer_id=future_cust.id,
        start_time=future_start,
        end_time=future_end,
        service_type="Install follow-up",
        is_emergency=False,
        description="Future job",
    )

    # Customer with recent visit (should be skipped by cutoff).
    recent = customers_repo.upsert(name="Recent", phone="+15550004003")
    recent_start = now - timedelta(days=10)
    recent_end = recent_start + timedelta(hours=1)
    appointments_repo.create(
        customer_id=recent.id,
        start_time=recent_start,
        end_time=recent_end,
        service_type="Recent job",
        is_emergency=False,
        description="Recent job",
    )

    resp = client.post(
        "/v1/retention/send-retention",
        params={"min_days_since_last_visit": 30, "max_messages": 10, "campaign_type": "generic"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["retention_messages_sent"] == 1

    sent = sms_service.sent_messages
    assert len(sent) == 1
    assert sent[0].to == eligible.phone

    per_tenant = metrics.sms_by_business.get("default_business")
    assert per_tenant is not None
    assert per_tenant.retention_messages_sent == 1
    assert per_tenant.sms_sent_customer == 1

    campaigns = metrics.retention_by_business.get("default_business")
    assert campaigns is not None
    assert campaigns.get("generic") == 1


def test_send_retention_respects_sms_opt_out() -> None:
    _reset_state()

    now = datetime.now(UTC)

    opted_out = customers_repo.upsert(name="Opted Out", phone="+15550004010")
    customers_repo.set_sms_opt_out(
        opted_out.phone, business_id="default_business", opt_out=True
    )

    start = now - timedelta(days=90)
    end = start + timedelta(hours=1)
    appointments_repo.create(
        customer_id=opted_out.id,
        start_time=start,
        end_time=end,
        service_type="Old job",
        is_emergency=False,
        description="Should not receive retention SMS",
    )

    resp = client.post(
        "/v1/retention/send-retention",
        params={"min_days_since_last_visit": 30, "max_messages": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["retention_messages_sent"] == 0

    assert sms_service.sent_messages == []
    per_tenant = metrics.sms_by_business.get("default_business")
    if per_tenant is not None:
        assert per_tenant.retention_messages_sent == 0

