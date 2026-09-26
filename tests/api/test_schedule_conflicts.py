"""Edge #13 / #14: schedule changes never silently orphan an active booking (ADR-005)."""

from datetime import UTC, datetime, time

import pytest

from apps.bookings.models import Booking
from apps.scheduling.models import AvailabilityRule, TimeOff
from tests.api.test_auth import assert_problem
from tests.bookings_setup import frozen_now, haircut, sardor
from tests.factories import BookingFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

T_0900 = datetime(2026, 10, 1, 4, tzinfo=UTC)  # Thursday 09:00 Tashkent


@pytest.fixture
def booked(haircut, sardor):
    return BookingFactory(provider=sardor, service=haircut, start_at=T_0900)


def time_off_url(provider):
    return f"/api/v1/providers/{provider.pk}/time-off"


def availability_url(provider):
    return f"/api/v1/providers/{provider.pk}/availability"


def test_edge_13_time_off_over_active_booking_is_409(admin_client, sardor, booked):
    response = admin_client.post(
        time_off_url(sardor),
        {"start_at": "2026-10-01T08:00:00+05:00", "end_at": "2026-10-01T12:00:00+05:00"},
        format="json",
    )
    body = assert_problem(response, 409, "CONFLICTS_WITH_BOOKINGS")
    assert [b["id"] for b in body["bookings"]] == [str(booked.pk)]
    assert body["bookings"][0]["start_at"] == "2026-10-01T04:00:00Z"
    assert not TimeOff.objects.exists()
    booked.refresh_from_db()
    assert booked.status == "pending"  # never cancelled automatically


def test_time_off_touching_booking_is_allowed(admin_client, sardor, booked):
    # Booking is 09:00–09:30; time off from 09:30 does not overlap ([) ranges).
    response = admin_client.post(
        time_off_url(sardor),
        {"start_at": "2026-10-01T09:30:00+05:00", "end_at": "2026-10-01T12:00:00+05:00"},
        format="json",
    )
    assert response.status_code == 201, response.content


def test_time_off_over_cancelled_booking_is_allowed(admin_client, haircut, sardor):
    BookingFactory(
        provider=sardor, service=haircut, start_at=T_0900, status=Booking.Status.CANCELLED
    )
    response = admin_client.post(
        time_off_url(sardor),
        {"start_at": "2026-10-01T08:00:00+05:00", "end_at": "2026-10-01T12:00:00+05:00"},
        format="json",
    )
    assert response.status_code == 201


def test_edge_14_narrowing_rule_leaving_booking_outside_is_409(admin_client, sardor, booked):
    rules = [{"weekday": 3, "start_time": "10:00", "end_time": "18:00"}]
    body = assert_problem(
        admin_client.put(availability_url(sardor), {"rules": rules}, format="json"),
        409,
        "CONFLICTS_WITH_BOOKINGS",
    )
    assert [b["id"] for b in body["bookings"]] == [str(booked.pk)]
    # The old schedule is untouched.
    assert AvailabilityRule.objects.get(provider=sardor).start_time == time(9)


def test_removing_the_working_day_is_409(admin_client, sardor, booked):
    assert_problem(
        admin_client.put(availability_url(sardor), {"rules": []}, format="json"),
        409,
        "CONFLICTS_WITH_BOOKINGS",
    )


def test_narrowing_that_still_covers_booking_is_allowed(admin_client, sardor, booked):
    rules = [{"weekday": 3, "start_time": "09:00", "end_time": "12:00"}]
    response = admin_client.put(availability_url(sardor), {"rules": rules}, format="json")
    assert response.status_code == 200, response.content


def test_split_windows_do_not_count_as_covering_a_spanning_booking(admin_client, sardor, booked):
    # 09:00–09:15 and 09:15–18:00 together cover 09:00–09:30 once merged.
    rules = [
        {"weekday": 3, "start_time": "09:00", "end_time": "09:15"},
        {"weekday": 3, "start_time": "09:15", "end_time": "18:00"},
    ]
    assert (
        admin_client.put(availability_url(sardor), {"rules": rules}, format="json").status_code
        == 200
    )
    # A real gap does not.
    gap = [
        {"weekday": 3, "start_time": "09:00", "end_time": "09:15"},
        {"weekday": 3, "start_time": "09:20", "end_time": "18:00"},
    ]
    assert_problem(
        admin_client.put(availability_url(sardor), {"rules": gap}, format="json"),
        409,
        "CONFLICTS_WITH_BOOKINGS",
    )


def test_past_bookings_do_not_block_schedule_changes(admin_client, haircut, sardor):
    BookingFactory(provider=sardor, service=haircut, start_at=datetime(2026, 9, 24, 4, tzinfo=UTC))
    response = admin_client.put(availability_url(sardor), {"rules": []}, format="json")
    assert response.status_code == 200
