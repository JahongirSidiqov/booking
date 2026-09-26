"""RFC 5545 export: escaping, folding, line endings, status and sequence."""

from datetime import UTC, datetime

import pytest

from apps.bookings.ical import _escape, _fold, booking_calendar
from apps.bookings.models import BookingStatusHistory
from tests.factories import BookingFactory, ProviderFactory, ServiceFactory

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def render(booking, **kwargs):
    return booking_calendar(
        booking,
        business_name=kwargs.get("business_name", "Navbat Barbershop"),
        link="https://navbat.uz/bookings/x/",
        now=NOW,
        domain="navbat.uz",
    )


def unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


@pytest.fixture
def booking():
    service = ServiceFactory(name="Soch olish")
    provider = ProviderFactory(name="Sardor")
    return BookingFactory(
        service=service,
        provider=provider,
        start_at=datetime(2026, 10, 1, 4, tzinfo=UTC),
        customer_note="Qisqaroq, iltimos; rahmat",
    )


def test_event_fields(booking):
    lines = unfold(render(booking))
    assert lines[0] == "BEGIN:VCALENDAR"
    assert f"UID:booking-{booking.pk}@navbat.uz" in lines
    assert "DTSTAMP:20260926T120000Z" in lines
    assert "DTSTART:20261001T040000Z" in lines
    assert "DTEND:20261001T043000Z" in lines
    assert "STATUS:TENTATIVE" in lines
    assert "SUMMARY:Soch olish — Navbat Barbershop" in lines
    assert (
        "DESCRIPTION:Xodim: Sardor\\nBron: https://navbat.uz/bookings/x/"
        "\\nIzoh: Qisqaroq\\, iltimos\\; rahmat"
    ) in lines
    assert lines[-2] == "END:VCALENDAR" and lines[-1] == ""


def test_lines_end_with_crlf_only(booking):
    ics = render(booking)
    assert "\n" not in ics.replace("\r\n", "")


@pytest.mark.parametrize(
    ("status", "expected"),
    [("confirmed", "CONFIRMED"), ("cancelled", "CANCELLED"), ("completed", "CONFIRMED")],
)
def test_status_mapping(status, expected):
    booking = BookingFactory(status=status)
    assert f"STATUS:{expected}" in unfold(render(booking))


def test_sequence_grows_with_status_changes(booking):
    assert "SEQUENCE:0" in unfold(render(booking))
    BookingStatusHistory.objects.create(booking=booking, to_status="pending")
    BookingStatusHistory.objects.create(
        booking=booking, from_status="pending", to_status="confirmed"
    )
    assert "SEQUENCE:1" in unfold(render(booking))


def test_escape():
    assert _escape("a\\b;c,d\ne") == "a\\\\b\\;c\\,d\\ne"


def test_fold_limits_octets_and_keeps_multibyte_characters_whole():
    line = "SUMMARY:" + "Soqol oʻldirish " * 10  # ʻ is 2 bytes in UTF-8
    folded = _fold(line)
    parts = folded.split("\r\n ")
    assert all(len(part.encode("utf-8")) <= 75 for part in parts)
    assert "".join(parts) == line  # nothing lost, no broken character


def test_long_business_name_is_folded(booking):
    ics = render(booking, business_name="Navbat " * 20)
    assert all(len(raw.encode("utf-8")) <= 75 for raw in ics.split("\r\n"))
