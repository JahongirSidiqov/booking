"""Admin screens for services and providers: list + modal form (?new=1 / ?edit=<id>)."""

import uuid

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.bookings import selectors as booking_selectors
from apps.catalog import selectors as catalog_selectors
from apps.catalog import services as catalog_services
from apps.catalog.models import Service
from apps.common.exceptions import DomainError
from apps.providers import selectors as provider_selectors
from apps.providers import services as provider_services
from apps.providers.models import Provider
from apps.web.access import admin_required
from apps.web.forms_dashboard import ProviderForm, ServiceForm


def _uuid_or_none(raw):
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _apply_domain_errors(form, exc: DomainError):
    for field, errors in (exc.errors or {}).items():
        target = {"service_ids": "services", "user_id": "user"}.get(field, field)
        for error in errors:
            form.add_error(target if target in form.fields else None, error)
    if not exc.errors:
        form.add_error(None, exc.message)


# --- services -----------------------------------------------------------------------------


def _service_initial(service: Service) -> dict:
    return {
        "name": service.name,
        "slug": service.slug,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price": service.price,
        "sort_order": service.sort_order,
        "is_active": service.is_active,
    }


@admin_required
def services(request):
    editing = None
    if request.GET.get("edit"):
        editing = catalog_selectors.service_get(
            pk=_uuid_or_none(request.GET["edit"]), include_inactive=True
        )
        if editing is None:
            raise Http404
    show_form = bool(editing) or "new" in request.GET or request.method == "POST"

    form = ServiceForm(
        request.POST or None,
        initial=_service_initial(editing)
        if editing
        else {"is_active": True, "duration_minutes": 30},
    )
    if request.method == "POST" and form.is_valid():
        try:
            if editing:
                catalog_services.update_service(service=editing, **form.cleaned_data)
                messages.success(request, "Xizmat saqlandi.")
            else:
                catalog_services.create_service(**form.cleaned_data)
                messages.success(request, "Xizmat qoʻshildi.")
        except DomainError as exc:
            _apply_domain_errors(form, exc)
        else:
            return redirect("web:dashboard_services")

    upcoming = booking_selectors.upcoming_counts("service_id", now=timezone.now())
    rows = [
        {"service": s, "upcoming": upcoming.get(s.pk, 0)}
        for s in catalog_selectors.service_list(include_inactive=True)
    ]
    return render(
        request,
        "dashboard/services.html",
        {
            "nav": "services",
            "rows": rows,
            "form": form,
            "show_form": show_form,
            "editing": editing,
        },
    )


@admin_required
@require_POST
def service_deactivate(request, service_id):
    service = catalog_selectors.service_get(pk=service_id, include_inactive=True)
    if service is None:
        raise Http404
    catalog_services.deactivate_service(service=service)
    kept = booking_selectors.upcoming_active(now=timezone.now(), service=service).count()
    messages.success(
        request,
        f"«{service.name}» nofaol qilindi. {kept} ta kelgusi bron saqlanib qoldi."
        if kept
        else f"«{service.name}» nofaol qilindi.",
    )
    return redirect("web:dashboard_services")


# --- providers ----------------------------------------------------------------------------


def _provider_initial(provider: Provider) -> dict:
    return {
        "name": provider.name,
        "bio": provider.bio,
        "color": provider.color,
        "timezone": provider.timezone or "",
        "user": provider.user_id,
        "services": list(provider.services.all()),
        "is_active": provider.is_active,
    }


@admin_required
def providers(request):
    editing = None
    if request.GET.get("edit"):
        editing = provider_selectors.provider_get(
            pk=_uuid_or_none(request.GET["edit"]), include_inactive=True
        )
        if editing is None:
            raise Http404
    show_form = bool(editing) or "new" in request.GET or request.method == "POST"

    form = ProviderForm(
        request.POST or None,
        provider=editing,
        initial=_provider_initial(editing) if editing else {"is_active": True, "color": "#2563EB"},
    )
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        service_ids = [s.pk for s in data.pop("services")]
        user = data.pop("user")
        data["timezone"] = data["timezone"] or None
        try:
            if editing:
                provider_services.update_provider(
                    provider=editing, user_id=user.pk if user else None, **data
                )
                provider_services.set_provider_services(provider=editing, service_ids=service_ids)
                messages.success(request, "Xodim saqlandi.")
            else:
                provider_services.create_provider(
                    service_ids=service_ids, user_id=user.pk if user else None, **data
                )
                messages.success(request, "Xodim qoʻshildi.")
        except DomainError as exc:
            _apply_domain_errors(form, exc)
        else:
            return redirect("web:dashboard_providers")

    upcoming = booking_selectors.upcoming_counts("provider_id", now=timezone.now())
    rows = [
        {"provider": p, "upcoming": upcoming.get(p.pk, 0)}
        for p in provider_selectors.provider_list(include_inactive=True).select_related("user")
    ]
    return render(
        request,
        "dashboard/providers.html",
        {
            "nav": "providers",
            "rows": rows,
            "form": form,
            "show_form": show_form,
            "editing": editing,
        },
    )


@admin_required
@require_POST
def provider_deactivate(request, provider_id):
    provider = provider_selectors.provider_get(pk=provider_id, include_inactive=True)
    if provider is None:
        raise Http404
    provider_services.deactivate_provider(provider=provider)
    kept = booking_selectors.upcoming_active(now=timezone.now(), provider=provider).count()
    messages.success(
        request,
        f"«{provider.name}» nofaol qilindi. {kept} ta kelgusi bron saqlanib qoldi."
        if kept
        else f"«{provider.name}» nofaol qilindi.",
    )
    return redirect("web:dashboard_providers")
