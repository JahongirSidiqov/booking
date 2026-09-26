from datetime import datetime

from django.db.models import QuerySet

from apps.providers.models import Provider

from .models import AvailabilityRule, BusinessSettings, TimeOff


def provider_timezone(provider: Provider, business: BusinessSettings) -> str:
    return provider.timezone or business.timezone


def availability_rules(*, provider: Provider) -> QuerySet[AvailabilityRule]:
    return AvailabilityRule.objects.filter(provider=provider).order_by("weekday", "start_time")


def time_off_list(
    *, provider: Provider, now: datetime, include_past: bool = False
) -> QuerySet[TimeOff]:
    qs = TimeOff.objects.filter(provider=provider)
    if not include_past:
        qs = qs.filter(end_at__gt=now)
    return qs.order_by("start_at")
