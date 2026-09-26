from datetime import datetime

from django.db.models import QuerySet

from .models import ACTIVE_STATUSES, Booking


def active_overlapping(**filters) -> QuerySet[Booking]:
    return Booking.objects.filter(status__in=ACTIVE_STATUSES, **filters)


def busy_ranges(*, provider, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    return list(
        active_overlapping(provider=provider, start_at__lt=end, end_at__gt=start)
        .order_by("start_at")
        .values_list("start_at", "end_at")
    )


def customer_has_overlap(*, customer, start: datetime, end: datetime) -> bool:
    return active_overlapping(customer=customer, start_at__lt=end, end_at__gt=start).exists()


def upcoming_active(*, now: datetime, **filters) -> QuerySet[Booking]:
    return active_overlapping(start_at__gte=now, **filters).order_by("start_at")


def booking_with_history(*, pk) -> Booking | None:
    return (
        Booking.objects.select_related("service", "provider", "customer")
        .prefetch_related("history__changed_by")
        .filter(pk=pk)
        .first()
    )
