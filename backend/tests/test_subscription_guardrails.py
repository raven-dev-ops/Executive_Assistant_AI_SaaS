from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.repositories import appointments_repo, customers_repo
from app.deps import DEFAULT_BUSINESS_ID
from app.db_models import BusinessDB


client = TestClient(app)


@pytest.mark.anyio
async def test_subscription_enforced_blocks_access(monkeypatch):
    from app.services import subscription as subscription_service

    monkeypatch.setenv("ENFORCE_SUBSCRIPTION", "true")
    config.get_settings.cache_clear()

    # Force compute_state to report a canceled subscription.
    def fake_state(business_id: str):
        return subscription_service.SubscriptionState(
            status="canceled", blocked=False, in_grace=False
        )

    monkeypatch.setattr(subscription_service, "compute_state", fake_state)

    with pytest.raises(Exception):
        await subscription_service.check_access(
            DEFAULT_BUSINESS_ID, feature="appointments", upcoming_appointments=1
        )
