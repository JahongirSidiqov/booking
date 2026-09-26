from django.db.models import Prefetch, QuerySet

from apps.catalog.models import Service

from .models import Provider


def provider_list(*, service_id=None, include_inactive: bool = False) -> QuerySet[Provider]:
    services_qs = Service.objects.order_by("sort_order", "name")
    if not include_inactive:
        services_qs = services_qs.filter(is_active=True)
    qs = Provider.objects.prefetch_related(Prefetch("services", queryset=services_qs))
    if not include_inactive:
        qs = qs.filter(is_active=True)
    if service_id is not None:
        offering = {"offerings__service_id": service_id}
        if not include_inactive:
            offering["offerings__service__is_active"] = True
        qs = qs.filter(**offering)
    return qs.order_by("name").distinct()


def provider_get(*, pk, include_inactive: bool = False) -> Provider | None:
    return provider_list(include_inactive=include_inactive).filter(pk=pk).first()
