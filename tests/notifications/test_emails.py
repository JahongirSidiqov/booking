"""Booking emails: sent after commit, never before; a mail failure never undoes a booking."""

import logging

import pytest
from django.db import OperationalError
from django.utils.dateparse import parse_datetime
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking, BookingStatusHistory
from apps.common.exceptions import DomainError
from apps.notifications import senders
from apps.scheduling.models import BusinessSettings
from tests.bookings_setup import BOOKINGS, SLOT_0900, booking_body, frozen_now, haircut, sardor
from tests.factories import UserFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]


@pytest.fixture
def customer():
    return UserFactory(role=User.Role.CUSTOMER, full_name="Ali Valiyev", email="ali@example.com")


@pytest.fixture
def staff(sardor):
    user = UserFactory(role=User.Role.PROVIDER, email="sardor@example.com")
    sardor.user = user
    sardor.save()
    return user


def create(customer, haircut, sardor, **kwargs):
    return services.create_booking(
        customer=customer,
        service_id=haircut.pk,
        provider_id=sardor.pk,
        start_at=parse_datetime(SLOT_0900),
        **kwargs,
    ).booking


def by_recipient(outbox):
    return {m.to[0]: m for m in outbox}


# --- created ------------------------------------------------------------------------------


def test_created_emails_customer_and_linked_provider(
    customer, staff, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        booking = create(customer, haircut, sardor, note="Qisqaroq")

    mails = by_recipient(mailoutbox)
    assert set(mails) == {"ali@example.com", "sardor@example.com"}

    to_customer = mails["ali@example.com"]
    assert to_customer.subject == "Bron qabul qilindi — Soch olish, Pa, 1-okt 09:00"
    assert "Ali Valiyev" in to_customer.body
    assert "1-oktabr, payshanba" in to_customer.body
    assert "09:00–09:30 (Asia/Tashkent)" in to_customer.body
    assert "60 000 soʻm" in to_customer.body
    assert f"http://localhost:8000/bookings/{booking.pk}/" in to_customer.body
    html, mimetype = to_customer.alternatives[0]
    assert mimetype == "text/html"
    assert f'href="http://localhost:8000/bookings/{booking.pk}/"' in html

    to_staff = mails["sardor@example.com"]
    assert to_staff.subject.startswith("Yangi bron: Ali Valiyev")
    assert "Izoh:   Qisqaroq" in to_staff.body
    assert f"/dashboard/bookings/{booking.pk}/" in to_staff.body


def test_email_uses_customer_timezone(
    haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    dubai = UserFactory(timezone="Asia/Dubai")
    with django_capture_on_commit_callbacks(execute=True):
        create(dubai, haircut, sardor)
    assert "08:00–08:30 (Asia/Dubai)" in mailoutbox[0].body


def test_no_email_before_commit(
    customer, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        create(customer, haircut, sardor)
    assert len(callbacks) == 1
    assert mailoutbox == []  # nothing is sent while the transaction is still open


def test_edge_36_auto_confirm_sends_one_confirmed_email(
    customer, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    business = BusinessSettings.load()
    business.auto_confirm = True
    business.save()
    with django_capture_on_commit_callbacks(execute=True):
        create(customer, haircut, sardor)
    assert [m.subject for m in mailoutbox] == ["Bron tasdiqlandi — Soch olish, Pa, 1-okt 09:00"]


def test_idempotent_replay_sends_nothing_new(
    customer, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        create(customer, haircut, sardor, idempotency_key="k1")
        create(customer, haircut, sardor, idempotency_key="k1")
    assert len(mailoutbox) == 1


def test_plain_text_is_not_html_escaped(
    haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    customer = UserFactory(full_name="Ali & Vali <MChJ>")
    with django_capture_on_commit_callbacks(execute=True):
        create(customer, haircut, sardor)
    assert "Ali & Vali <MChJ>" in mailoutbox[0].body
    assert "Ali &amp; Vali &lt;MChJ&gt;" in mailoutbox[0].alternatives[0][0]


# --- status changes -----------------------------------------------------------------------


def transition(booking, to_status, actor, reason=""):
    return services.transition_booking(
        booking_id=booking.pk, to_status=to_status, actor=actor, reason=reason
    )


def test_confirm_emails_customer(
    customer, staff, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    booking = create(customer, haircut, sardor)
    with django_capture_on_commit_callbacks(execute=True):
        transition(booking, Booking.Status.CONFIRMED, staff)
    assert [(m.to[0], m.subject) for m in mailoutbox] == [
        ("ali@example.com", "Bron tasdiqlandi — Soch olish, Pa, 1-okt 09:00")
    ]


def test_staff_cancel_emails_customer_with_reason(
    customer, staff, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    booking = create(customer, haircut, sardor)
    with django_capture_on_commit_callbacks(execute=True):
        transition(booking, Booking.Status.CANCELLED, staff, "Xodim kasal")
    assert len(mailoutbox) == 1
    mail = mailoutbox[0]
    assert mail.to == ["ali@example.com"]
    assert "afsuski" in mail.body
    assert "Sabab: Xodim kasal" in mail.body


def test_customer_cancel_acknowledges_and_tells_provider(
    customer, staff, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    booking = create(customer, haircut, sardor)
    with django_capture_on_commit_callbacks(execute=True):
        transition(booking, Booking.Status.CANCELLED, customer, "Rejalar oʻzgardi")
    mails = by_recipient(mailoutbox)
    assert "bekor qilganingiz qayd etildi" in mails["ali@example.com"].body
    assert mails["sardor@example.com"].subject.startswith("Mijoz bronni bekor qildi: Ali Valiyev")
    assert "Sabab:  Rejalar oʻzgardi" in mails["sardor@example.com"].body


def test_complete_sends_nothing(
    customer, staff, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    booking = create(customer, haircut, sardor)
    transition(booking, Booking.Status.CONFIRMED, staff)
    with freeze_time("2026-10-01 04:40:00"), django_capture_on_commit_callbacks(execute=True):
        transition(booking, Booking.Status.COMPLETED, staff)
    assert mailoutbox == []


def test_provider_without_account_gets_no_email(
    customer, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        create(customer, haircut, sardor)
    assert [m.to[0] for m in mailoutbox] == ["ali@example.com"]


def test_refused_transition_sends_nothing(
    customer, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks
):
    booking = create(customer, haircut, sardor)
    other = UserFactory(role=User.Role.CUSTOMER)
    with django_capture_on_commit_callbacks(execute=True), pytest.raises(DomainError):
        transition(booking, Booking.Status.CANCELLED, other)
    assert mailoutbox == []


# --- failures -----------------------------------------------------------------------------


def test_edge_29_mail_failure_keeps_booking_and_is_logged(
    haircut, sardor, mailoutbox, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    def smtp_down(self, *args, **kwargs):
        raise ConnectionRefusedError("SMTP server unreachable")

    monkeypatch.setattr("django.core.mail.EmailMultiAlternatives.send", smtp_down)
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.CUSTOMER))

    with (
        caplog.at_level(logging.ERROR, logger="apps.notifications.senders"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client.post(BOOKINGS, booking_body(haircut, sardor), format="json")

    assert response.status_code == 201
    assert Booking.objects.filter(pk=response.json()["id"]).exists()
    assert mailoutbox == []
    assert "Email not sent: booking_created" in caplog.text
    assert "SMTP server unreachable" in caplog.text


def test_edge_37_rolled_back_booking_sends_no_email(
    customer, haircut, sardor, mailoutbox, django_capture_on_commit_callbacks, monkeypatch
):
    def lose_connection(**kwargs):
        raise OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(BookingStatusHistory.objects, "create", lose_connection)
    with (
        django_capture_on_commit_callbacks(execute=True) as callbacks,
        pytest.raises(OperationalError),
    ):
        create(customer, haircut, sardor)
    assert callbacks == []
    assert mailoutbox == []
    assert not Booking.objects.exists()


def test_sender_ignores_missing_booking(mailoutbox):
    senders.booking_created("00000000-0000-0000-0000-000000000000")
    senders.booking_status_changed("00000000-0000-0000-0000-000000000000", "confirmed")
    assert mailoutbox == []
