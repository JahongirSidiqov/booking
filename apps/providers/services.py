from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.catalog.models import Service
from apps.common.exceptions import DomainError

from .models import Provider, ProviderService

PROVIDER_FIELDS = frozenset({"name", "bio", "color", "is_active", "timezone"})


def _invalid(field: str, message: str) -> DomainError:
    return DomainError(
        "VALIDATION_ERROR", "Kiritilgan maʼlumotlarni tekshiring.", errors={field: [message]}
    )


def _resolve_user(user_id, *, provider: Provider | None = None) -> User | None:
    if user_id is None:
        return None
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise _invalid("user_id", "Foydalanuvchi topilmadi.")
    if user.role != User.Role.PROVIDER:
        raise _invalid("user_id", "Faqat 'provider' rolidagi foydalanuvchini bogʻlash mumkin.")
    linked = Provider.objects.filter(user=user)
    if provider is not None:
        linked = linked.exclude(pk=provider.pk)
    if linked.exists():
        raise _invalid("user_id", "Bu foydalanuvchi boshqa xodimga bogʻlangan.")
    return user


def _resolve_services(service_ids) -> list[Service]:
    ids = list(dict.fromkeys(service_ids))
    found = {s.pk: s for s in Service.objects.filter(pk__in=ids)}
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise _invalid("service_ids", f"Xizmat topilmadi: {', '.join(missing)}")
    return [found[i] for i in ids]


@transaction.atomic
def create_provider(*, service_ids=None, user_id=None, **data) -> Provider:
    fields = {k: v for k, v in data.items() if k in PROVIDER_FIELDS}
    fields["user"] = _resolve_user(user_id)
    try:
        with transaction.atomic():
            provider = Provider.objects.create(**fields)
    except IntegrityError as exc:
        raise _invalid("user_id", "Bu foydalanuvchi boshqa xodimga bogʻlangan.") from exc
    if service_ids:
        _replace_services(provider, _resolve_services(service_ids))
    return provider


@transaction.atomic
def update_provider(*, provider: Provider, **data) -> Provider:
    changed = [k for k in data if k in PROVIDER_FIELDS]
    if "user_id" in data:
        provider.user = _resolve_user(data["user_id"], provider=provider)
        changed.append("user")
    for name in (c for c in changed if c != "user"):
        setattr(provider, name, data[name])
    if changed:
        provider.save(update_fields=[*changed, "updated_at"])
    return provider


def deactivate_provider(*, provider: Provider) -> Provider:
    # Existing bookings stay as they are; only new bookings become impossible.
    if provider.is_active:
        provider.is_active = False
        provider.save(update_fields=["is_active", "updated_at"])
    return provider


@transaction.atomic
def set_provider_services(*, provider: Provider, service_ids) -> Provider:
    _replace_services(provider, _resolve_services(service_ids))
    return provider


def _replace_services(provider: Provider, services: list[Service]) -> None:
    wanted = {s.pk for s in services}
    ProviderService.objects.filter(provider=provider).exclude(service_id__in=wanted).delete()
    existing = set(
        ProviderService.objects.filter(provider=provider).values_list("service_id", flat=True)
    )
    ProviderService.objects.bulk_create(
        [ProviderService(provider=provider, service_id=pk) for pk in wanted - existing]
    )
