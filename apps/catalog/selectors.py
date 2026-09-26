from django.db.models import QuerySet

from .models import Service


def service_list(*, include_inactive: bool = False) -> QuerySet[Service]:
    qs = Service.objects.all()
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return qs.order_by("sort_order", "name")


def service_get(*, pk, include_inactive: bool = False) -> Service | None:
    return service_list(include_inactive=include_inactive).filter(pk=pk).first()


def service_by_slug(*, slug: str) -> Service | None:
    return service_list().filter(slug=slug).first()
