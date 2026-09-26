"""Booking emails.

Always called through transaction.on_commit (ADR-006): a booking that was rolled back never
produces an email, and a failing mail server never rolls a booking back — every sender
swallows and logs its own errors (edge case #29).
"""

import logging
from functools import wraps

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.scheduling.models import BusinessSettings
from apps.web import text

logger = logging.getLogger(__name__)


def _never_raise(sender):
    @wraps(sender)
    def wrapper(*args, **kwargs):
        try:
            sender(*args, **kwargs)
        except Exception:
            # The booking is already committed; losing an email must not look like a failed
            # booking to the customer. The log line is the signal to follow up manually.
            logger.exception("Email not sent: %s%s", sender.__name__, args)

    return wrapper


def _load(booking_id) -> Booking | None:
    return (
        Booking.objects.select_related("customer", "provider__user", "cancelled_by")
        .filter(pk=booking_id)
        .first()
    )


def _when(booking: Booking, tz: str) -> dict:
    start = text.local(booking.start_at, tz)
    end = text.local(booking.end_at, tz)
    short_day = text.short_day(start.date())
    return {
        "day": text.long_day(start.date()),
        "time": f"{start:%H:%M}–{end:%H:%M}",
        "label": f"{short_day} {start:%H:%M}",
        "tz": tz,
    }


def _send(*, to: str, subject: str, template: str, context: dict) -> None:
    body = render_to_string(f"emails/{template}.txt", context)
    html = render_to_string(f"emails/{template}.html", context)
    message = EmailMultiAlternatives(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
    message.attach_alternative(html, "text/html")
    message.send()
    logger.info("Email sent: %s to %s", template, to)


def _customer_context(booking: Booking, business: BusinessSettings) -> dict:
    return {
        "booking": booking,
        "business": business,
        "price": text.money(booking.price, business.currency),
        "when": _when(booking, booking.customer.timezone or business.timezone),
        "link": settings.SITE_URL + reverse("web:booking_detail", args=[booking.pk]),
        "deadline_hours": business.cancellation_deadline_hours,
    }


def _staff_context(booking: Booking, business: BusinessSettings, staff: User) -> dict:
    return {
        "booking": booking,
        "business": business,
        "when": _when(booking, staff.timezone or business.timezone),
        "link": settings.SITE_URL + reverse("web:dashboard_booking", args=[booking.pk]),
    }


def _provider_user(booking: Booking) -> User | None:
    user = booking.provider.user
    return user if user is not None and user.is_active else None


@_never_raise
def booking_created(booking_id) -> None:
    booking = _load(booking_id)
    if booking is None:
        return
    business = BusinessSettings.load()
    context = _customer_context(booking, business)
    label = context["when"]["label"]
    if booking.status == Booking.Status.CONFIRMED:  # auto_confirm: one email, not two
        subject, template = (
            f"Bron tasdiqlandi — {booking.service_name}, {label}",
            "booking_confirmed",
        )
    else:
        subject, template = (
            f"Bron qabul qilindi — {booking.service_name}, {label}",
            "booking_created",
        )
    _send(to=booking.customer.email, subject=subject, template=template, context=context)

    staff = _provider_user(booking)
    if staff:
        staff_context = _staff_context(booking, business, staff)
        _send(
            to=staff.email,
            subject=f"Yangi bron: {booking.customer.full_name}, {staff_context['when']['label']}",
            template="staff_booking_created",
            context=staff_context,
        )


@_never_raise
def booking_status_changed(booking_id, to_status: str) -> None:
    booking = _load(booking_id)
    if booking is None:
        return
    business = BusinessSettings.load()
    context = _customer_context(booking, business)
    label = context["when"]["label"]

    if to_status == Booking.Status.CONFIRMED:
        _send(
            to=booking.customer.email,
            subject=f"Bron tasdiqlandi — {booking.service_name}, {label}",
            template="booking_confirmed",
            context=context,
        )
    elif to_status == Booking.Status.CANCELLED:
        by_customer = booking.cancelled_by_id == booking.customer_id
        _send(
            to=booking.customer.email,
            subject=f"Bron bekor qilindi — {booking.service_name}, {label}",
            template="booking_cancelled",
            context={**context, "by_customer": by_customer},
        )
        staff = _provider_user(booking)
        if by_customer and staff:
            staff_context = _staff_context(booking, business, staff)
            _send(
                to=staff.email,
                subject=f"Mijoz bronni bekor qildi: {booking.customer.full_name}, "
                f"{staff_context['when']['label']}",
                template="staff_booking_cancelled",
                context=staff_context,
            )
    # completed: nothing to tell anyone.
