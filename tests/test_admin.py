import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser_client(client):
    user = User.objects.create_superuser(email="root@example.com", password="x", full_name="Root")
    client.force_login(user)
    return client


def test_admin_user_pages_render(superuser_client):
    user = User.objects.create_user(email="c@example.com", password="x", full_name="C")
    assert superuser_client.get("/django-admin/accounts/user/").status_code == 200
    assert superuser_client.get("/django-admin/accounts/user/add/").status_code == 200
    assert superuser_client.get(f"/django-admin/accounts/user/{user.pk}/change/").status_code == 200


def test_admin_creates_user_with_lowercase_email(superuser_client):
    response = superuser_client.post(
        "/django-admin/accounts/user/add/",
        {
            "email": "Yangi.Xodim@Example.com",
            "full_name": "Yangi Xodim",
            "role": "provider",
            "password1": "Kuchli-Parol-77",
            "password2": "Kuchli-Parol-77",
        },
    )
    assert response.status_code == 302, response.content
    user = User.objects.get(email="yangi.xodim@example.com")
    assert user.role == User.Role.PROVIDER
    assert user.check_password("Kuchli-Parol-77")


def test_booking_admin_is_read_only(superuser_client):
    from apps.bookings.models import BookingStatusHistory
    from tests.factories import BookingFactory

    booking = BookingFactory()
    BookingStatusHistory.objects.create(booking=booking, to_status="pending")
    assert superuser_client.get("/django-admin/bookings/booking/").status_code == 200
    page = superuser_client.get(f"/django-admin/bookings/booking/{booking.pk}/change/")
    assert page.status_code == 200
    assert b"None \xe2\x86\x92 pending" in page.content
    assert superuser_client.get("/django-admin/bookings/booking/add/").status_code == 403
    response = superuser_client.post(
        f"/django-admin/bookings/booking/{booking.pk}/change/", {"status": "cancelled"}
    )
    assert response.status_code == 403
    booking.refresh_from_db()
    assert booking.status == "pending"
