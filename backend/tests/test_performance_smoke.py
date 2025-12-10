from datetime import UTC, datetime, timedelta

from app.routers.chat_api import _build_business_context
from app.repositories import appointments_repo, conversations_repo, customers_repo


def test_load_smoke_context_build_fast():
    biz = "perf_biz"
    # Seed many appointments and conversation messages.
    if hasattr(appointments_repo, "_by_id"):
        appointments_repo._by_id.clear()  # type: ignore[attr-defined]
        appointments_repo._by_business.clear()  # type: ignore[attr-defined]
        appointments_repo._by_customer.clear()  # type: ignore[attr-defined]
    if hasattr(conversations_repo, "_by_id"):
        conversations_repo._by_id.clear()  # type: ignore[attr-defined]
        conversations_repo._by_business.clear()  # type: ignore[attr-defined]
    if hasattr(customers_repo, "_by_id"):
        customers_repo._by_id.clear()  # type: ignore[attr-defined]
        customers_repo._by_business.clear()  # type: ignore[attr-defined]
        customers_repo._by_phone.clear()  # type: ignore[attr-defined]

    cust = customers_repo.upsert(name="Perf User", phone="+155501", business_id=biz)
    now = datetime.now(UTC)
    for i in range(200):
        start = now + timedelta(days=i % 10)
        end = start + timedelta(hours=1)
        appointments_repo.create(
            customer_id=cust.id,
            start_time=start,
            end_time=end,
            service_type="Service",
            is_emergency=(i % 25 == 0),
            description="Test load",
            business_id=biz,
            calendar_event_id=f"evt_{i}",
        )

    ctx = _build_business_context(biz)
    assert "Appointments last 30d" in ctx
    assert "Voice calls" in ctx
