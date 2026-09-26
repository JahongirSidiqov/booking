import uuid
from datetime import UTC, datetime, time
from decimal import Decimal

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.scheduling.models import BusinessSettings, TimeOff
from tests.api.test_auth import assert_problem
from tests.bookings_setup import BOOKINGS, SLOT_0900, booking_body, frozen_now, haircut, sardor
from tests.factories import (
    AvailabilityRuleFactory,
    BookingFactory,
    ProviderFactory,
    ServiceFactory,
    UserFactory,
)

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]


def book(client, service, provider, start_at=SLOT_0900, key=None, **extra):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client.post(
        BOOKINGS, booking_body(service, provider, start_at, **extra), format="json", **headers
    )


def new_customer():
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.CUSTOMER))
    return client


# --- happy path ---------------------------------------------------------------------------


def test_create_booking_matches_documented_shape(customer_client, haircut, sardor):
    response = book(customer_client, haircut, sardor, note="Qisqaroq")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "pending"
    assert body["service"] == {"id": str(haircut.pk), "name": "Soch olish"}
    assert body["provider"] == {"id": str(sardor.pk), "name": "Sardor"}
    assert body["start_at"] == "2026-10-01T04:00:00Z"
    assert body["end_at"] == "2026-10-01T04:30:00Z"
    assert body["start_at_local"] == "2026-10-01T09:00:00+05:00"
    assert body["price"] == "60000.00"
    assert body["currency"] == "UZS"
    assert body["customer_note"] == "Qisqaroq"
    assert body["can_cancel_until"] == "2026-09-30T04:00:00Z"
    assert [(h["from"], h["to"], h["by"]) for h in body["history"]] == [
        (None, "pending", "customer")
    ]
    booking = Booking.objects.get(pk=body["id"])
    assert booking.customer == customer_client.user
    assert (booking.service_name, booking.duration_minutes, booking.price) == (
        "Soch olish",
        30,
        Decimal("60000.00"),
    )


def test_edge_17_customer_offset_lands_on_same_instant(customer_client, haircut, sardor):
    customer_client.user.timezone = "Asia/Dubai"
    customer_client.user.save()
    body = book(customer_client, haircut, sardor, start_at="2026-10-01T08:00:00+04:00").json()
    assert body["start_at"] == "2026-10-01T04:00:00Z"
    assert body["start_at_local"] == "2026-10-01T08:00:00+04:00"


def test_booking_removes_slot_from_listing(customer_client, haircut, sardor):
    book(customer_client, haircut, sardor)
    slots = (
        APIClient()
        .get(
            "/api/v1/availability/slots",
            {"service": str(haircut.pk), "provider": str(sardor.pk), "date": "2026-10-01"},
        )
        .json()["slots"]
    )
    starts = [s["start_local"] for s in slots]
    assert "09:00" not in starts
    assert "08:45" not in starts
    assert starts[0] == "09:30"


def test_edge_36_auto_confirm_creates_two_history_rows(customer_client, haircut, sardor):
    settings = BusinessSettings.load()
    settings.auto_confirm = True
    settings.save()
    body = book(customer_client, haircut, sardor).json()
    assert body["status"] == "confirmed"
    assert [(h["from"], h["to"], h["by"]) for h in body["history"]] == [
        (None, "pending", "customer"),
        ("pending", "confirmed", "system"),
    ]


def test_edge_32_script_in_note_is_stored_verbatim(customer_client, haircut, sardor):
    note = "<script>alert(1)</script>"
    body = book(customer_client, haircut, sardor, note=note).json()
    assert body["customer_note"] == note


# --- idempotency --------------------------------------------------------------------------


def test_edge_02_double_click_with_same_key_creates_one_booking(customer_client, haircut, sardor):
    first = book(customer_client, haircut, sardor, key="a1b2c3")
    second = book(customer_client, haircut, sardor, key="a1b2c3")
    assert first.status_code == 201
    assert second.status_code == 200
    assert second["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert Booking.objects.count() == 1


def test_edge_03_same_key_different_payload_is_409(customer_client, haircut, sardor):
    book(customer_client, haircut, sardor, key="k-1")
    response = book(customer_client, haircut, sardor, "2026-10-01T10:00:00+05:00", key="k-1")
    assert_problem(response, 409, "IDEMPOTENCY_MISMATCH")
    assert Booking.objects.count() == 1


def test_same_key_is_scoped_per_customer(haircut, sardor):
    assert book(new_customer(), haircut, sardor, key="shared").status_code == 201
    other = book(new_customer(), haircut, sardor, "2026-10-01T10:00:00+05:00", key="shared")
    assert other.status_code == 201


@pytest.mark.parametrize("key", ["has space", "x" * 65, "kalit/1"])
def test_malformed_idempotency_key_is_422(customer_client, haircut, sardor, key):
    body = assert_problem(book(customer_client, haircut, sardor, key=key), 422, "VALIDATION_ERROR")
    assert "Idempotency-Key" in body["errors"]


# --- time rules (edge #4–#8) --------------------------------------------------------------


def test_edge_04_past_slot(customer_client, haircut, sardor):
    assert_problem(
        book(customer_client, haircut, sardor, "2026-09-24T09:00:00+05:00"), 422, "IN_PAST"
    )


def test_edge_05_inside_lead_time(customer_client, haircut, sardor):
    with freeze_time("2026-10-01 04:10:00"):  # 09:10 local, lead 60 min
        response = book(customer_client, haircut, sardor, "2026-10-01T09:45:00+05:00")
    assert_problem(response, 422, "LEAD_TIME")


def test_edge_06_beyond_max_advance(customer_client, haircut, sardor):
    assert_problem(
        book(customer_client, haircut, sardor, "2026-10-29T09:00:00+05:00"),
        422,
        "TOO_FAR_AHEAD",
    )


def test_edge_07_service_does_not_fit_before_closing(customer_client, haircut, sardor):
    assert_problem(
        book(customer_client, haircut, sardor, "2026-10-01T17:45:00+05:00"),
        422,
        "SLOT_UNAVAILABLE",
    )


def test_edge_08_step_misaligned(customer_client, haircut, sardor):
    assert_problem(
        book(customer_client, haircut, sardor, "2026-10-01T10:07:00+05:00"),
        422,
        "STEP_MISALIGNED",
    )


def test_outside_working_day_is_unavailable(customer_client, haircut, sardor):
    assert_problem(
        book(customer_client, haircut, sardor, "2026-10-02T09:00:00+05:00"),
        422,
        "SLOT_UNAVAILABLE",
    )


def test_time_off_makes_slot_unavailable(customer_client, haircut, sardor):
    TimeOff.objects.create(
        provider=sardor,
        start_at=datetime(2026, 10, 1, 4, tzinfo=UTC),
        end_at=datetime(2026, 10, 1, 6, tzinfo=UTC),
    )
    assert_problem(book(customer_client, haircut, sardor), 422, "SLOT_UNAVAILABLE")


def test_naive_start_at_rejected(customer_client, haircut, sardor):
    body = assert_problem(
        book(customer_client, haircut, sardor, "2026-10-01T09:00:00"), 422, "VALIDATION_ERROR"
    )
    assert "start_at" in body["errors"]


# --- resources (edge #9–#12) --------------------------------------------------------------


def test_edge_09_provider_not_offering_service(customer_client, sardor):
    other = ServiceFactory()
    assert_problem(book(customer_client, other, sardor), 422, "PROVIDER_NOT_OFFERING_SERVICE")


@pytest.mark.parametrize("target", ["service", "provider"])
def test_edge_10_inactive_resource(customer_client, haircut, sardor, target):
    obj = haircut if target == "service" else sardor
    obj.is_active = False
    obj.save()
    assert_problem(book(customer_client, haircut, sardor), 422, "INACTIVE_RESOURCE")


def test_unknown_provider_or_service_is_404(customer_client, haircut, sardor):
    ghost = type("Ghost", (), {"pk": uuid.uuid4()})()
    assert_problem(book(customer_client, haircut, ghost), 404, "NOT_FOUND")
    assert_problem(book(customer_client, ghost, sardor), 404, "NOT_FOUND")


def test_edge_11_12_service_changes_do_not_rewrite_booking(customer_client, haircut, sardor):
    booking_id = book(customer_client, haircut, sardor).json()["id"]
    haircut.duration_minutes = 60
    haircut.price = Decimal("90000.00")
    haircut.name = "Soch olish (premium)"
    haircut.save()

    booking = Booking.objects.get(pk=booking_id)
    assert (booking.duration_minutes, booking.price, booking.service_name) == (
        30,
        Decimal("60000.00"),
        "Soch olish",
    )
    assert booking.end_at == datetime(2026, 10, 1, 4, 30, tzinfo=UTC)
    # New bookings use the new duration: 09:30–10:30 now.
    second = book(new_customer(), haircut, sardor, "2026-10-01T09:30:00+05:00").json()
    assert second["end_at"] == "2026-10-01T05:30:00Z"
    assert second["price"] == "90000.00"


# --- conflicts ----------------------------------------------------------------------------


def test_slot_taken_by_another_customer(haircut, sardor):
    assert book(new_customer(), haircut, sardor).status_code == 201
    assert_problem(book(new_customer(), haircut, sardor), 409, "SLOT_TAKEN")


def test_partial_overlap_is_taken(haircut, sardor):
    book(new_customer(), haircut, sardor)
    assert_problem(
        book(new_customer(), haircut, sardor, "2026-10-01T09:15:00+05:00"), 409, "SLOT_TAKEN"
    )


def test_adjacent_slot_is_free_half_open_range(haircut, sardor):
    book(new_customer(), haircut, sardor)
    response = book(new_customer(), haircut, sardor, "2026-10-01T09:30:00+05:00")
    assert response.status_code == 201


def test_cancelled_booking_does_not_block(customer_client, haircut, sardor):
    BookingFactory(
        provider=sardor,
        service=haircut,
        start_at=datetime(2026, 10, 1, 4, tzinfo=UTC),
        status=Booking.Status.CANCELLED,
    )
    assert book(customer_client, haircut, sardor).status_code == 201


def test_edge_24_customer_overlap_with_other_provider(customer_client, haircut, sardor):
    jasur = ProviderFactory(name="Jasur", with_services=[haircut])
    AvailabilityRuleFactory(provider=jasur, weekday=3, start_time=time(9), end_time=time(18))
    assert book(customer_client, haircut, sardor).status_code == 201
    assert_problem(
        book(customer_client, haircut, jasur, "2026-10-01T09:15:00+05:00"),
        409,
        "CUSTOMER_OVERLAP",
    )


# --- permissions / throttling -------------------------------------------------------------


@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.PROVIDER])
def test_only_customers_can_book(haircut, sardor, role):
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))
    assert_problem(book(client, haircut, sardor), 403, "FORBIDDEN")


def test_anon_cannot_book(haircut, sardor):
    assert_problem(book(APIClient(), haircut, sardor), 401, "AUTH_REQUIRED")


def test_edge_31_booking_attempts_are_throttled(customer_client, haircut, sardor):
    for _ in range(10):
        book(customer_client, haircut, sardor, "2026-10-01T10:07:00+05:00")
    response = book(customer_client, haircut, sardor)
    assert_problem(response, 429, "THROTTLED")
    assert not Booking.objects.exists()


# --- deactivation keeps bookings (edge #25) -----------------------------------------------


def test_edge_25_deactivating_provider_lists_upcoming_bookings(admin_client, haircut, sardor):
    booking_id = book(new_customer(), haircut, sardor).json()["id"]
    response = admin_client.delete(f"/api/v1/providers/{sardor.pk}")
    assert response.status_code == 200
    body = response.json()
    assert body["upcoming_bookings_count"] == 1
    assert body["upcoming_bookings"][0]["id"] == booking_id
    assert Booking.objects.get(pk=booking_id).status == "pending"
    assert_problem(
        book(new_customer(), haircut, sardor, "2026-10-01T11:00:00+05:00"),
        422,
        "INACTIVE_RESOURCE",
    )


def test_edge_12_price_change_keeps_old_price_on_booking(customer_client, haircut, sardor):
    booking_id = book(customer_client, haircut, sardor).json()["id"]
    haircut.price = Decimal("75000.00")
    haircut.save()
    body = customer_client.get(f"{BOOKINGS}/{booking_id}").json()
    assert body["price"] == "60000.00"
