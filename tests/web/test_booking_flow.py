"""The customer booking flow through real HTML pages (Django test client)."""

import re
from datetime import UTC, datetime, time
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.messages import get_messages

from apps.accounts.models import User
from apps.bookings.models import Booking
from tests.bookings_setup import frozen_now, haircut, sardor
from tests.factories import AvailabilityRuleFactory, BookingFactory, ProviderFactory, UserFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

THURSDAY = "2026-10-01"
SLOT_0900_Z = "2026-10-01T04:00:00Z"


def book_url(service, **params):
    base = f"/book/{service.slug}/"
    if not params:
        return base
    return base + "?" + "&".join(f"{k}={v}" for k, v in params.items())


@pytest.fixture
def customer_web(client):
    user = UserFactory(role=User.Role.CUSTOMER)
    client.force_login(user)
    client.user = user
    return client


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


def idempotency_key(html: str) -> str:
    return re.search(r'name="idempotency_key" value="([^"]+)"', html).group(1)


# --- step 1: provider -----------------------------------------------------------------------


def test_home_lists_active_services(client, haircut):
    haircut.description = "Klassik soch olish"
    haircut.save()
    html = client.get("/").content.decode()
    assert "Soch olish" in html
    assert "60 000 soʻm" in html
    assert "30 daq" in html
    assert f'href="/book/{haircut.slug}/"' in html


def test_home_empty_state(client):
    assert "Hozircha xizmatlar yoʻq" in client.get("/").content.decode()


def test_step_1_lists_providers_offering_the_service(client, haircut, sardor):
    ProviderFactory(name="Boshqa xizmatdagi xodim")
    html = client.get(book_url(haircut)).content.decode()
    assert "Sardor" in html
    assert "Boshqa xizmatdagi xodim" not in html
    assert 'aria-current="step"' in html


def test_unknown_or_inactive_service_is_404(client, haircut):
    assert client.get("/book/yoq-xizmat/").status_code == 404
    haircut.is_active = False
    haircut.save()
    assert client.get(book_url(haircut)).status_code == 404


def test_unknown_provider_falls_back_to_step_1(client, haircut, sardor):
    html = client.get(book_url(haircut, provider="not-a-uuid")).content.decode()
    assert "Xodimni tanlang" in html


# --- step 2: date and time ------------------------------------------------------------------


def test_step_2_shows_strip_and_grouped_chips(client, haircut, sardor):
    html = client.get(book_url(haircut, provider=sardor.pk, date=THURSDAY)).content.decode()
    assert "<html" in html
    assert "Pa, 1-okt" in html
    assert "35 boʻsh" in html  # Thursday has 35 half-hour starts from 09:00 to 17:30
    assert f'value="{SLOT_0900_Z}"' in html
    assert "Ertalab" in html and "Kunduzi" in html and "Kechqurun" in html


def test_step_2_defaults_to_first_day_with_slots(client, haircut, sardor):
    html = client.get(book_url(haircut, provider=sardor.pk)).content.decode()
    assert 'aria-current="date"' in html
    assert f'value="{SLOT_0900_Z}"' in html


def test_htmx_request_returns_only_the_picker(client, haircut, sardor):
    response = client.get(
        book_url(haircut, provider=sardor.pk, date=THURSDAY), HTTP_HX_REQUEST="true"
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert "<html" not in html
    assert html.lstrip().startswith('<div id="time-picker"')


def test_empty_day_points_to_next_free_day(client, haircut, sardor):
    html = client.get(book_url(haircut, provider=sardor.pk, date="2026-10-02")).content.decode()
    assert "Bu kunda boʻsh vaqt yoʻq" in html
    assert "Keyingi boʻsh kun: Pa, 8-okt" in html


def test_chips_are_rendered_in_viewer_timezone(client, haircut, sardor):
    viewer = UserFactory(timezone="Asia/Dubai")
    client.force_login(viewer)
    html = client.get(book_url(haircut, provider=sardor.pk, date=THURSDAY)).content.decode()
    assert 'data-label="08:00"' in html  # 09:00 Tashkent is 08:00 in Dubai


# --- step 3 and 4: confirm and result -------------------------------------------------------


def test_step_3_requires_login(client, haircut, sardor):
    url = book_url(haircut, provider=sardor.pk, start=SLOT_0900_Z)
    response = client.get(url)
    assert response.status_code == 302
    target = urlparse(response["Location"])
    assert target.path == "/login/"
    assert parse_qs(target.query)["next"] == [url]


def test_full_flow_creates_booking(customer_web, haircut, sardor):
    page = customer_web.get(book_url(haircut, provider=sardor.pk, start=SLOT_0900_Z))
    html = page.content.decode()
    assert "Bronni tasdiqlash" in html
    assert "1-oktabr, payshanba" in html
    assert "09:00–09:30" in html

    response = customer_web.post(
        f"/book/{haircut.slug}/confirm/",
        {
            "provider": sardor.pk,
            "start_at": SLOT_0900_Z,
            "idempotency_key": idempotency_key(html),
            "note": "Qisqaroq",
        },
    )
    booking = Booking.objects.get()
    assert response.status_code == 302
    assert response["Location"] == f"/book/{haircut.slug}/done/{booking.pk}/"
    assert booking.customer == customer_web.user
    assert booking.customer_note == "Qisqaroq"

    done = customer_web.get(response["Location"]).content.decode()
    assert "Bron qabul qilindi — tasdiqlashni kuting" in done
    assert "Kutilmoqda" in done


def test_double_submit_creates_one_booking(customer_web, haircut, sardor):
    html = customer_web.get(book_url(haircut, provider=sardor.pk, start=SLOT_0900_Z)).content
    data = {
        "provider": sardor.pk,
        "start_at": SLOT_0900_Z,
        "idempotency_key": idempotency_key(html.decode()),
    }
    first = customer_web.post(f"/book/{haircut.slug}/confirm/", data)
    second = customer_web.post(f"/book/{haircut.slug}/confirm/", data)
    assert first["Location"] == second["Location"]
    assert Booking.objects.count() == 1


def test_slot_taken_between_steps_returns_to_picker(customer_web, haircut, sardor):
    html = customer_web.get(book_url(haircut, provider=sardor.pk, start=SLOT_0900_Z)).content
    # Someone else books 09:00 while this customer is on the confirm page.
    BookingFactory(provider=sardor, service=haircut, start_at=datetime(2026, 10, 1, 4, tzinfo=UTC))

    response = customer_web.post(
        f"/book/{haircut.slug}/confirm/",
        {
            "provider": sardor.pk,
            "start_at": SLOT_0900_Z,
            "idempotency_key": idempotency_key(html.decode()),
        },
    )
    assert response.status_code == 302
    assert f"provider={sardor.pk}" in response["Location"]
    assert f"date={THURSDAY}" in response["Location"]
    assert messages_of(response) == ["Bu vaqt hozirgina band qilindi. Boshqa vaqtni tanlang."]
    assert Booking.objects.filter(customer=customer_web.user).count() == 0

    picker = customer_web.get(response["Location"]).content.decode()
    assert f'value="{SLOT_0900_Z}"' not in picker  # reloaded slots, selection gone
    assert "checked" not in picker


def test_stale_slot_on_confirm_page_redirects_back(customer_web, haircut, sardor):
    BookingFactory(provider=sardor, service=haircut, start_at=datetime(2026, 10, 1, 4, tzinfo=UTC))
    response = customer_web.get(book_url(haircut, provider=sardor.pk, start=SLOT_0900_Z))
    assert response.status_code == 302
    assert messages_of(response) == ["Bu vaqt endi boʻsh emas. Boshqa vaqtni tanlang."]


@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.PROVIDER])
def test_staff_accounts_cannot_book(client, haircut, sardor, role):
    client.force_login(UserFactory(role=role))
    response = client.get(book_url(haircut, provider=sardor.pk, start=SLOT_0900_Z))
    assert response["Location"] == "/"
    assert messages_of(response) == ["Bron faqat mijoz akkaunti bilan qilinadi."]


def test_tampered_start_time_is_rejected_by_service(customer_web, haircut, sardor):
    response = customer_web.post(
        f"/book/{haircut.slug}/confirm/",
        {"provider": sardor.pk, "start_at": "2026-10-01T04:07:00Z", "idempotency_key": "k1"},
    )
    assert response.status_code == 302
    assert "jadval qadamiga mos emas" in messages_of(response)[0]
    assert not Booking.objects.exists()


def test_edge_33_long_names_are_truncated_not_overflowing(client, haircut):
    long_name = "Xushnudbek Abdurahmonov Jumaniyazov Toshkentlik"  # 46 characters
    provider = ProviderFactory(name=long_name, with_services=[haircut])
    AvailabilityRuleFactory(provider=provider, weekday=3, start_time=time(9), end_time=time(18))
    html = client.get(book_url(haircut)).content.decode()
    assert f'<span class="block truncate font-semibold">{long_name}</span>' in html
