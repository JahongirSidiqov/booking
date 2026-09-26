from datetime import UTC, datetime

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings.models import Booking
from tests.api.test_auth import assert_problem
from tests.bookings_setup import BOOKINGS, SLOT_0900, booking_body, frozen_now, haircut, sardor
from tests.factories import BookingFactory, ProviderFactory, UserFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

START = datetime(2026, 10, 1, 4, tzinfo=UTC)  # 09:00 Tashkent


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    client.user = user
    return client


@pytest.fixture
def staff(sardor):
    user = UserFactory(role=User.Role.PROVIDER)
    sardor.user = user
    sardor.save()
    return client_for(user)


@pytest.fixture
def owner():
    return client_for(UserFactory(role=User.Role.CUSTOMER))


@pytest.fixture
def admin():
    return client_for(UserFactory(role=User.Role.ADMIN))


@pytest.fixture
def booking(owner, haircut, sardor):
    response = owner.post(BOOKINGS, booking_body(haircut, sardor), format="json")
    assert response.status_code == 201, response.content
    return Booking.objects.get(pk=response.json()["id"])


def act(client, booking, action, reason=None):
    body = {} if reason is None else {"reason": reason}
    return client.post(f"{BOOKINGS}/{booking.pk}/{action}", body, format="json")


def history(response):
    return [(h["from"], h["to"], h["by"]) for h in response.json()["history"]]


# --- confirm ------------------------------------------------------------------------------


def test_own_provider_confirms(staff, booking):
    response = act(staff, booking, "confirm")
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "confirmed"
    assert history(response)[-1] == ("pending", "confirmed", "provider")


def test_admin_confirms(admin, booking):
    assert act(admin, booking, "confirm").json()["status"] == "confirmed"


def test_customer_cannot_confirm_own_booking(owner, booking):
    assert_problem(act(owner, booking, "confirm"), 403, "FORBIDDEN")


def test_other_provider_gets_404(booking):
    stranger = UserFactory(role=User.Role.PROVIDER)
    ProviderFactory(user=stranger)
    assert_problem(act(client_for(stranger), booking, "confirm"), 404, "NOT_FOUND")


def test_edge_35_unlinked_provider_user_sees_nothing(booking):
    unlinked = client_for(UserFactory(role=User.Role.PROVIDER))
    assert_problem(act(unlinked, booking, "confirm"), 404, "NOT_FOUND")
    assert unlinked.get(BOOKINGS).json()["results"] == []


def test_edge_22_confirm_after_start_is_409(staff, booking):
    with freeze_time("2026-10-01 04:05:00"):
        assert_problem(act(staff, booking, "confirm"), 409, "INVALID_TRANSITION")


# --- cancel -------------------------------------------------------------------------------


def test_customer_cancels_before_deadline(owner, booking):
    response = act(owner, booking, "cancel", "Rejalar oʻzgardi")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancel_reason"] == "Rejalar oʻzgardi"
    assert body["cancelled_at"] == "2026-09-26T12:00:00Z"
    booking.refresh_from_db()
    assert booking.cancelled_by == owner.user


def test_customer_cancel_without_reason_is_fine(owner, booking):
    assert act(owner, booking, "cancel").status_code == 200


def test_edge_19_customer_cancel_after_deadline(owner, booking):
    with freeze_time("2026-09-30 04:00:01"):  # 24h before start + 1s
        assert_problem(act(owner, booking, "cancel"), 422, "CANCELLATION_DEADLINE_PASSED")


def test_provider_cancels_late_with_reason(staff, booking):
    with freeze_time("2026-10-01 03:30:00"):
        assert_problem(act(staff, booking, "cancel"), 422, "VALIDATION_ERROR")
        response = act(staff, booking, "cancel", "Xodim kasal")
    assert response.status_code == 200
    assert history(response)[-1] == ("pending", "cancelled", "provider")


def test_cancel_frees_the_slot(owner, booking, haircut, sardor):
    act(owner, booking, "cancel")
    other = client_for(UserFactory(role=User.Role.CUSTOMER))
    response = other.post(BOOKINGS, booking_body(haircut, sardor, SLOT_0900), format="json")
    assert response.status_code == 201


def test_edge_26_other_customer_gets_404(booking):
    stranger = client_for(UserFactory(role=User.Role.CUSTOMER))
    assert_problem(act(stranger, booking, "cancel"), 404, "NOT_FOUND")
    assert_problem(stranger.get(f"{BOOKINGS}/{booking.pk}"), 404, "NOT_FOUND")


def test_reason_too_long_is_422(owner, booking):
    assert_problem(act(owner, booking, "cancel", "x" * 501), 422, "VALIDATION_ERROR")


# --- complete / terminal ------------------------------------------------------------------


def test_complete_after_start(staff, booking):
    act(staff, booking, "confirm")
    with freeze_time("2026-10-01 04:30:00"):
        response = act(staff, booking, "complete")
    assert response.status_code == 200
    assert history(response) == [
        (None, "pending", "customer"),
        ("pending", "confirmed", "provider"),
        ("confirmed", "completed", "provider"),
    ]


def test_edge_21_complete_before_start_is_409(staff, booking):
    act(staff, booking, "confirm")
    assert_problem(act(staff, booking, "complete"), 409, "INVALID_TRANSITION")


def test_complete_pending_is_409(staff, booking):
    with freeze_time("2026-10-01 04:30:00"):
        assert_problem(act(staff, booking, "complete"), 409, "INVALID_TRANSITION")


@pytest.mark.parametrize("action", ["confirm", "cancel", "complete"])
def test_edge_20_cancelled_booking_is_terminal(admin, owner, booking, action):
    act(owner, booking, "cancel")
    body = assert_problem(act(admin, booking, action, "sabab"), 409, "INVALID_TRANSITION")
    assert body["from"] == "cancelled"


def test_anon_is_401(booking):
    assert_problem(act(APIClient(), booking, "cancel"), 401, "AUTH_REQUIRED")


def test_malformed_id_is_404(admin):
    assert_problem(admin.post(f"{BOOKINGS}/xyz/confirm", {}, format="json"), 404, "NOT_FOUND")


# --- list / detail visibility -------------------------------------------------------------


def test_list_is_scoped_by_role(owner, staff, admin, booking, haircut):
    elsewhere = BookingFactory(service=haircut, start_at=START)  # other customer, provider
    ids = lambda c: {b["id"] for b in c.get(BOOKINGS).json()["results"]}  # noqa: E731
    assert ids(owner) == {str(booking.pk)}
    assert ids(staff) == {str(booking.pk)}
    assert ids(admin) == {str(booking.pk), str(elsewhere.pk)}


def test_detail_includes_history_and_customer(staff, booking):
    body = staff.get(f"{BOOKINGS}/{booking.pk}").json()
    assert body["customer"]["id"] == str(booking.customer_id)
    assert history_of(body) == [(None, "pending", "customer")]


def history_of(body):
    return [(h["from"], h["to"], h["by"]) for h in body["history"]]
