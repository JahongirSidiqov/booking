"""RFC 5545 (iCalendar) export of a single booking. Pure: no database, `now` is passed in.

Kept dependency-free on purpose: one VEVENT needs only escaping, line folding and CRLF, and
a library would be a larger surface than this file.
"""

from datetime import UTC, datetime
from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.scheduling.models import BusinessSettings

from .models import Booking

PRODID = "-//Navbat//Booking//UZ"
STATUS_MAP = {
    Booking.Status.PENDING: "TENTATIVE",
    Booking.Status.CONFIRMED: "CONFIRMED",
    Booking.Status.COMPLETED: "CONFIRMED",
    Booking.Status.CANCELLED: "CANCELLED",
}


def _escape(value: str) -> str:
    # RFC 5545 §3.3.11: backslash first, then the separators, newlines as literal "\n".
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after CRLF + one space.

    Counting octets, not characters: Uzbek ʻ is two bytes in UTF-8, and splitting inside a
    multi-byte character would corrupt the text.
    """
    out, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        limit = 75 if not out else 74  # continuation lines start with a space
        if len(current) + len(encoded) > limit:
            out.append(current.decode("utf-8"))
            current = b""
        current += encoded
    out.append(current.decode("utf-8"))
    return "\r\n ".join(out)


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def booking_calendar(
    booking: Booking, *, business_name: str, link: str, now: datetime, domain: str
) -> str:
    description = f"Xodim: {booking.provider.name}\nBron: {link}"
    if booking.customer_note:
        description += f"\nIzoh: {booking.customer_note}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:booking-{booking.pk}@{domain}",
        f"DTSTAMP:{_utc(now)}",
        f"DTSTART:{_utc(booking.start_at)}",
        f"DTEND:{_utc(booking.end_at)}",
        # Calendars replace an event only when SEQUENCE grows; every status change counts.
        f"SEQUENCE:{max(booking.history.count() - 1, 0)}",
        f"STATUS:{STATUS_MAP[booking.status]}",
        f"SUMMARY:{_escape(f'{booking.service_name} — {business_name}')}",
        f"LOCATION:{_escape(business_name)}",
        f"DESCRIPTION:{_escape(description)}",
        f"URL:{link}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "".join(_fold(line) + "\r\n" for line in lines)


def calendar_file(booking: Booking) -> tuple[str, str]:
    """(filename, .ics body) for a booking, using site and business settings."""
    link = settings.SITE_URL + reverse("web:booking_detail", args=[booking.pk])
    body = booking_calendar(
        booking,
        business_name=BusinessSettings.load().name,
        link=link,
        now=timezone.now(),
        domain=urlparse(settings.SITE_URL).hostname or "navbat",
    )
    return f"navbat-{booking.start_at.astimezone(UTC):%Y%m%d-%H%M}.ics", body
