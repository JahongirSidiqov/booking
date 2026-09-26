"""Operational pieces: health check, expiry job, demo seed."""

from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError
from freezegun import freeze_time

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import ACTIVE_STATUSES, Booking
from apps.catalog.models import Service
from apps.providers.models import Provider
from apps.scheduling.models import AvailabilityRule, TimeOff
from tests.factories import BookingFactory, ProviderFactory, ServiceFactory

pytestmark = pytest.mark.django_db


# --- /healthz -----------------------------------------------------------------------------


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_healthz_reports_database_down(client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise DatabaseError("connection refused")

    monkeypatch.setattr("apps.common.views.connection.cursor", broken_cursor)
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_healthz_is_exempt_from_ssl_redirect():
    from config.settings import prod

    assert r"^healthz$" in prod.SECURE_REDIRECT_EXEMPT
    assert "localhost" in prod.ALLOWED_HOSTS


# --- expire_stale_bookings ----------------------------------------------------------------

START = datetime(2026, 10, 1, 4, tzinfo=UTC)


@pytest.fixture
def scenario():
    service = ServiceFactory()
    return service, ProviderFactory(with_services=[service])


def test_edge_22_expire_cancels_only_past_pending(
    scenario, django_capture_on_commit_callbacks, mailoutbox
):
    service, provider = scenario
    stale = BookingFactory(service=service, provider=provider, start_at=START)
    confirmed = BookingFactory(
        service=service, provider=provider, start_at=START.replace(hour=5), status="confirmed"
    )
    upcoming = BookingFactory(service=service, provider=provider, start_at=START.replace(day=2))

    with freeze_time("2026-10-01 04:10:00"), django_capture_on_commit_callbacks(execute=True):
        out = StringIO()
        call_command("expire_stale_bookings", stdout=out)

    assert out.getvalue().strip() == "expired: 1"
    stale.refresh_from_db()
    assert (stale.status, stale.cancel_reason, stale.cancelled_by) == ("cancelled", "expired", None)
    entry = stale.history.get()
    assert (entry.from_status, entry.to_status, entry.changed_by, entry.reason) == (
        "pending",
        "cancelled",
        None,
        "expired",
    )
    assert Booking.objects.get(pk=confirmed.pk).status == "confirmed"
    assert Booking.objects.get(pk=upcoming.pk).status == "pending"
    assert len(mailoutbox) == 1
    assert "Vaqtida tasdiqlanmagani uchun avtomatik bekor qilindi." in mailoutbox[0].body


def test_expire_skips_booking_confirmed_meanwhile(scenario, monkeypatch):
    """The candidate list is read first; a confirmation landing before the lock must win."""
    service, provider = scenario
    booking = BookingFactory(service=service, provider=provider, start_at=START)
    original_filter = Booking.objects.filter

    def list_then_confirm(*args, **kwargs):
        qs = original_filter(*args, **kwargs)
        if kwargs.get("start_at__lte"):  # the candidate query
            ids = list(qs.values_list("pk", flat=True))
            original_filter(pk=booking.pk).update(status="confirmed")  # a provider clicked
            return original_filter(pk__in=ids)
        return qs

    monkeypatch.setattr(Booking.objects, "filter", list_then_confirm)
    with freeze_time("2026-10-01 04:10:00"):
        assert services.expire_stale_bookings() == 0
    monkeypatch.undo()
    assert Booking.objects.get(pk=booking.pk).status == "confirmed"


def test_expire_is_idempotent(scenario):
    service, provider = scenario
    BookingFactory(service=service, provider=provider, start_at=START)
    with freeze_time("2026-10-01 04:10:00"):
        assert services.expire_stale_bookings() == 1
        assert services.expire_stale_bookings() == 0


# --- seed_demo ----------------------------------------------------------------------------


def test_seed_demo_builds_a_complete_business():
    out = StringIO()
    call_command("seed_demo", stdout=out)

    assert Service.objects.count() == 5
    assert Provider.objects.count() == 3
    assert AvailabilityRule.objects.exists()
    assert TimeOff.objects.count() == 1
    statuses = set(Booking.objects.values_list("status", flat=True))
    assert statuses == {"pending", "confirmed", "cancelled", "completed"}
    assert Booking.objects.count() >= 20
    # Every booking went through the service: each has a status history starting at pending.
    for booking in Booking.objects.prefetch_related("history"):
        history = list(booking.history.all())
        assert history[0].from_status is None and history[0].to_status == "pending"
        assert history[-1].to_status == booking.status
    assert (
        Booking.objects.filter(start_at__lt=datetime.now(UTC), status__in=ACTIVE_STATUSES).count()
        == 0
    )

    sardor = Provider.objects.get(name="Sardor Rahimov")
    assert sardor.user.email == "sardor@navbat.uz"
    admin = User.objects.get(email="admin@navbat.uz")
    assert admin.is_superuser and admin.role == User.Role.ADMIN
    assert User.objects.get(email="mijoz@navbat.uz").check_password("Navbat-Demo-2026")
    assert "Demo data ready" in out.getvalue()


def test_seed_demo_refuses_non_empty_database():
    ServiceFactory()
    with pytest.raises(CommandError, match="not empty"):
        call_command("seed_demo", stdout=StringIO())


def test_seed_demo_custom_password():
    call_command("seed_demo", "--password", "Boshqa-Parol-1", stdout=StringIO())
    assert User.objects.get(email="admin@navbat.uz").check_password("Boshqa-Parol-1")


# --- static files in production -----------------------------------------------------------


def test_collectstatic_with_production_manifest_storage(tmp_path, settings):
    """The prod container runs collectstatic on start; a broken url()/@import kills it."""
    settings.STATIC_ROOT = tmp_path
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    call_command("collectstatic", "--noinput", verbosity=0)

    built = next((tmp_path / "css").glob("app.*.css"))
    assert "fonts/inter-latin-wght-normal." in built.read_text(encoding="utf-8")
    assert not (tmp_path / "src").exists()  # Tailwind source stays out of static/
