"""DB-level guarantees for scheduling tables, checked without the service layer."""

from datetime import UTC, datetime, time

import pytest
from django.db import IntegrityError

from apps.scheduling.models import AvailabilityRule, BusinessSettings, TimeOff
from tests.factories import ProviderFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(("start", "end"), [(time(10), time(10)), (time(22), time(2))])
def test_rule_must_start_before_end(start, end):
    with pytest.raises(IntegrityError):
        AvailabilityRule.objects.create(
            provider=ProviderFactory(), weekday=0, start_time=start, end_time=end
        )


def test_rule_weekday_range():
    with pytest.raises(IntegrityError):
        AvailabilityRule.objects.create(
            provider=ProviderFactory(), weekday=7, start_time=time(9), end_time=time(10)
        )


def test_time_off_must_start_before_end():
    moment = datetime(2026, 10, 1, 4, tzinfo=UTC)
    with pytest.raises(IntegrityError):
        TimeOff.objects.create(provider=ProviderFactory(), start_at=moment, end_at=moment)


def test_settings_is_a_singleton():
    BusinessSettings.load()
    with pytest.raises(IntegrityError):
        BusinessSettings.objects.create(id=2)


def test_settings_load_is_idempotent():
    assert BusinessSettings.load().pk == BusinessSettings.load().pk == 1


def test_settings_step_must_be_a_supported_value():
    obj = BusinessSettings.load()
    obj.slot_step_minutes = 7
    with pytest.raises(IntegrityError):
        obj.save()
