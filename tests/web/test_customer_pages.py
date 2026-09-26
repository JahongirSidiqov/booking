from datetime import UTC, datetime

import pytest
from django.contrib.messages import get_messages
from freezegun import freeze_time

from apps.accounts.models import User
from apps.bookings.models import Booking
from tests.bookings_setup import frozen_now, haircut, sardor
from tests.factories import DEFAULT_PASSWORD, BookingFactory, UserFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

T_0900 = datetime(2026, 10, 1, 4, tzinfo=UTC)


@pytest.fixture
def customer_web(client):
    user = UserFactory(role=User.Role.CUSTOMER)
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def my_booking(customer_web, haircut, sardor):
    return BookingFactory(
        customer=customer_web.user, provider=sardor, service=haircut, start_at=T_0900
    )


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


# --- my bookings ----------------------------------------------------------------------------


def test_bookings_requires_login(client):
    response = client.get("/bookings/")
    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_upcoming_tab(customer_web, my_booking):
    html = customer_web.get("/bookings/").content.decode()
    assert "Soch olish" in html
    assert "Kutilmoqda" in html
    assert f"/bookings/{my_booking.pk}/" in html


def test_tabs_split_bookings(customer_web, haircut, sardor):
    user = customer_web.user
    BookingFactory(
        customer=user,
        service=haircut,
        start_at=datetime(2026, 9, 20, 4, tzinfo=UTC),
        status="completed",
    )
    BookingFactory(
        customer=user,
        service=haircut,
        start_at=datetime(2026, 9, 21, 4, tzinfo=UTC),
        status="cancelled",
    )
    past = customer_web.get("/bookings/?tab=past").content.decode()
    cancelled = customer_web.get("/bookings/?tab=cancelled").content.decode()
    upcoming = customer_web.get("/bookings/").content.decode()
    assert "Bajarilgan" in past and "Bekor qilingan</span>" not in past
    assert "Bekor qilingan</span>" in cancelled
    assert "Kelgusi bronlaringiz yoʻq" in upcoming


def test_other_customers_bookings_are_invisible(customer_web, haircut, sardor):
    foreign = BookingFactory(service=haircut, provider=sardor, start_at=T_0900)
    assert "Soch olish" not in customer_web.get("/bookings/").content.decode()
    assert customer_web.get(f"/bookings/{foreign.pk}/").status_code == 404


# --- detail and cancel ----------------------------------------------------------------------


def test_detail_shows_timeline_and_cancel_button(customer_web, my_booking):
    my_booking.history.create(to_status="pending", changed_by=customer_web.user)
    html = customer_web.get(f"/bookings/{my_booking.pk}/").content.decode()
    assert "Holat tarixi" in html
    assert "Mijoz" in html
    assert 'id="cancel-dialog"' in html


def test_customer_cancels_booking(customer_web, my_booking):
    response = customer_web.post(f"/bookings/{my_booking.pk}/cancel/", {"reason": "Kasal boʻldim"})
    my_booking.refresh_from_db()
    assert my_booking.status == Booking.Status.CANCELLED
    assert my_booking.cancel_reason == "Kasal boʻldim"
    assert messages_of(response) == ["Bron bekor qilindi."]
    html = customer_web.get(f"/bookings/{my_booking.pk}/").content.decode()
    assert 'id="cancel-dialog"' not in html


def test_edge_19_after_deadline_no_cancel_button_and_friendly_error(customer_web, my_booking):
    with freeze_time("2026-09-30 10:00:00"):  # 18h before start, deadline is 24h
        html = customer_web.get(f"/bookings/{my_booking.pk}/").content.decode()
        response = customer_web.post(f"/bookings/{my_booking.pk}/cancel/", {})
    assert 'id="cancel-dialog"' not in html
    assert "Bekor qilish muddati oʻtgan" in html
    assert "24 soat oldin" in messages_of(response)[0]
    my_booking.refresh_from_db()
    assert my_booking.status == Booking.Status.PENDING


def test_cannot_cancel_someone_elses_booking(customer_web, haircut, sardor):
    foreign = BookingFactory(service=haircut, provider=sardor, start_at=T_0900)
    assert customer_web.post(f"/bookings/{foreign.pk}/cancel/", {}).status_code == 404
    foreign.refresh_from_db()
    assert foreign.status == Booking.Status.PENDING


def test_edge_32_note_with_script_is_escaped(customer_web, haircut, sardor):
    booking = BookingFactory(
        customer=customer_web.user,
        service=haircut,
        provider=sardor,
        start_at=T_0900,
        customer_note="<script>alert(1)</script>",
    )
    html = customer_web.get(f"/bookings/{booking.pk}/").content.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --- auth and profile -----------------------------------------------------------------------


def test_register_logs_in_and_returns_to_next(client):
    response = client.post(
        "/register/",
        {
            "full_name": "Yangi Mijoz",
            "email": "Yangi@Example.com",
            "password": "Kuchli-Parol-77",
            "next": "/bookings/",
        },
    )
    assert response.status_code == 302
    assert response["Location"] == "/bookings/"
    user = User.objects.get(email="yangi@example.com")
    assert user.role == User.Role.CUSTOMER
    assert client.get("/bookings/").status_code == 200


def test_register_rejects_foreign_next_url(client):
    response = client.post(
        "/register/",
        {
            "full_name": "A B",
            "email": "a@example.com",
            "password": "Kuchli-Parol-77",
            "next": "https://evil.example/",
        },
    )
    assert response["Location"] == "/"


def test_register_shows_field_errors(client):
    UserFactory(email="band@example.com")
    html = client.post(
        "/register/", {"full_name": "A", "email": "band@example.com", "password": "123"}
    ).content.decode()
    assert "Bu email bilan akkaunt allaqachon mavjud." in html
    assert 'aria-invalid="true"' in html


def test_login_and_logout(client):
    user = UserFactory()
    response = client.post(
        "/login/", {"username": user.email.upper(), "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 302
    assert client.get("/profile/").status_code == 200
    client.post("/logout/")
    assert client.get("/profile/").status_code == 302


def test_login_error_message(client):
    html = client.post(
        "/login/", {"username": "x@example.com", "password": "yomon"}
    ).content.decode()
    assert "Email yoki parol notoʻgʻri." in html


def test_profile_update_changes_display_timezone(customer_web):
    response = customer_web.post(
        "/profile/", {"full_name": "Yangi Ism", "phone": "", "timezone": "Asia/Dubai"}
    )
    assert response.status_code == 302
    customer_web.user.refresh_from_db()
    assert customer_web.user.timezone == "Asia/Dubai"
    assert "Vaqt zonasi: Asia/Dubai" in customer_web.get("/").content.decode()


def test_profile_rejects_bad_phone(customer_web):
    html = customer_web.post(
        "/profile/", {"full_name": "A", "phone": "901234567", "timezone": "Asia/Tashkent"}
    ).content.decode()
    assert "+998XXXXXXXXX" in html


# --- page shell -----------------------------------------------------------------------------


def test_page_shell_accessibility_basics(client):
    html = client.get("/").content.decode()
    assert '<html lang="uz">' in html
    assert 'href="#main"' in html and 'id="main"' in html
    assert 'aria-live="polite"' in html


def test_html_404_page_uses_design(client):
    response = client.get("/yoq-sahifa/")
    assert response.status_code == 404
    assert "Sahifa topilmadi" in response.content.decode()


def test_api_is_not_affected_by_display_timezone(client, customer_web, my_booking):
    customer_web.user.timezone = "Asia/Dubai"
    customer_web.user.save()
    body = customer_web.get(f"/api/v1/bookings/{my_booking.pk}").json()
    assert body["start_at"] == "2026-10-01T04:00:00Z"
