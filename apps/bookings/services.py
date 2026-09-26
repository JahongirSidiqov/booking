"""Booking write operations. The only module allowed to change Booking.status."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.common.exceptions import CONSTRAINT_ERRORS, DomainError, constraint_name
from apps.notifications import senders as notifications
from apps.providers.models import Provider
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling import slot_engine
from apps.scheduling.models import BusinessSettings

from . import selectors, state_machine
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


@dataclass(frozen=True)
class CreateResult:
    booking: Booking
    replayed: bool


def slot_error(code: str) -> DomainError:
    message, status, title = SLOT_ERRORS[code]
    return DomainError(code, message, status, title=title)


def constraint_error_code(exc: IntegrityError) -> str | None:
    """Map a violated exclusion constraint to its domain error code (None if unrelated)."""
    known = CONSTRAINT_ERRORS.get(constraint_name(exc))
    return known[0] if known else None


def fingerprint(*, service_id, provider_id, start_at: datetime, note: str) -> str:
    raw = f"{service_id}|{provider_id}|{start_at.astimezone(UTC).isoformat()}|{note}"
    return hashlib.sha256(raw.encode()).hexdigest()


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
        if constraint_name(exc) == "uniq_idempotency_per_customer":
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
    business = inputs["settings"]
    if business.auto_confirm:
        _apply(
            booking,
            Booking.Status.CONFIRMED,
            actor=None,
            reason="auto_confirm",
            now=now,
            business=business,
        )
    # on_commit: no email for a booking that is rolled back, and a mail failure happens
    # after the booking is safely stored (ADR-006, edge cases #29, #37).
    transaction.on_commit(partial(notifications.booking_created, booking.pk))
    return CreateResult(booking, replayed=False)


def actor_role(actor: User | None) -> str:
    return actor.role if actor is not None else state_machine.SYSTEM


def _apply(
    booking: Booking,
    to_status: str,
    *,
    actor: User | None,
    reason: str,
    now: datetime,
    business: BusinessSettings,
) -> Booking:
    state_machine.check_transition(
        state_machine.Context(
            status=booking.status,
            start_at=booking.start_at,
            actor_role=actor_role(actor),
            now=now,
            cancellation_deadline_hours=business.cancellation_deadline_hours,
            reason=reason,
        ),
        to_status,
    )
    from_status = booking.status
    booking.status = to_status
    fields = ["status", "updated_at"]
    if to_status == Booking.Status.CANCELLED:
        booking.cancelled_at = now
        booking.cancelled_by = actor
        booking.cancel_reason = reason
        fields += ["cancelled_at", "cancelled_by", "cancel_reason"]
    booking._status_change_allowed = True
    booking.save(update_fields=fields)
    _record(booking, from_status, to_status, actor, reason)
    return booking


@transaction.atomic
def transition_booking(
    *,
    booking_id,
    to_status: str,
    actor: User | None,
    reason: str = "",
    now: datetime | None = None,
) -> Booking:
    """Move a booking to `to_status` on behalf of `actor` (None = the system)."""
    # Row lock: two admins pressing "Confirm" at once are applied one after the other, and the
    # second one is judged against the state the first one left behind (edge #23).
    booking = Booking.objects.select_for_update().filter(pk=booking_id).first()
    if booking is None or (actor is not None and not selectors.can_view(actor, booking)):
        raise DomainError("NOT_FOUND", "Bron topilmadi.", 404)
    booking = _apply(
        booking,
        to_status,
        actor=actor,
        reason=reason.strip(),
        now=now or timezone.now(),
        business=BusinessSettings.load(),
    )
    transaction.on_commit(partial(notifications.booking_status_changed, booking.pk, to_status))
    return booking
