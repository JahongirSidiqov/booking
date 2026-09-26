from datetime import datetime

from django.db.models import QuerySet

from apps.accounts.models import User

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


def visible_bookings(user: User) -> QuerySet[Booking]:
    """Bookings `user` may see; anything else is reported as 404, not 403 (no enumeration)."""
    qs = Booking.objects.select_related("service", "provider", "customer")
    if user.role == User.Role.ADMIN:
        return qs
    if user.role == User.Role.PROVIDER:
        # A provider user without a linked Provider sees nothing (edge #35).
        return qs.filter(provider__user=user)
    return qs.filter(customer=user)


def can_view(user: User, booking: Booking) -> bool:
    if user.role == User.Role.ADMIN:
        return True
    if user.role == User.Role.PROVIDER:
        return booking.provider.user_id == user.pk
    return booking.customer_id == user.pk


def visible_booking(user: User, pk) -> Booking | None:
    return visible_bookings(user).prefetch_related("history__changed_by").filter(pk=pk).first()


def filter_bookings(
    qs: QuerySet[Booking],
    *,
    statuses: list[str] | None = None,
    provider_id=None,
    service_id=None,
    starts_from: datetime | None = None,
    starts_before: datetime | None = None,
    upcoming_after: datetime | None = None,
) -> QuerySet[Booking]:
    if statuses:
        qs = qs.filter(status__in=statuses)
    if provider_id:
        qs = qs.filter(provider_id=provider_id)
    if service_id:
        qs = qs.filter(service_id=service_id)
    if starts_from:
        qs = qs.filter(start_at__gte=starts_from)
    if starts_before:
        qs = qs.filter(start_at__lt=starts_before)
    if upcoming_after:
        # Upcoming = not finished yet, soonest first; history views read newest first.
        return qs.filter(end_at__gt=upcoming_after).order_by("start_at", "id")
    return qs.order_by("-start_at", "id")
