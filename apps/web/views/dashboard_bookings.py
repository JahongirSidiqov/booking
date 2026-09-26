import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.bookings import selectors as booking_selectors
from apps.bookings import services as booking_services
from apps.bookings import state_machine
from apps.bookings.models import Booking
from apps.common.exceptions import DomainError
from apps.providers.models import Provider
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling.models import BusinessSettings
from apps.scheduling.slot_engine import local_day_bounds, merge, rule_windows
from apps.web.access import own_provider, staff_required
from apps.web.forms_dashboard import BookingFilterForm, StaffCancelForm

DEFAULT_AXIS = (9, 19)  # TASK 10.3: the day view shows at least 09:00–19:00
HOUR_PX = 64
ACTIONS = {
    "confirm": Booking.Status.CONFIRMED,
    "complete": Booking.Status.COMPLETED,
    "cancel": Booking.Status.CANCELLED,
}
ACTION_LABELS = {
    Booking.Status.CONFIRMED: "Bronni tasdiqlash",
    Booking.Status.COMPLETED: "Bajarildi deb belgilash",
    Booking.Status.CANCELLED: "Bronni bekor qilish",
}


def css_percent(value: float) -> str:
    # Formatted here, not in the template: with LANGUAGE_CODE="uz" Django would render the
    # float as "69,231" and the browser silently drops the whole CSS declaration.
    return f"{value:.3f}%"


def _visible_providers(user: User):
    if user.role == User.Role.ADMIN:
        return list(Provider.objects.filter(is_active=True).order_by("name"))
    mine = own_provider(user)
    return [mine] if mine else []


def _hour(moment: datetime, zone: ZoneInfo) -> float:
    local = moment.astimezone(zone)
    return local.hour + local.minute / 60


@staff_required
def today(request):
    tz = request.display_tz
    zone = ZoneInfo(tz)
    now = timezone.now()
    today_local = now.astimezone(zone).date()
    day = parse_date(request.GET.get("date") or "") or today_local
    start, end = local_day_bounds(day, tz)

    providers = _visible_providers(request.user)
    visible = booking_selectors.visible_bookings(request.user)
    day_qs = booking_selectors.overlapping(visible, start=start, end=end)
    kpis = booking_selectors.day_kpis(day_qs)
    bookings = list(day_qs.exclude(status=Booking.Status.CANCELLED).order_by("start_at"))

    business = BusinessSettings.load()
    windows_by_provider = {}
    first, last = DEFAULT_AXIS
    for provider in providers:
        provider_tz = scheduling_selectors.provider_timezone(provider, business)
        rules = scheduling_selectors.availability_rules(provider=provider)
        # Rules are provider-local; the viewer may be in another zone, so both provider
        # dates touching the viewer's day are converted and clipped to it.
        windows = []
        for offset in (-1, 0, 1):
            windows += rule_windows(rules, day + timedelta(days=offset), provider_tz)
        windows = [(max(s, start), min(e, end)) for s, e in merge(windows) if s < end and e > start]
        windows_by_provider[provider.pk] = windows
        for s, e in windows:
            first = min(first, int(_hour(s, zone)))
            last = max(last, math.ceil(_hour(e, zone)) if e < end else 24)
    for booking in bookings:
        first = min(first, int(_hour(max(booking.start_at, start), zone)))
        until = booking.blocked_until
        last = max(last, 24 if until >= end else math.ceil(_hour(until, zone)))

    span = last - first

    def position(s, e):
        top = (_hour(max(s, start), zone) - first) / span * 100
        bottom = (24 if e >= end else _hour(e, zone)) - first
        return {"top": css_percent(top), "height": css_percent(bottom / span * 100 - top)}

    columns = []
    for provider in providers:
        columns.append(
            {
                "provider": provider,
                "windows": [position(s, e) for s, e in windows_by_provider[provider.pk]],
                "blocks": [
                    {
                        "booking": b,
                        **position(b.start_at, b.end_at),
                        "buffer": position(b.end_at, b.blocked_until)
                        if b.blocked_until > b.end_at
                        else None,
                    }
                    for b in bookings
                    if b.provider_id == provider.pk
                ],
            }
        )

    now_line = None
    if day == today_local and first <= _hour(now, zone) < last:
        now_line = css_percent((_hour(now, zone) - first) / span * 100)

    return render(
        request,
        "dashboard/today.html",
        {
            "nav": "today",
            "day": day,
            "is_today": day == today_local,
            "prev_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1),
            "kpis": kpis,
            "columns": columns,
            "hours": list(range(first, last)),
            "axis_px": span * HOUR_PX,
            "now_line": now_line,
            "unlinked": request.user.role == User.Role.PROVIDER and not providers,
        },
    )


@staff_required
def booking_list(request):
    is_admin = request.user.role == User.Role.ADMIN
    providers = list(Provider.objects.order_by("name")) if is_admin else []
    form = BookingFilterForm(request.GET or None, providers=providers)
    filters = form.cleaned_data if form.is_valid() else {}
    tz = request.display_tz

    starts_from = (
        local_day_bounds(filters["date_from"], tz)[0] if filters.get("date_from") else None
    )
    starts_before = local_day_bounds(filters["date_to"], tz)[1] if filters.get("date_to") else None
    bookings = booking_selectors.filter_bookings(
        booking_selectors.visible_bookings(request.user),
        statuses=[filters["status"]] if filters.get("status") else None,
        provider_id=filters.get("provider") or None,
        starts_from=starts_from,
        starts_before=starts_before,
        search=(filters.get("q") or "").strip(),
    )
    page = Paginator(bookings, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "dashboard/bookings.html",
        {
            "nav": "bookings",
            "form": form,
            "page": page,
            "query": query.urlencode(),
            "is_admin": is_admin,
            "filtered": any(filters.values()) if filters else False,
            "list_url": request.get_full_path(),
        },
    )


def _context_for(booking: Booking, user: User) -> state_machine.Context:
    return state_machine.Context(
        status=booking.status,
        start_at=booking.start_at,
        actor_role=user.role,
        now=timezone.now(),
        cancellation_deadline_hours=BusinessSettings.load().cancellation_deadline_hours,
    )


@staff_required
def booking_detail(request, booking_id):
    booking = booking_selectors.visible_booking(request.user, booking_id)
    if booking is None:
        raise Http404
    targets = state_machine.available_targets(_context_for(booking, request.user))
    back = request.GET.get("back", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = ""
    return render(
        request,
        "dashboard/booking_detail.html",
        {
            "nav": "bookings",
            "booking": booking,
            "history": booking.history.all(),
            "can_confirm": Booking.Status.CONFIRMED in targets,
            "can_complete": Booking.Status.COMPLETED in targets,
            "can_cancel": Booking.Status.CANCELLED in targets,
            "cancel_form": StaffCancelForm(),
            "back": back,
        },
    )


@staff_required
@require_POST
def booking_action(request, booking_id, action):
    to_status = ACTIONS.get(action)
    if to_status is None:
        raise Http404
    reason = ""
    if to_status == Booking.Status.CANCELLED:
        form = StaffCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Bekor qilish sababini yozing.")
            return redirect("web:dashboard_booking", booking_id=booking_id)
        reason = form.cleaned_data["reason"]
    try:
        booking_services.transition_booking(
            booking_id=booking_id, to_status=to_status, actor=request.user, reason=reason
        )
    except DomainError as exc:
        if exc.code == "NOT_FOUND":
            raise Http404 from exc
        messages.error(request, exc.message)
    else:
        messages.success(request, f"{ACTION_LABELS[to_status]}: bajarildi.")
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("web:dashboard_booking", booking_id=booking_id)
