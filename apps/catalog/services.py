from django.db import IntegrityError, transaction
from django.utils.text import slugify

from apps.common.exceptions import DomainError

from .models import Service

SERVICE_FIELDS = frozenset(
    {
        "name",
        "slug",
        "description",
        "duration_minutes",
        "price",
        "buffer_after_minutes",
        "is_active",
        "sort_order",
    }
)


def _slug_taken_error() -> DomainError:
    return DomainError(
        "VALIDATION_ERROR",
        "Kiritilgan maʼlumotlarni tekshiring.",
        errors={"slug": ["Bu slug band. Boshqasini tanlang."]},
    )


def _unique_slug(name: str, *, exclude_pk=None) -> str:
    # slugify drops ʻ/ʼ, so "Soqol oʻldirish" becomes "soqol-oldirish".
    base = slugify(name)[:110] or "xizmat"
    taken = set(
        Service.objects.filter(slug__startswith=base)
        .exclude(pk=exclude_pk)
        .values_list("slug", flat=True)
    )
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def create_service(**data) -> Service:
    fields = {k: v for k, v in data.items() if k in SERVICE_FIELDS}
    if not fields.get("slug"):
        fields["slug"] = _unique_slug(fields["name"])
    elif Service.objects.filter(slug=fields["slug"]).exists():
        raise _slug_taken_error()
    try:
        with transaction.atomic():
            return Service.objects.create(**fields)
    except IntegrityError as exc:
        raise _slug_taken_error() from exc


def update_service(*, service: Service, **data) -> Service:
    # Changing duration/price affects only future bookings: bookings keep a snapshot.
    changed = [k for k in data if k in SERVICE_FIELDS]
    if "slug" in changed:
        if not data["slug"]:
            data["slug"] = _unique_slug(data.get("name", service.name), exclude_pk=service.pk)
        elif Service.objects.filter(slug=data["slug"]).exclude(pk=service.pk).exists():
            raise _slug_taken_error()
    for name in changed:
        setattr(service, name, data[name])
    if changed:
        try:
            with transaction.atomic():
                service.save(update_fields=[*changed, "updated_at"])
        except IntegrityError as exc:
            raise _slug_taken_error() from exc
    return service


def deactivate_service(*, service: Service) -> Service:
    if service.is_active:
        service.is_active = False
        service.save(update_fields=["is_active", "updated_at"])
    return service
