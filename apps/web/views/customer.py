from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.bookings import ical
from apps.bookings import selectors as booking_selectors
from apps.bookings import services as booking_services
from apps.bookings.models import ACTIVE_STATUSES, Booking
from apps.catalog import selectors as catalog_selectors
from apps.common.exceptions import DomainError
from apps.scheduling.models import BusinessSettings
from apps.web.forms import CancelForm

TABS = (("upcoming", "Kelgusi"), ("past", "Oʻtgan"), ("cancelled", "Bekor qilingan"))


def home(request):
    return render(request, "web/home.html", {"services": catalog_selectors.service_list()})


@login_required
def my_bookings(request):
    tab = request.GET.get("tab", "upcoming")
    if tab not in dict(TABS):
        tab = "upcoming"
    bookings = booking_selectors.customer_tab(request.user, tab, now=timezone.now())
    return render(
        request,
        "web/bookings.html",
        {"bookings": bookings.select_related("provider"), "tabs": TABS, "tab": tab},
    )


def _customer_can_cancel(booking: Booking, user: User) -> tuple[bool, bool]:
    """(cancel button visible, deadline already passed) for the customer view."""
    if user.role != User.Role.CUSTOMER or booking.status not in ACTIVE_STATUSES:
        return False, False
    business = BusinessSettings.load()
    deadline = booking.start_at - timezone.timedelta(hours=business.cancellation_deadline_hours)
    passed = timezone.now() > deadline
    return not passed, passed


@login_required
def booking_detail(request, booking_id):
    booking = booking_selectors.visible_booking(request.user, booking_id)
    if booking is None:
        raise Http404
    can_cancel, deadline_passed = _customer_can_cancel(booking, request.user)
    return render(
        request,
        "web/booking_detail.html",
        {
            "booking": booking,
            "history": booking.history.all(),
            "can_cancel": can_cancel,
            "deadline_passed": deadline_passed,
            "cancel_form": CancelForm(),
        },
    )


@login_required
@require_POST
def cancel_booking(request, booking_id):
    form = CancelForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Sabab 500 belgidan oshmasin.")
        return redirect("web:booking_detail", booking_id=booking_id)
    try:
        booking_services.transition_booking(
            booking_id=booking_id,
            to_status=Booking.Status.CANCELLED,
            actor=request.user,
            reason=form.cleaned_data["reason"],
        )
    except DomainError as exc:
        if exc.code == "NOT_FOUND":
            raise Http404 from exc
        messages.error(request, exc.message)
    else:
        messages.success(request, "Bron bekor qilindi.")
    return redirect("web:booking_detail", booking_id=booking_id)


@login_required
def booking_ical(request, booking_id):
    booking = booking_selectors.visible_booking(request.user, booking_id)
    if booking is None or booking.customer_id != request.user.pk:
        raise Http404
    filename, body = ical.calendar_file(booking)
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
