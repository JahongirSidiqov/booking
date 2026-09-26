"""Shared scenario for booking tests: Thursday 2026-10-01, Sardor works 09:00–18:00 Tashkent."""

from datetime import time

import pytest
from freezegun import freeze_time

from tests.factories import AvailabilityRuleFactory, ProviderFactory, ServiceFactory

NOW = "2026-09-26 12:00:00"
SLOT_0900 = "2026-10-01T09:00:00+05:00"  # = 04:00Z
BOOKINGS = "/api/v1/bookings"


@pytest.fixture
def frozen_now():
    with freeze_time(NOW):
        yield


@pytest.fixture
def haircut(db):
    return ServiceFactory(name="Soch olish", duration_minutes=30)


@pytest.fixture
def sardor(haircut):
    provider = ProviderFactory(name="Sardor", with_services=[haircut])
    AvailabilityRuleFactory(provider=provider, weekday=3, start_time=time(9), end_time=time(18))
    return provider


def booking_body(service, provider, start_at=SLOT_0900, **extra):
    return {
        "service_id": str(service.pk),
        "provider_id": str(provider.pk),
        "start_at": start_at,
        **extra,
    }
