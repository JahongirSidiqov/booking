"""Bonus features: .ics export (API + web) and the device-timezone switch."""

from datetime import UTC, datetime

import pytest
from django.contrib.messages import get_messages
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.api.test_auth import assert_problem
from tests.bookings_setup import frozen_now, haircut, sardor
from tests.factories import BookingFactory, UserFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

T_0900 = datetime(2026, 10, 1, 4, tzinfo=UTC)


@pytest.fixture
def owner():
    return UserFactory(role=User.Role.CUSTOMER)


@pytest.fixture
def booking(owner, haircut, sardor):
    return BookingFactory(customer=owner, provider=sardor, service=haircut, start_at=T_0900)


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


# --- .ics -----------------------------------------------------------------------------------


def test_api_ical_for_owner(owner, booking):
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(f"/api/v1/bookings/{booking.pk}/ical")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar; charset=utf-8"
    assert response["Content-Disposition"] == 'attachment; filename="navbat-20261001-0400.ics"'
    body = response.content.decode()
    assert "DTSTART:20261001T040000Z" in body
    assert f"UID:booking-{booking.pk}@localhost" in body


@pytest.mark.parametrize("role", [User.Role.CUSTOMER, User.Role.ADMIN])
def test_api_ical_is_owner_only(booking, role):
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))
    assert_problem(client.get(f"/api/v1/bookings/{booking.pk}/ical"), 404, "NOT_FOUND")


def test_api_ical_requires_auth(booking):
    assert_problem(APIClient().get(f"/api/v1/bookings/{booking.pk}/ical"), 401, "AUTH_REQUIRED")


def test_web_ical_download_and_links(client, owner, booking):
    client.force_login(owner)
    response = client.get(f"/bookings/{booking.pk}/ical/")
    assert response.status_code == 200
    assert "BEGIN:VEVENT" in response.content.decode()
    detail = client.get(f"/bookings/{booking.pk}/").content.decode()
    assert f'href="/bookings/{booking.pk}/ical/"' in detail


def test_web_ical_hidden_for_cancelled_and_forbidden_for_others(
    client, owner, booking, haircut, sardor
):
    cancelled = BookingFactory(
        customer=owner,
        provider=sardor,
        service=haircut,
        start_at=T_0900.replace(hour=6),
        status="cancelled",
    )
    client.force_login(owner)
    assert "/ical/" not in client.get(f"/bookings/{cancelled.pk}/").content.decode()
    client.force_login(UserFactory())
    assert client.get(f"/bookings/{booking.pk}/ical/").status_code == 404


def test_schema_documents_ical(client):
    assert "/api/v1/bookings/{id}/ical" in client.get("/api/schema/").content.decode()


# --- timezone switch ------------------------------------------------------------------------


def test_anonymous_visitor_switches_to_device_zone(client, haircut, sardor):
    response = client.post("/timezone/", {"tz": "Asia/Dubai", "next": f"/book/{haircut.slug}/"})
    assert response["Location"] == f"/book/{haircut.slug}/"
    assert messages_of(response) == ["Vaqtlar endi Asia/Dubai zonasida koʻrsatiladi."]
    html = client.get(
        f"/book/{haircut.slug}/?provider={sardor.pk}&date=2026-10-01"
    ).content.decode()
    assert 'data-label="08:00"' in html  # 09:00 Tashkent shown in Dubai time
    assert "Vaqt zonasi: Asia/Dubai" in html


def test_logged_in_user_switch_updates_profile(client):
    user = UserFactory(timezone="Asia/Tashkent")
    client.force_login(user)
    client.post("/timezone/", {"tz": "Europe/Berlin"})
    user.refresh_from_db()
    assert user.timezone == "Europe/Berlin"


def test_invalid_zone_is_refused(client):
    response = client.post("/timezone/", {"tz": "Mars/Olympus"})
    assert "aniqlanmadi" in messages_of(response)[0]
    assert "Vaqt zonasi: Asia/Tashkent" in client.get("/").content.decode()


def test_tampered_session_zone_falls_back_to_business(client):
    session = client.session
    session["display_tz"] = "Not/AZone"
    session.save()
    assert "Vaqt zonasi: Asia/Tashkent" in client.get("/").content.decode()


def test_switch_refuses_foreign_next_and_get(client):
    response = client.post("/timezone/", {"tz": "Asia/Dubai", "next": "https://evil.example/"})
    assert response["Location"] == "/"
    assert client.get("/timezone/").status_code == 405


def test_banner_form_is_rendered(client):
    html = client.get("/").content.decode()
    assert 'action="/timezone/"' in html
    assert ':value="browser"' in html
