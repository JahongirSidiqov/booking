"""The database itself refuses double bookings, whatever code path writes the row."""

from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.bookings.models import Booking, BookingStatusHistory, ImmutableHistoryError
from tests.factories import BookingFactory, ProviderFactory, ServiceFactory, UserFactory

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 1, 4, tzinfo=UTC)


def raw_booking(**overrides):
    service = overrides.pop("service", None) or ServiceFactory()
    fields = {
        "customer": UserFactory(),
        "provider": ProviderFactory(),
        "service": service,
        "start_at": T0,
        "end_at": T0 + timedelta(minutes=30),
        "service_name": service.name,
        "duration_minutes": 30,
        "price": service.price,
    }
    fields.update(overrides)
    return Booking.objects.create(**fields)


def test_provider_overlap_rejected_by_db():
    first = raw_booking()
    with pytest.raises(IntegrityError) as exc:
        raw_booking(
            provider=first.provider,
            start_at=T0 + timedelta(minutes=15),
            end_at=T0 + timedelta(minutes=45),
        )
    assert exc.value.__cause__.diag.constraint_name == "no_overlap_per_provider"


def test_customer_overlap_rejected_by_db():
    first = raw_booking()
    with pytest.raises(IntegrityError) as exc:
        raw_booking(customer=first.customer)
    assert exc.value.__cause__.diag.constraint_name == "no_overlap_per_customer"


def test_touching_ranges_are_allowed():
    first = raw_booking()
    raw_booking(
        provider=first.provider, start_at=first.end_at, end_at=first.end_at + timedelta(minutes=30)
    )


@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_inactive_statuses_do_not_block(status):
    first = raw_booking(status=status)
    raw_booking(provider=first.provider)


def test_start_before_end_check():
    with pytest.raises(IntegrityError):
        raw_booking(end_at=T0)


def test_idempotency_key_unique_per_customer():
    first = raw_booking(idempotency_key="k")
    with pytest.raises(IntegrityError), transaction.atomic():
        raw_booking(
            customer=first.customer,
            idempotency_key="k",
            start_at=T0 + timedelta(hours=2),
            end_at=T0 + timedelta(hours=3),
        )
    raw_booking(idempotency_key="k")  # another customer may reuse the key


def test_service_and_provider_are_protected():
    booking = BookingFactory()
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        booking.service.delete()
    with pytest.raises(ProtectedError):
        booking.provider.delete()


def test_status_history_is_append_only():
    booking = BookingFactory()
    entry = BookingStatusHistory.objects.create(booking=booking, to_status="pending")
    entry.reason = "tahrir"
    with pytest.raises(ImmutableHistoryError):
        entry.save()
    with pytest.raises(ImmutableHistoryError):
        entry.delete()
    with pytest.raises(ImmutableHistoryError):
        BookingStatusHistory.objects.filter(pk=entry.pk).update(reason="x")
    with pytest.raises(ImmutableHistoryError):
        BookingStatusHistory.objects.all().delete()
