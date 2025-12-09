from datetime import UTC, datetime, timedelta
import time

from app.repositories import appointments_repo, customers_repo
from app.routers.chat_api import _build_business_context


def test_multitenant_context_perf():
    # Seed two tenants with many appointments to ensure context generation stays fast.
    business_ids = ["perf_tenant_a", "perf_tenant_b"]
    for biz in business_ids:
        # Clear per-tenant data if the in-memory repos expose it.
        try:
            appointments_repo._by_business[biz] = []  # type: ignore[attr-defined]
            customers_repo._by_business[biz] = []  # type: ignore[attr-defined]
        except Exception:
            pass
        base_day = datetime.now(UTC) + timedelta(days=2)
        for i in range(200):
            cust = customers_repo.upsert(
                name=f"{biz}-Customer-{i}",
                phone=f"+1999{1000 + i}",
                business_id=biz,
            )
            appointments_repo.create(
                customer_id=cust.id,
                start_time=base_day + timedelta(minutes=30 * i),
                end_time=base_day + timedelta(minutes=30 * i + 30),
                service_type="test",
                is_emergency=(i % 11 == 0),
                description="Perf multi-tenant appointment",
                business_id=biz,
            )

    start = time.perf_counter()
    for biz in business_ids:
        ctx = _build_business_context(biz)
        assert "Callback queue size" in ctx
    elapsed = time.perf_counter() - start
    # All contexts should be generated quickly even under load.
    assert elapsed < 2.0
