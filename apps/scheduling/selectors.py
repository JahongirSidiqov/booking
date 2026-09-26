from datetime import UTC, date, datetime, time, timedelta

from django.db.models import QuerySet

from apps.catalog.models import Service
from apps.common.exceptions import DomainError
from apps.providers.models import Provider, ProviderService

from . import slot_engine
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


def bookable_pair(*, service_id, provider_id) -> tuple[Service, Provider]:
    """Load a service/provider pair and check that it can take bookings at all."""
    service = Service.objects.filter(pk=service_id).first()
    provider = Provider.objects.filter(pk=provider_id).first()
    if service is None or provider is None:
        raise DomainError("NOT_FOUND", "Xizmat yoki xodim topilmadi.", 404)
    if not service.is_active or not provider.is_active:
        raise DomainError(
            "INACTIVE_RESOURCE",
            "Bu xizmat yoki xodim hozir bron qabul qilmaydi.",
            title="Faol emas",
        )
    if not ProviderService.objects.filter(provider=provider, service=service).exists():
        raise DomainError(
            "PROVIDER_NOT_OFFERING_SERVICE",
            "Tanlangan xodim bu xizmatni koʻrsatmaydi.",
            title="Xodim bu xizmatni koʻrsatmaydi",
        )
    return service, provider


def time_off_ranges(*, provider: Provider, start: datetime, end: datetime) -> list:
    return list(
        TimeOff.objects.filter(provider=provider, start_at__lt=end, end_at__gt=start)
        .order_by("start_at")
        .values_list("start_at", "end_at")
    )


def _query_window(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    # One extra day on each side covers every timezone pairing between customer and provider.
    start = datetime.combine(date_from - timedelta(days=1), time.min, tzinfo=UTC)
    end = datetime.combine(date_to + timedelta(days=2), time.min, tzinfo=UTC)
    return start, end


def _engine_inputs(provider: Provider, date_from: date, date_to: date) -> dict:
    business = BusinessSettings.load()
    start, end = _query_window(date_from, date_to)
    return {
        "settings": business,
        "rules": list(availability_rules(provider=provider)),
        "time_offs": time_off_ranges(provider=provider, start=start, end=end),
    }


def day_slots(
    *, service: Service, provider: Provider, date_local: date, tz: str, now: datetime
) -> list[slot_engine.Slot]:
    return slot_engine.get_available_slots(
        service=service,
        provider=provider,
        date_local=date_local,
        now=now,
        tz=tz,
        **_engine_inputs(provider, date_local, date_local),
    )


def days_summary(
    *, service: Service, provider: Provider, date_from: date, date_to: date, tz: str, now: datetime
) -> list[tuple[date, int]]:
    slot_engine.validate_range(date_from, date_to)
    return slot_engine.get_day_summary(
        service=service,
        provider=provider,
        date_from=date_from,
        date_to=date_to,
        now=now,
        tz=tz,
        **_engine_inputs(provider, date_from, date_to),
    )
