"""Provider/admin dashboard (TASK 10.3 dashboard pages)."""

import re
from datetime import UTC, datetime, time, timedelta

import pytest
from django.contrib.messages import get_messages
from freezegun import freeze_time

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.catalog.models import Service
from apps.providers.models import Provider
from apps.scheduling.models import AvailabilityRule, BusinessSettings, TimeOff
from tests.bookings_setup import frozen_now, haircut, sardor
from tests.factories import (
    DEFAULT_PASSWORD,
    BookingFactory,
    ProviderFactory,
    ServiceFactory,
    UserFactory,
)

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

TODAY_0900 = datetime(2026, 9, 26, 4, tzinfo=UTC)  # Saturday 09:00 Tashkent; "now" is 17:00
THURSDAY_0900 = datetime(2026, 10, 1, 4, tzinfo=UTC)


def login_as(client, role, **kwargs):
    user = UserFactory(role=role, **kwargs)
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def admin_web(client):
    return login_as(client, User.Role.ADMIN)


@pytest.fixture
def staff_web(client, sardor):
    login_as(client, User.Role.PROVIDER)
    sardor.user = client.user
    sardor.save()
    return client


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


# --- access -------------------------------------------------------------------------------


def test_anonymous_is_sent_to_login(client):
    response = client.get("/dashboard/")
    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_customer_gets_403(client):
    login_as(client, User.Role.CUSTOMER)
    response = client.get("/dashboard/")
    assert response.status_code == 403
    assert "Ruxsat yoʻq" in response.content.decode()


@pytest.mark.parametrize(
    "url", ["/dashboard/services/", "/dashboard/providers/", "/dashboard/settings/"]
)
def test_provider_cannot_open_admin_pages(staff_web, url):
    assert staff_web.get(url).status_code == 403


def test_staff_login_lands_on_dashboard(client):
    user = UserFactory(role=User.Role.ADMIN)
    response = client.post("/login/", {"username": user.email, "password": DEFAULT_PASSWORD})
    assert response["Location"] == "/dashboard/"


def test_navbar_shows_dashboard_link_for_staff(admin_web):
    assert 'href="/dashboard/"' in admin_web.get("/").content.decode()


def test_edge_35_unlinked_provider_sees_explanation(client):
    login_as(client, User.Role.PROVIDER)
    assert "Xodim profili bogʻlanmagan" in client.get("/dashboard/").content.decode()
    response = client.get("/dashboard/my-schedule/")
    assert response.status_code == 403
    assert "bogʻlanmagan" in response.content.decode()


# --- today --------------------------------------------------------------------------------


def test_today_shows_columns_blocks_and_kpis(admin_web, haircut, sardor):
    other = ProviderFactory(name="Jasur", with_services=[haircut])
    customer = UserFactory(full_name="Ali Valiyev")
    BookingFactory(customer=customer, provider=sardor, service=haircut, start_at=TODAY_0900)
    BookingFactory(provider=other, service=haircut, start_at=TODAY_0900, status="confirmed")
    BookingFactory(
        provider=other,
        service=haircut,
        start_at=TODAY_0900 + timedelta(hours=2),
        status="cancelled",
    )

    html = admin_web.get("/dashboard/").content.decode()
    assert "Sardor" in html and "Jasur" in html
    assert "Ali Valiyev" in html
    assert "09:00–09:30" in html
    kpis = re.findall(r"text-2xl font-semibold tabular-nums[^>]*>([^<]+)<", html)
    assert kpis == ["2", "1", "33%"]  # 2 booked, 1 pending, 1 of 3 cancelled
    assert "Hozir" in html  # now-line legend on today


def test_provider_sees_only_own_column_and_bookings(staff_web, haircut, sardor):
    other = ProviderFactory(name="Jasur", with_services=[haircut])
    BookingFactory(
        provider=other,
        service=haircut,
        start_at=TODAY_0900,
        customer=UserFactory(full_name="Begona Mijoz"),
    )
    html = staff_web.get("/dashboard/").content.decode()
    assert "Sardor" in html
    assert "Jasur" not in html
    assert "Begona Mijoz" not in html


def test_other_day_shows_working_hours_and_no_now_line(admin_web, haircut, sardor):
    BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    html = admin_web.get("/dashboard/?date=2026-10-01").content.decode()
    assert "Pa, 1-okt" in html
    assert "09:00–09:30" in html
    assert "Hozir</span>" not in html
    assert 'class="absolute inset-x-0 bg-surface"' in html  # the 09–18 working window


def test_axis_grows_for_late_bookings(admin_web, haircut, sardor):
    BookingFactory(provider=sardor, service=haircut, start_at=datetime(2026, 9, 26, 16, tzinfo=UTC))
    html = admin_web.get("/dashboard/").content.decode()
    assert ">21:00<" in html  # 21:00–21:30 local pushes the axis past the default 19:00


# --- bookings list ------------------------------------------------------------------------


def test_list_filters_and_search(admin_web, haircut, sardor):
    other = ProviderFactory(name="Jasur", with_services=[haircut])
    BookingFactory(
        provider=sardor,
        service=haircut,
        start_at=THURSDAY_0900,
        customer=UserFactory(full_name="Ali Valiyev"),
    )
    BookingFactory(
        provider=other,
        service=haircut,
        start_at=THURSDAY_0900,
        customer=UserFactory(full_name="Vali Aliyev"),
        status="confirmed",
    )

    assert "2 ta bron" in admin_web.get("/dashboard/bookings/").content.decode()
    by_status = admin_web.get("/dashboard/bookings/?status=confirmed").content.decode()
    assert "Vali Aliyev" in by_status and "Ali Valiyev" not in by_status
    by_provider = admin_web.get(f"/dashboard/bookings/?provider={sardor.pk}").content.decode()
    assert "Ali Valiyev" in by_provider and "Vali Aliyev" not in by_provider
    by_search = admin_web.get("/dashboard/bookings/?q=vali+a").content.decode()
    assert "1 ta bron" in by_search
    by_date = admin_web.get("/dashboard/bookings/?date_from=2026-10-02").content.decode()
    assert "Filtrga mos bron topilmadi" in by_date


def test_list_paginates(admin_web, haircut, sardor):
    for i in range(25):
        BookingFactory(
            provider=sardor, service=haircut, start_at=THURSDAY_0900 + timedelta(hours=i)
        )
    first = admin_web.get("/dashboard/bookings/").content.decode()
    assert "1 / 2" in first
    assert "page=2" in first
    assert "2 / 2" in admin_web.get("/dashboard/bookings/?page=2").content.decode()


def test_provider_list_is_scoped(staff_web, haircut, sardor):
    BookingFactory(provider=ProviderFactory(), service=haircut, start_at=THURSDAY_0900)
    BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    assert "1 ta bron" in staff_web.get("/dashboard/bookings/").content.decode()


def test_quick_confirm_returns_to_list(admin_web, haircut, sardor):
    booking = BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    response = admin_web.post(
        f"/dashboard/bookings/{booking.pk}/confirm/",
        {"next": "/dashboard/bookings/?status=pending"},
    )
    assert response["Location"] == "/dashboard/bookings/?status=pending"
    booking.refresh_from_db()
    assert booking.status == "confirmed"


# --- detail and actions -------------------------------------------------------------------


def test_detail_offers_only_possible_actions(staff_web, haircut, sardor):
    booking = BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    html = staff_web.get(f"/dashboard/bookings/{booking.pk}/").content.decode()
    assert "Bronni tasdiqlash" in html
    assert 'id="cancel-dialog"' in html
    assert "Bajarildi deb belgilash" not in html


def test_confirm_then_complete_after_start(staff_web, haircut, sardor):
    booking = BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    staff_web.post(f"/dashboard/bookings/{booking.pk}/confirm/")
    with freeze_time("2026-10-01 04:40:00"):
        html = staff_web.get(f"/dashboard/bookings/{booking.pk}/").content.decode()
        assert "Bajarildi deb belgilash" in html
        staff_web.post(f"/dashboard/bookings/{booking.pk}/complete/")
    booking.refresh_from_db()
    assert booking.status == "completed"
    assert [h.changed_by for h in booking.history.all()] == [staff_web.user, staff_web.user]


def test_cancel_requires_reason(staff_web, haircut, sardor):
    booking = BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    response = staff_web.post(f"/dashboard/bookings/{booking.pk}/cancel/", {"reason": ""})
    assert messages_of(response) == ["Bekor qilish sababini yozing."]
    booking.refresh_from_db()
    assert booking.status == "pending"

    staff_web.post(f"/dashboard/bookings/{booking.pk}/cancel/", {"reason": "Xodim kasal"})
    booking.refresh_from_db()
    assert (booking.status, booking.cancel_reason) == ("cancelled", "Xodim kasal")


def test_edge_21_complete_before_start_is_refused(staff_web, haircut, sardor):
    booking = BookingFactory(
        provider=sardor, service=haircut, start_at=THURSDAY_0900, status="confirmed"
    )
    response = staff_web.post(f"/dashboard/bookings/{booking.pk}/complete/")
    assert "hali boshlanmagan" in messages_of(response)[0]
    booking.refresh_from_db()
    assert booking.status == "confirmed"


def test_other_providers_booking_is_404(staff_web, haircut):
    foreign = BookingFactory(provider=ProviderFactory(), service=haircut, start_at=THURSDAY_0900)
    assert staff_web.get(f"/dashboard/bookings/{foreign.pk}/").status_code == 404
    assert staff_web.post(f"/dashboard/bookings/{foreign.pk}/confirm/").status_code == 404


def test_unknown_action_is_404(admin_web, haircut, sardor):
    booking = BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    assert admin_web.post(f"/dashboard/bookings/{booking.pk}/delete/").status_code == 404


def test_customer_contact_is_shown_to_staff(staff_web, haircut, sardor):
    customer = UserFactory(phone="+998901234567")
    booking = BookingFactory(
        customer=customer, provider=sardor, service=haircut, start_at=THURSDAY_0900
    )
    html = staff_web.get(f"/dashboard/bookings/{booking.pk}/").content.decode()
    assert 'href="tel:+998901234567"' in html
    assert f'href="mailto:{customer.email}"' in html


# --- services -----------------------------------------------------------------------------


SERVICE_FORM = {
    "name": "Soqol oʻldirish",
    "slug": "",
    "description": "",
    "duration_minutes": "20",
    "price": "40000",
    "buffer_after_minutes": "0",
    "sort_order": "1",
    "is_active": "on",
}


def test_service_create_edit_and_errors(admin_web):
    response = admin_web.post("/dashboard/services/", SERVICE_FORM)
    assert response.status_code == 302
    service = Service.objects.get(slug="soqol-oldirish")

    html = admin_web.get(f"/dashboard/services/?edit={service.pk}").content.decode()
    assert "Xizmatni tahrirlash" in html and "data-autoshow" in html
    admin_web.post(f"/dashboard/services/?edit={service.pk}", {**SERVICE_FORM, "price": "45000"})
    service.refresh_from_db()
    assert str(service.price) == "45000.00"

    bad = admin_web.post("/dashboard/services/", {**SERVICE_FORM, "duration_minutes": "7"})
    assert "5 ga karrali" in bad.content.decode()
    taken = admin_web.post("/dashboard/services/", {**SERVICE_FORM, "slug": "soqol-oldirish"})
    assert "Bu slug band" in taken.content.decode()


def test_service_deactivate_reports_kept_bookings(admin_web, haircut, sardor):
    BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    page = admin_web.get("/dashboard/services/").content.decode()
    assert "1 ta kelgusi bron" in page
    response = admin_web.post(f"/dashboard/services/{haircut.pk}/deactivate/")
    assert "1 ta kelgusi bron saqlanib qoldi" in messages_of(response)[0]
    haircut.refresh_from_db()
    assert haircut.is_active is False
    assert Booking.objects.get().status == "pending"


def test_bad_edit_id_is_404(admin_web):
    assert admin_web.get("/dashboard/services/?edit=nope").status_code == 404
    assert admin_web.get("/dashboard/providers/?edit=nope").status_code == 404


# --- providers ----------------------------------------------------------------------------


def test_provider_create_with_services_and_login(admin_web, haircut):
    staff = UserFactory(role=User.Role.PROVIDER)
    response = admin_web.post(
        "/dashboard/providers/",
        {
            "name": "Jasur",
            "bio": "",
            "color": "#16A34A",
            "timezone": "",
            "user": str(staff.pk),
            "services": [str(haircut.pk)],
            "is_active": "on",
        },
    )
    assert response.status_code == 302, response.content.decode()[:500]
    provider = Provider.objects.get(name="Jasur")
    assert provider.user == staff
    assert provider.timezone is None
    assert list(provider.services.all()) == [haircut]


def test_provider_edit_changes_services(admin_web, haircut, sardor):
    beard = ServiceFactory(name="Soqol")
    admin_web.post(
        f"/dashboard/providers/?edit={sardor.pk}",
        {
            "name": "Sardor",
            "color": "#2563EB",
            "timezone": "Asia/Dubai",
            "services": [str(beard.pk)],
            "is_active": "on",
        },
    )
    sardor.refresh_from_db()
    assert list(sardor.services.all()) == [beard]
    assert sardor.timezone == "Asia/Dubai"


def test_customer_account_cannot_be_linked(admin_web):
    customer = UserFactory(role=User.Role.CUSTOMER)
    html = admin_web.post(
        "/dashboard/providers/", {"name": "X", "color": "#2563EB", "user": str(customer.pk)}
    ).content.decode()
    assert "aria-invalid" in html
    assert not Provider.objects.filter(name="X").exists()


def test_provider_deactivate(admin_web, sardor):
    response = admin_web.post(f"/dashboard/providers/{sardor.pk}/deactivate/")
    assert messages_of(response) == ["«Sardor» nofaol qilindi."]
    sardor.refresh_from_db()
    assert sardor.is_active is False


# --- availability and time off ------------------------------------------------------------


def week_post(**days):
    data = {}
    for day, windows in days.items():
        data[f"start_{day[1:]}"] = [w[0] for w in windows]
        data[f"end_{day[1:]}"] = [w[1] for w in windows]
    return data


def test_availability_page_renders_rules_as_json(staff_web, sardor):
    html = staff_web.get(f"/dashboard/providers/{sardor.pk}/availability/").content.decode()
    assert '"3": [{"start": "09:00", "end": "18:00"}]' in html


def test_availability_save_replaces_week(staff_web, sardor):
    response = staff_web.post(
        f"/dashboard/providers/{sardor.pk}/availability/",
        week_post(d0=[("09:00", "13:00"), ("14:00", "18:00")], d3=[("10:00", "16:00")]),
    )
    assert response.status_code == 302
    rules = list(
        AvailabilityRule.objects.filter(provider=sardor).values_list("weekday", "start_time")
    )
    assert rules == [(0, time(9)), (0, time(14)), (3, time(10))]


def test_availability_overlap_and_midnight_errors_keep_input(staff_web, sardor):
    overlap = staff_web.post(
        f"/dashboard/providers/{sardor.pk}/availability/",
        week_post(d0=[("09:00", "14:00"), ("13:00", "18:00")]),
    )
    assert overlap.status_code == 422
    assert "kesishadi" in overlap.content.decode()
    assert (
        '"0": [{"start": "09:00", "end": "14:00"}, {"start": "13:00", "end": "18:00"}]'
        in overlap.content.decode()
    )

    midnight = staff_web.post(
        f"/dashboard/providers/{sardor.pk}/availability/", week_post(d4=[("22:00", "02:00")])
    )
    assert "Yarim tundan" in midnight.content.decode()
    assert AvailabilityRule.objects.filter(provider=sardor).count() == 1  # untouched


def test_edge_14_narrowing_over_booking_shows_conflict_list(staff_web, haircut, sardor):
    booking = BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    response = staff_web.post(
        f"/dashboard/providers/{sardor.pk}/availability/", week_post(d3=[("10:00", "18:00")])
    )
    html = response.content.decode()
    assert response.status_code == 409
    assert "1 ta faol bron bilan toʻqnashadi" in html
    assert f"/dashboard/bookings/{booking.pk}/" in html
    assert "Pa, 1-okt, 09:00" in html


def test_provider_cannot_edit_other_schedule(staff_web):
    other = ProviderFactory()
    assert staff_web.get(f"/dashboard/providers/{other.pk}/availability/").status_code == 403
    assert staff_web.post(f"/dashboard/providers/{other.pk}/time-off/", {}).status_code == 403


def test_my_schedule_redirects_to_own_page(staff_web, sardor):
    response = staff_web.get("/dashboard/my-schedule/")
    assert response["Location"] == f"/dashboard/providers/{sardor.pk}/availability/"


def test_time_off_uses_provider_local_time(staff_web, sardor):
    response = staff_web.post(
        f"/dashboard/providers/{sardor.pk}/time-off/",
        {"start_at": "2026-10-05T09:00", "end_at": "2026-10-05T18:00", "reason": "Shifokor"},
    )
    assert response.status_code == 302
    item = TimeOff.objects.get()
    assert item.start_at == datetime(2026, 10, 5, 4, tzinfo=UTC)  # 09:00 Tashkent
    page = staff_web.get(f"/dashboard/providers/{sardor.pk}/availability/").content.decode()
    assert "Shifokor" in page

    staff_web.post(f"/dashboard/providers/{sardor.pk}/time-off/{item.pk}/delete/")
    assert not TimeOff.objects.exists()


def test_edge_13_time_off_over_booking_is_refused_with_list(staff_web, haircut, sardor):
    BookingFactory(provider=sardor, service=haircut, start_at=THURSDAY_0900)
    response = staff_web.post(
        f"/dashboard/providers/{sardor.pk}/time-off/",
        {"start_at": "2026-10-01T08:00", "end_at": "2026-10-01T12:00"},
    )
    assert response.status_code == 409
    assert "toʻqnashadi" in response.content.decode()
    assert not TimeOff.objects.exists()


def test_time_off_end_before_start(staff_web, sardor):
    response = staff_web.post(
        f"/dashboard/providers/{sardor.pk}/time-off/",
        {"start_at": "2026-10-05T18:00", "end_at": "2026-10-05T09:00"},
    )
    assert response.status_code == 422
    assert "Tugash vaqti boshlanishdan keyin" in response.content.decode()


# --- settings -----------------------------------------------------------------------------


def test_settings_save(admin_web):
    response = admin_web.post(
        "/dashboard/settings/",
        {
            "name": "Navbat Salon",
            "timezone": "Asia/Tashkent",
            "currency": "UZS",
            "slot_step_minutes": "30",
            "min_lead_time_minutes": "120",
            "max_advance_days": "14",
            "cancellation_deadline_hours": "12",
            "auto_confirm": "on",
        },
    )
    assert response.status_code == 302
    business = BusinessSettings.load()
    assert (business.name, business.slot_step_minutes, business.auto_confirm) == (
        "Navbat Salon",
        30,
        True,
    )


def test_settings_validation(admin_web):
    html = admin_web.post(
        "/dashboard/settings/", {"name": "", "slot_step_minutes": "7"}
    ).content.decode()
    assert 'aria-invalid="true"' in html
    assert BusinessSettings.load().slot_step_minutes == 15


def test_day_view_css_positions_are_not_localized(admin_web, haircut, sardor):
    # 17:00–17:30 on an axis 09:00–19:00 → top 80%, height 5%; a decimal comma would be
    # invalid CSS and the block would jump to the top of the column.
    BookingFactory(provider=sardor, service=haircut, start_at=datetime(2026, 9, 26, 12, tzinfo=UTC))
    html = admin_web.get("/dashboard/").content.decode()
    assert "top: 80.000%; height: 5.000%;" in html
    assert not re.search(r"top: \d+,\d+", html)
