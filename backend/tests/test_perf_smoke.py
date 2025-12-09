from datetime import UTC, datetime, timedelta
import time

from app.routers.chat_api import _build_business_context
from app.repositories import appointments_repo, customers_repo


def test_business_context_with_many_appointments_is_fast():
    business_id = "default_business"
    # Seed a few hundred appointments to simulate load.
    customers_repo._by_business = {}  # type: ignore[attr-defined]
    appointments_repo._by_business = {}  # type: ignore[attr-defined]
    base_day = datetime.now(UTC) + timedelta(days=1)
    for i in range(400):
        customer = customers_repo.upsert(
            name=f"Customer {i}",
            phone=f"+1555{100000 + i}",
            business_id=business_id,
        )
        appointments_repo.create(
            customer_id=customer.id,
            start_time=base_day + timedelta(minutes=30 * i),
            end_time=base_day + timedelta(minutes=30 * i + 30),
            service_type="test",
            is_emergency=(i % 7 == 0),
            description="Load test appointment",
            business_id=business_id,
        )

    start = time.perf_counter()
    ctx = _build_business_context(business_id)
    elapsed = time.perf_counter() - start
    assert "Upcoming appointments" in ctx
    # Ensure context building remains reasonably fast under load.
    assert elapsed < 1.0
