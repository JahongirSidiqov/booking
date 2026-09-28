from datetime import UTC, date, datetime, time, timedelta

from django.db.models import QuerySet

from apps.bookings import selectors as booking_selectors
from apps.catalog.models import Service
from apps.common.exceptions import DomainError
from apps.providers import selectors as provider_selectors
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


def engine_inputs(provider: Provider, date_from: date, date_to: date) -> dict:
    """Everything the slot engine needs about one provider for a range of dates."""
    business = BusinessSettings.load()
    start, end = _query_window(date_from, date_to)
    return {
        "settings": business,
        "rules": list(availability_rules(provider=provider)),
        "time_offs": time_off_ranges(provider=provider, start=start, end=end),
        "busy_ranges": booking_selectors.busy_ranges(provider=provider, start=start, end=end),
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
        **engine_inputs(provider, date_local, date_local),
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
        **engine_inputs(provider, date_from, date_to),
    )


def offering_providers(*, service: Service) -> list[Provider]:
    """Active providers who offer an active `service` (the "any provider" candidates)."""
    return list(provider_selectors.provider_list(service_id=service.pk))


def any_provider_day_slots(
    *, service: Service, date_local: date, tz: str, now: datetime
) -> list[slot_engine.Slot]:
    return slot_engine.union_slots(
        day_slots(service=service, provider=p, date_local=date_local, tz=tz, now=now)
        for p in offering_providers(service=service)
    )


def any_provider_days_summary(
    *, service: Service, date_from: date, date_to: date, tz: str, now: datetime
) -> list[tuple[date, int]]:
    """Free starts per day across all providers — a union, so counts are not summed."""
    slot_engine.validate_range(date_from, date_to)
    providers = offering_providers(service=service)
    inputs = {p.pk: engine_inputs(p, date_from, date_to) for p in providers}
    summary = []
    day = date_from
    while day <= date_to:
        per_provider = (
            slot_engine.get_available_slots(
                service=service, provider=p, date_local=day, now=now, tz=tz, **inputs[p.pk]
            )
            for p in providers
        )
        summary.append((day, len(slot_engine.union_slots(per_provider))))
        day += timedelta(days=1)
    return summary


def bookable_service(*, service_id) -> Service:
    """The service half of bookable_pair, for bookings without a chosen provider."""
    service = Service.objects.filter(pk=service_id).first()
    if service is None:
        raise DomainError("NOT_FOUND", "Xizmat topilmadi.", 404)
    if not service.is_active:
        raise DomainError(
            "INACTIVE_RESOURCE",
            "Bu xizmat hozir bron qabul qilmaydi.",
            title="Faol emas",
        )
    return service
