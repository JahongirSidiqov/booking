"""Weekly availability editor, time off, and business settings."""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.common.exceptions import DomainError
from apps.providers import selectors as provider_selectors
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling import services as scheduling_services
from apps.scheduling.models import AvailabilityRule, BusinessSettings
from apps.web import text
from apps.web.access import admin_required, can_manage, forbidden, own_provider, staff_required
from apps.web.forms_dashboard import RuleForm, SettingsForm, TimeOffForm

WEEKDAYS = AvailabilityRule.Weekday.choices


def _managed_provider(request, provider_id):
    provider = provider_selectors.provider_get(pk=provider_id, include_inactive=True)
    if provider is None:
        raise Http404
    if not can_manage(request.user, provider):
        return None
    return provider


def _rows_from_db(provider) -> dict[int, list[dict]]:
    rows = {day: [] for day, _ in WEEKDAYS}
    for rule in scheduling_selectors.availability_rules(provider=provider):
        rows[rule.weekday].append(
            {"start": rule.start_time.strftime("%H:%M"), "end": rule.end_time.strftime("%H:%M")}
        )
    return rows


def _rows_from_post(post) -> dict[int, list[dict]]:
    rows = {}
    for day, _ in WEEKDAYS:
        starts, ends = post.getlist(f"start_{day}"), post.getlist(f"end_{day}")
        rows[day] = [{"start": s, "end": e} for s, e in zip(starts, ends, strict=False) if s or e]
    return rows


def _parse_rules(rows) -> tuple[list[dict], list[str]]:
    rules, errors = [], []
    labels = dict(WEEKDAYS)
    for day, windows in rows.items():
        for window in windows:
            form = RuleForm(
                {"weekday": day, "start_time": window["start"], "end_time": window["end"]}
            )
            if form.is_valid():
                rules.append(form.cleaned_data)
            else:
                message = form.non_field_errors() or ["Vaqtni HH:MM koʻrinishida kiriting."]
                errors.append(
                    f"{labels[day]} {window['start'] or '—'}–{window['end'] or '—'}: {message[0]}"
                )
    return rules, errors


def _local_label(moment, tz: str) -> str:
    local = text.local(moment, tz)
    return f"{text.short_day(local.date())}, {local:%H:%M}"


def _render(
    request, provider, *, rows=None, rule_errors=(), conflicts=(), time_off_form=None, status=200
):
    business = BusinessSettings.load()
    tz = scheduling_selectors.provider_timezone(provider, business)
    rows = rows or _rows_from_db(provider)
    conflicts = [{**c, "when": _local_label(parse_datetime(c["start_at"]), tz)} for c in conflicts]
    return render(
        request,
        "dashboard/availability.html",
        {
            "nav": "providers" if request.user.role == User.Role.ADMIN else "availability",
            "provider": provider,
            "provider_tz": tz,
            "weekdays": WEEKDAYS,
            "rows": {str(k): v for k, v in rows.items()},
            "rule_errors": rule_errors,
            "conflicts": conflicts,
            "time_offs": scheduling_selectors.time_off_list(provider=provider, now=timezone.now()),
            "time_off_form": time_off_form or TimeOffForm(tz=tz),
        },
        status=status,
    )


@staff_required
def my_availability(request):
    provider = own_provider(request.user)
    if provider is None:
        return forbidden(
            request,
            "Akkauntingiz hali xodim profiliga bogʻlanmagan. Administratorga murojaat qiling.",
        )
    return redirect("web:dashboard_availability", provider_id=provider.pk)


@staff_required
def availability(request, provider_id):
    provider = _managed_provider(request, provider_id)
    if provider is None:
        return forbidden(request, "Faqat oʻz ish vaqtingizni boshqara olasiz.")
    if request.method != "POST":
        return _render(request, provider)

    rows = _rows_from_post(request.POST)
    rules, errors = _parse_rules(rows)
    if errors:
        return _render(request, provider, rows=rows, rule_errors=errors, status=422)
    try:
        scheduling_services.replace_availability(provider=provider, rules=rules)
    except DomainError as exc:
        return _render(
            request,
            provider,
            rows=rows,
            rule_errors=(exc.errors or {}).get("rules", [])
            if exc.code == "VALIDATION_ERROR"
            else [],
            conflicts=exc.extra.get("bookings", [])
            if exc.code == "CONFLICTS_WITH_BOOKINGS"
            else [],
            status=exc.http_status,
        )
    messages.success(request, "Ish vaqti saqlandi.")
    return redirect("web:dashboard_availability", provider_id=provider.pk)


@staff_required
@require_POST
def time_off_add(request, provider_id):
    provider = _managed_provider(request, provider_id)
    if provider is None:
        return forbidden(request, "Faqat oʻz ish vaqtingizni boshqara olasiz.")
    tz = scheduling_selectors.provider_timezone(provider, BusinessSettings.load())
    form = TimeOffForm(request.POST, tz=tz)
    if not form.is_valid():
        return _render(request, provider, time_off_form=form, status=422)
    try:
        scheduling_services.add_time_off(provider=provider, **form.cleaned_data)
    except DomainError as exc:
        return _render(
            request,
            provider,
            time_off_form=form,
            conflicts=exc.extra.get("bookings", []),
            status=exc.http_status,
        )
    messages.success(request, "Dam olish qoʻshildi.")
    return redirect("web:dashboard_availability", provider_id=provider.pk)


@staff_required
@require_POST
def time_off_delete(request, provider_id, time_off_id):
    provider = _managed_provider(request, provider_id)
    if provider is None:
        return forbidden(request, "Faqat oʻz ish vaqtingizni boshqara olasiz.")
    try:
        scheduling_services.delete_time_off(provider=provider, time_off_id=time_off_id)
    except DomainError as exc:
        raise Http404 from exc
    messages.success(request, "Dam olish oʻchirildi.")
    return redirect("web:dashboard_availability", provider_id=provider.pk)


@admin_required
def settings_view(request):
    business = BusinessSettings.load()
    form = SettingsForm(
        request.POST or None,
        initial={
            "name": business.name,
            "timezone": business.timezone,
            "currency": business.currency,
            "slot_step_minutes": business.slot_step_minutes,
            "min_lead_time_minutes": business.min_lead_time_minutes,
            "max_advance_days": business.max_advance_days,
            "cancellation_deadline_hours": business.cancellation_deadline_hours,
            "auto_confirm": business.auto_confirm,
        },
    )
    if request.method == "POST" and form.is_valid():
        scheduling_services.update_settings(**form.cleaned_data)
        messages.success(request, "Sozlamalar saqlandi.")
        return redirect("web:dashboard_settings")
    return render(request, "dashboard/settings.html", {"nav": "settings", "form": form})
