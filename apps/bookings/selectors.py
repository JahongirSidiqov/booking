from datetime import datetime

from django.db.models import Count, Q, QuerySet

from apps.accounts.models import User

from .models import ACTIVE_STATUSES, Booking


def active_overlapping(**filters) -> QuerySet[Booking]:
    return Booking.objects.filter(status__in=ACTIVE_STATUSES, **filters)


def busy_ranges(*, provider, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """When the provider is occupied: each active booking plus its buffer (to blocked_until)."""
    return list(
        active_overlapping(provider=provider, start_at__lt=end, blocked_until__gt=start)
        .order_by("start_at")
        .values_list("start_at", "blocked_until")
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
    search: str = "",
) -> QuerySet[Booking]:
    if search:
        qs = qs.filter(
            Q(customer__full_name__icontains=search)
            | Q(customer__email__icontains=search)
            | Q(customer__phone__icontains=search)
            | Q(service_name__icontains=search)
        )
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


def customer_tab(user: User, tab: str, *, now: datetime) -> QuerySet[Booking]:
    """'Bronlarim' tabs: upcoming (active, not finished), past, cancelled."""
    qs = visible_bookings(user).filter(customer=user)
    if tab == "cancelled":
        return qs.filter(status=Booking.Status.CANCELLED).order_by("-start_at")
    if tab == "past":
        return qs.filter(
            Q(status=Booking.Status.COMPLETED) | Q(status__in=ACTIVE_STATUSES, end_at__lte=now)
        ).order_by("-start_at")
    return qs.filter(status__in=ACTIVE_STATUSES, end_at__gt=now).order_by("start_at")


def overlapping(qs: QuerySet[Booking], *, start: datetime, end: datetime) -> QuerySet[Booking]:
    return qs.filter(start_at__lt=end, end_at__gt=start)


def day_kpis(qs: QuerySet[Booking]) -> dict:
    """Counts for the dashboard header; `qs` is already limited to one day and one viewer."""
    counts = qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Booking.Status.PENDING)),
        cancelled=Count("id", filter=Q(status=Booking.Status.CANCELLED)),
    )
    counts["booked"] = counts["total"] - counts["cancelled"]
    counts["cancelled_pct"] = (
        round(100 * counts["cancelled"] / counts["total"]) if counts["total"] else 0
    )
    return counts


def upcoming_counts(field: str, *, now: datetime) -> dict:
    """{provider_id or service_id: number of future active bookings} for deactivation warnings."""
    rows = (
        active_overlapping(start_at__gte=now)
        .values(field)
        .annotate(n=Count("id"))
        .values_list(field, "n")
    )
    return dict(rows)
