"""Booking write operations. The only module allowed to change Booking.status."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.common.exceptions import DomainError
from apps.providers.models import Provider
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling import slot_engine

from . import selectors
from .models import Booking, BookingStatusHistory

SLOT_ERRORS = {
    "IN_PAST": ("Tanlangan vaqt oʻtib ketgan.", 422, "Vaqt oʻtib ketgan"),
    "LEAD_TIME": ("Bu vaqtga bron qilish uchun juda kech.", 422, "Juda yaqin vaqt"),
    "TOO_FAR_AHEAD": ("Bu sana hali bron uchun ochilmagan.", 422, "Juda uzoq sana"),
    "STEP_MISALIGNED": (
        "Vaqt jadval qadamiga mos emas (masalan 10:00, 10:15).",
        422,
        "Notoʻgʻri vaqt",
    ),
    "SLOT_UNAVAILABLE": ("Xodim bu vaqtda ishlamaydi.", 422, "Vaqt mavjud emas"),
    "SLOT_TAKEN": (
        "Tanlangan vaqt boshqa mijoz tomonidan band qilindi. Boshqa vaqtni tanlang.",
        409,
        "Bu vaqt band",
    ),
    "CUSTOMER_OVERLAP": ("Sizda shu vaqtga boshqa bron bor.", 409, "Vaqtingiz band"),
}

CONSTRAINT_ERRORS = {
    "no_overlap_per_provider": "SLOT_TAKEN",
    "no_overlap_per_customer": "CUSTOMER_OVERLAP",
}


@dataclass(frozen=True)
class CreateResult:
    booking: Booking
    replayed: bool


def slot_error(code: str) -> DomainError:
    message, status, title = SLOT_ERRORS[code]
    return DomainError(code, message, status, title=title)


def constraint_error_code(exc: IntegrityError) -> str | None:
    """Map a violated exclusion constraint to its domain error code (None if unrelated)."""
    return CONSTRAINT_ERRORS.get(_constraint_name(exc))


def fingerprint(*, service_id, provider_id, start_at: datetime, note: str) -> str:
    raw = f"{service_id}|{provider_id}|{start_at.astimezone(UTC).isoformat()}|{note}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def _lock_provider(provider_id) -> Provider | None:
    # Serialises every booking for one provider: a racing request waits here, then sees the
    # winner's committed row and gets a friendly 409 instead of an IntegrityError.
    # Only this provider's row is locked, so bookings for other providers run in parallel.
    return Provider.objects.select_for_update().filter(pk=provider_id).first()


def _record(booking: Booking, from_status, to_status, actor, reason: str = "") -> None:
    BookingStatusHistory.objects.create(
        booking=booking,
        from_status=from_status,
        to_status=to_status,
        changed_by=actor,
        reason=reason,
    )


def _replay(customer: User, key: str | None, payload_hash: str) -> CreateResult | None:
    existing = Booking.objects.filter(customer=customer, idempotency_key=key).first()
    if existing is None:
        return None
    if existing.idempotency_fingerprint != payload_hash:
        raise DomainError(
            "IDEMPOTENCY_MISMATCH",
            "Bu Idempotency-Key boshqa soʻrov uchun ishlatilgan.",
            409,
            title="Idempotency kaliti mos emas",
        )
    return CreateResult(existing, replayed=True)


def create_booking(
    *,
    customer: User,
    service_id,
    provider_id,
    start_at: datetime,
    note: str = "",
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> CreateResult:
    now = now or timezone.now()
    payload_hash = fingerprint(
        service_id=service_id, provider_id=provider_id, start_at=start_at, note=note
    )
    try:
        with transaction.atomic():
            return _create_locked(
                customer=customer,
                service_id=service_id,
                provider_id=provider_id,
                start_at=start_at,
                note=note,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                now=now,
            )
    except IntegrityError as exc:
        # Reached only when a write slipped past the provider lock (e.g. the same customer
        # booking two different providers at once): the constraints decide, we translate.
        code = constraint_error_code(exc)
        if code:
            raise slot_error(code) from exc
        if _constraint_name(exc) == "uniq_idempotency_per_customer":
            replay = _replay(customer, idempotency_key, payload_hash)
            if replay is not None:
                return replay
        raise


def _create_locked(
    *, customer, service_id, provider_id, start_at, note, idempotency_key, payload_hash, now
) -> CreateResult:
    if _lock_provider(provider_id) is None:
        raise DomainError("NOT_FOUND", "Xizmat yoki xodim topilmadi.", 404)

    # Checked under the lock: a double-click's second request waits for the first to commit
    # and then finds its booking here, instead of reporting its own slot as taken.
    if idempotency_key:
        replay = _replay(customer, idempotency_key, payload_hash)
        if replay is not None:
            return replay

    service, provider = scheduling_selectors.bookable_pair(
        service_id=service_id, provider_id=provider_id
    )
    utc_day = start_at.astimezone(UTC).date()
    inputs = scheduling_selectors.engine_inputs(provider, utc_day, utc_day)
    reason = slot_engine.slot_rejection(
        service=service, provider=provider, start_at=start_at, now=now, **inputs
    )
    if reason:
        raise slot_error(reason)

    end_at = start_at + timedelta(minutes=service.duration_minutes)
    if selectors.customer_has_overlap(customer=customer, start=start_at, end=end_at):
        raise slot_error("CUSTOMER_OVERLAP")

    booking = Booking.objects.create(
        customer=customer,
        provider=provider,
        service=service,
        start_at=start_at,
        end_at=end_at,
        status=Booking.Status.PENDING,
        service_name=service.name,
        duration_minutes=service.duration_minutes,
        price=service.price,
        customer_note=note,
        idempotency_key=idempotency_key or None,
        idempotency_fingerprint=payload_hash if idempotency_key else "",
    )
    _record(booking, None, Booking.Status.PENDING, customer)
    if inputs["settings"].auto_confirm:
        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=["status", "updated_at"])
        _record(booking, Booking.Status.PENDING, Booking.Status.CONFIRMED, None, "auto_confirm")
    return CreateResult(booking, replayed=False)
