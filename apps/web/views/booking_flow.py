"""Public booking flow: service → provider → date & time → confirm → result.

Views only translate HTTP into service/selector calls (TASK 3.1). Steps are driven by query
parameters so every step has a shareable URL and the back button behaves.
"""

import uuid
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.bookings import selectors as booking_selectors
from apps.bookings import services as booking_services
from apps.catalog import selectors as catalog_selectors
from apps.common.exceptions import DomainError
from apps.providers import selectors as provider_selectors
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling.models import BusinessSettings
from apps.web import text
from apps.web.forms import BookingConfirmForm

STRIP_DAYS = 7
BOOKING_STEPS = ((1, "Xodim"), (2, "Vaqt"), (3, "Tasdiq"))
DAY_PARTS = (("morning", "Ertalab"), ("afternoon", "Kunduzi"), ("evening", "Kechqurun"))
# Errors after which the customer should simply pick another time on the picker.
RETRY_TIME_CODES = {
    "SLOT_TAKEN",
    "SLOT_UNAVAILABLE",
    "IN_PAST",
    "LEAD_TIME",
    "TOO_FAR_AHEAD",
    "STEP_MISALIGNED",
    "CUSTOMER_OVERLAP",
}


def _service_or_404(slug):
    service = catalog_selectors.service_by_slug(slug=slug)
    if service is None:
        raise Http404
    return service


def _provider_for(service, raw_id):
    try:
        provider_id = uuid.UUID(str(raw_id))
    except ValueError:
        return None
    return provider_selectors.provider_list(service_id=service.pk).filter(pk=provider_id).first()


def _step_url(service, **params) -> str:
    base = reverse("web:book", args=[service.slug])
    params = {k: v for k, v in params.items() if v not in (None, "")}
    return f"{base}?{urlencode(params)}" if params else base


def _today(tz: str) -> date:
    return timezone.now().astimezone(ZoneInfo(tz)).date()


def book(request, slug):
    service = _service_or_404(slug)
    provider = (
        _provider_for(service, request.GET.get("provider")) if "provider" in request.GET else None
    )
    if provider is None:
        return _choose_provider(request, service)
    if request.GET.get("start"):
        return _confirm(request, service, provider)
    return _choose_time(request, service, provider)


def _choose_provider(request, service):
    providers = provider_selectors.provider_list(service_id=service.pk)
    return render(
        request,
        "web/book_provider.html",
        {
            "service": service,
            "providers": providers,
            "step": 1,
            "booking_steps": BOOKING_STEPS,
            "back_url": reverse("web:home"),
        },
    )


def _time_context(request, service, provider) -> dict:
    tz = request.display_tz
    now = timezone.now()
    business = BusinessSettings.load()
    today = _today(tz)
    last_day = today + timedelta(days=business.max_advance_days)

    selected = parse_date(request.GET.get("date") or "") or None
    week = parse_date(request.GET.get("week") or "") or selected or today
    week = min(max(week, today), last_day)

    counts = scheduling_selectors.days_summary(
        service=service,
        provider=provider,
        date_from=week,
        date_to=week + timedelta(days=STRIP_DAYS - 1),
        tz=tz,
        now=now,
    )
    if selected is None or not week <= selected < week + timedelta(days=STRIP_DAYS):
        selected = next((d for d, n in counts if n), week)

    slots = scheduling_selectors.day_slots(
        service=service, provider=provider, date_local=selected, tz=tz, now=now
    )
    zone = ZoneInfo(tz)
    groups = {key: [] for key, _ in DAY_PARTS}
    for slot in slots:
        local_start = slot.start_at.astimezone(zone)
        groups[text.day_part(local_start)].append(
            {
                "value": slot.start_at.isoformat().replace("+00:00", "Z"),
                "label": local_start.strftime("%H:%M"),
            }
        )

    next_free = None
    if not slots:
        horizon = min(selected + timedelta(days=30), last_day)
        if selected < horizon:
            ahead = scheduling_selectors.days_summary(
                service=service,
                provider=provider,
                date_from=selected + timedelta(days=1),
                date_to=horizon,
                tz=tz,
                now=now,
            )
            next_free = next((d for d, n in ahead if n), None)

    prev_week = week - timedelta(days=STRIP_DAYS)
    next_week = week + timedelta(days=STRIP_DAYS)
    return {
        "service": service,
        "provider": provider,
        "step": 2,
        "booking_steps": BOOKING_STEPS,
        "back_url": _step_url(service),
        "tz": tz,
        "days": [
            {
                "date": d,
                "count": n,
                "url": _step_url(service, provider=provider.pk, week=week, date=d),
            }
            for d, n in counts
        ],
        "selected": selected,
        "groups": [(label, groups[key]) for key, label in DAY_PARTS],
        "has_slots": bool(slots),
        "next_free": next_free,
        "next_free_url": next_free
        and _step_url(service, provider=provider.pk, week=next_free, date=next_free),
        "prev_week_url": _step_url(service, provider=provider.pk, week=prev_week)
        if week > today
        else None,
        "next_week_url": _step_url(service, provider=provider.pk, week=next_week)
        if next_week <= last_day
        else None,
    }


def _choose_time(request, service, provider):
    context = _time_context(request, service, provider)
    # HTMX swaps only the picker when a day or week is chosen; a full load renders the page.
    template = (
        "web/partials/time_picker.html"
        if request.headers.get("HX-Request")
        else "web/book_time.html"
    )
    return render(request, template, context)


def _require_customer(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('web:login')}?{urlencode({'next': request.get_full_path()})}")
    if request.user.role != User.Role.CUSTOMER:
        messages.error(request, "Bron faqat mijoz akkaunti bilan qilinadi.")
        return redirect("web:home")
    return None


def _confirm(request, service, provider):
    blocked = _require_customer(request)
    if blocked:
        return blocked
    start_at = parse_datetime(request.GET["start"])
    if start_at is None or timezone.is_naive(start_at):
        return redirect(_step_url(service, provider=provider.pk))
    tz = request.display_tz
    local_date = start_at.astimezone(ZoneInfo(tz)).date()
    available = {
        s.start_at
        for s in scheduling_selectors.day_slots(
            service=service, provider=provider, date_local=local_date, tz=tz, now=timezone.now()
        )
    }
    if start_at not in available:
        messages.error(request, "Bu vaqt endi boʻsh emas. Boshqa vaqtni tanlang.")
        return redirect(_step_url(service, provider=provider.pk, week=local_date, date=local_date))
    form = BookingConfirmForm(
        initial={
            "provider": provider.pk,
            "start_at": request.GET["start"],
            "idempotency_key": uuid.uuid4().hex,
        }
    )
    return _render_confirm(request, service, provider, start_at, form)


def _render_confirm(request, service, provider, start_at, form, status=200):
    return render(
        request,
        "web/book_confirm.html",
        {
            "service": service,
            "provider": provider,
            "step": 3,
            "booking_steps": BOOKING_STEPS,
            "start_at": start_at,
            "end_at": start_at + timedelta(minutes=service.duration_minutes),
            "form": form,
            "back_url": _step_url(service, provider=provider.pk),
        },
        status=status,
    )


@require_POST
def confirm(request, slug):
    service = _service_or_404(slug)
    blocked = _require_customer(request)
    if blocked:
        return blocked
    form = BookingConfirmForm(request.POST)
    if not form.is_valid():
        provider = _provider_for(service, request.POST.get("provider"))
        if provider is None:
            return redirect(_step_url(service))
        return redirect(_step_url(service, provider=provider.pk))
    data = form.cleaned_data
    try:
        result = booking_services.create_booking(
            customer=request.user,
            service_id=service.pk,
            provider_id=data["provider"],
            start_at=data["start_at"],
            note=data["note"],
            idempotency_key=data["idempotency_key"],
        )
    except DomainError as exc:
        local_date = data["start_at"].astimezone(ZoneInfo(request.display_tz)).date()
        if exc.code == "SLOT_TAKEN":
            messages.error(request, "Bu vaqt hozirgina band qilindi. Boshqa vaqtni tanlang.")
        else:
            messages.error(request, exc.message)
        if exc.code in RETRY_TIME_CODES:
            return redirect(
                _step_url(service, provider=data["provider"], week=local_date, date=local_date)
            )
        return redirect("web:home")
    return redirect("web:book_done", slug=service.slug, booking_id=result.booking.pk)


def done(request, slug, booking_id):
    if not request.user.is_authenticated:
        return redirect("web:login")
    booking = booking_selectors.visible_booking(request.user, booking_id)
    if booking is None:
        raise Http404
    return render(
        request, "web/book_done.html", {"booking": booking, "service": booking.service, "step": 4}
    )
