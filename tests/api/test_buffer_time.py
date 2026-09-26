"""Bonus: buffer time after a service — the provider is busy, the customer is not."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.scheduling.slot_engine import Rule, get_available_slots
from tests.api.test_auth import assert_problem
from tests.bookings_setup import BOOKINGS, booking_body, frozen_now, haircut, sardor
from tests.factories import (
    AvailabilityRuleFactory,
    BookingFactory,
    ProviderFactory,
    ServiceFactory,
    UserFactory,
)

__all__ = ["frozen_now", "haircut", "sardor"]

THU = date(2026, 10, 1)
NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def tashkent(h, m=0):
    return datetime.combine(THU, time(h, m), tzinfo=UTC) - timedelta(hours=5)


def slots(*, duration=30, buffer=0, busy=(), step=15, window=(time(9), time(18))):
    return [
        s.start_at
        for s in get_available_slots(
            service=SimpleNamespace(duration_minutes=duration, buffer_after_minutes=buffer),
            provider=SimpleNamespace(timezone=None),
            date_local=THU,
            now=NOW,
            settings=SimpleNamespace(
                timezone="Asia/Tashkent",
                slot_step_minutes=step,
                min_lead_time_minutes=60,
                max_advance_days=30,
            ),
            rules=[Rule(3, *window)],
            busy_ranges=busy,
        )
    ]


# --- slot engine --------------------------------------------------------------------------


def test_existing_booking_buffer_pushes_next_slot():
    # 09:00–09:30 booked with a 10-minute buffer: provider busy until 09:40.
    busy = [(tashkent(9), tashkent(9, 40))]
    assert slots(busy=busy)[0] == tashkent(9, 45)
    assert slots(busy=busy, step=5)[0] == tashkent(9, 40)


def test_candidate_buffer_must_not_run_into_next_booking():
    busy = [(tashkent(10), tashkent(10, 30))]
    assert tashkent(9, 30) in slots(busy=busy)  # no buffer: 09:30–10:00 fits exactly
    with_buffer = slots(busy=busy, buffer=15)
    assert tashkent(9, 15) in with_buffer  # 09:15–09:45 + 15 = 10:00
    assert tashkent(9, 30) not in with_buffer


def test_buffer_may_run_past_closing_time():
    # Cleanup after the last customer happens after hours; it must not remove the last slot.
    assert slots(buffer=15)[-1] == tashkent(17, 30)


# --- database -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_save_derives_blocked_until_from_buffer():
    booking = BookingFactory(start_at=tashkent(9), buffer_minutes=10)
    assert booking.end_at == tashkent(9, 30)
    assert booking.blocked_until == tashkent(9, 40)


@pytest.mark.django_db
def test_db_rejects_booking_inside_previous_buffer():
    first = BookingFactory(start_at=tashkent(9), buffer_minutes=10)
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        BookingFactory(provider=first.provider, service=first.service, start_at=tashkent(9, 30))
    assert exc.value.__cause__.diag.constraint_name == "no_overlap_per_provider"
    BookingFactory(provider=first.provider, service=first.service, start_at=tashkent(9, 40))


@pytest.mark.django_db
def test_customer_is_not_blocked_by_buffer():
    first = BookingFactory(start_at=tashkent(9), buffer_minutes=15)
    BookingFactory(customer=first.customer, start_at=tashkent(9, 30))  # other provider


@pytest.mark.django_db
def test_blocked_until_cannot_precede_end():
    booking = BookingFactory(start_at=tashkent(9))
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.filter(pk=booking.pk).update(blocked_until=tashkent(9, 10))


@pytest.mark.django_db
@pytest.mark.parametrize("minutes", [7, 125])
def test_service_buffer_check(minutes):
    with pytest.raises(IntegrityError), transaction.atomic():
        ServiceFactory(buffer_after_minutes=minutes)


# --- API ----------------------------------------------------------------------------------


@pytest.fixture
def beard_and_cut(db):
    service = ServiceFactory(name="Soch va soqol", duration_minutes=30, buffer_after_minutes=10)
    provider = ProviderFactory(with_services=[service])
    AvailabilityRuleFactory(provider=provider, weekday=3, start_time=time(9), end_time=time(18))
    return service, provider


def customer():
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.CUSTOMER))
    return client


@pytest.mark.django_db
@pytest.mark.usefixtures("frozen_now")
def test_booking_snapshots_buffer_and_customer_sees_plain_times(beard_and_cut):
    service, provider = beard_and_cut
    body = customer().post(BOOKINGS, booking_body(service, provider), format="json").json()
    assert body["end_at"] == "2026-10-01T04:30:00Z"  # customer's appointment ends at 09:30
    booking = Booking.objects.get(pk=body["id"])
    assert (booking.buffer_minutes, booking.blocked_until) == (10, tashkent(9, 40))

    service.buffer_after_minutes = 30
    service.save()
    booking.refresh_from_db()
    assert booking.blocked_until == tashkent(9, 40)  # later edits do not rewrite history


@pytest.mark.django_db
@pytest.mark.usefixtures("frozen_now")
def test_next_booking_respects_buffer(beard_and_cut):
    service, provider = beard_and_cut
    customer().post(BOOKINGS, booking_body(service, provider), format="json")
    listed = (
        APIClient()
        .get(
            "/api/v1/availability/slots",
            {"service": str(service.pk), "provider": str(provider.pk), "date": "2026-10-01"},
        )
        .json()["slots"]
    )
    assert [s["start_local"] for s in listed][:2] == ["09:45", "10:00"]

    at_0930 = booking_body(service, provider, "2026-10-01T09:30:00+05:00")
    assert_problem(customer().post(BOOKINGS, at_0930, format="json"), 409, "SLOT_TAKEN")
    at_0945 = booking_body(service, provider, "2026-10-01T09:45:00+05:00")
    assert customer().post(BOOKINGS, at_0945, format="json").status_code == 201


@pytest.mark.django_db
def test_admin_sets_buffer_via_api(admin_client, haircut):
    url = f"/api/v1/services/{haircut.pk}"
    assert_problem(
        admin_client.patch(url, {"buffer_after_minutes": 7}, format="json"),
        422,
        "VALIDATION_ERROR",
    )
    body = admin_client.patch(url, {"buffer_after_minutes": 10}, format="json").json()
    assert body["buffer_after_minutes"] == 10
    public = APIClient().get(url).json()
    assert "buffer_after_minutes" not in public  # internal detail, not shown to customers


# --- dashboard ----------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("frozen_now")
def test_day_view_draws_buffer(client, beard_and_cut):
    service, provider = beard_and_cut
    BookingFactory(provider=provider, service=service, start_at=tashkent(9), buffer_minutes=10)
    client.force_login(UserFactory(role=User.Role.ADMIN))
    html = client.get("/dashboard/?date=2026-10-01").content.decode()
    assert 'title="Tanaffus"' in html


@pytest.mark.django_db
def test_service_form_has_buffer_field(client):
    client.force_login(UserFactory(role=User.Role.ADMIN))
    html = client.get("/dashboard/services/?new=1").content.decode()
    assert 'name="buffer_after_minutes"' in html
