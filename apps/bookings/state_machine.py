"""Booking status state machine (TASK 5.3). Pure: no database, `now` is passed in.

    pending ──confirm──▶ confirmed ──complete──▶ completed
       │                    │
       └──────cancel────────┴──────▶ cancelled

completed and cancelled are terminal.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.common.exceptions import DomainError

PENDING, CONFIRMED, CANCELLED, COMPLETED = "pending", "confirmed", "cancelled", "completed"
STATUSES = (PENDING, CONFIRMED, CANCELLED, COMPLETED)

CUSTOMER, PROVIDER, ADMIN, SYSTEM = "customer", "provider", "admin", "system"
STAFF = frozenset({PROVIDER, ADMIN})


@dataclass(frozen=True)
class Context:
    status: str
    start_at: datetime
    actor_role: str
    now: datetime
    cancellation_deadline_hours: int
    reason: str = ""


Guard = Callable[[Context], None]


@dataclass(frozen=True)
class Transition:
    roles: frozenset[str]
    guard: Guard
    # Roles that must explain themselves (staff cancelling: the customer deserves a reason).
    reason_required_for: frozenset[str] = frozenset()


def invalid(ctx: Context, to_status: str, why: str) -> DomainError:
    return DomainError(
        "INVALID_TRANSITION",
        f"Bronni '{ctx.status}' holatidan '{to_status}' holatiga oʻtkazib boʻlmaydi: {why}",
        409,
        title="Holatni oʻzgartirib boʻlmaydi",
        extra={"from": ctx.status, "to": to_status},
    )


def _not_started(ctx: Context) -> None:
    # Confirming an appointment whose time has passed is meaningless (edge #22);
    # expire_stale_bookings cancels such rows instead.
    if ctx.now >= ctx.start_at:
        raise invalid(ctx, CONFIRMED, "uchrashuv vaqti oʻtib ketgan.")


def _started(ctx: Context) -> None:
    if ctx.now < ctx.start_at:
        raise invalid(ctx, COMPLETED, "uchrashuv hali boshlanmagan.")


def _cancel(ctx: Context) -> None:
    if ctx.actor_role == CUSTOMER:
        deadline = ctx.start_at - timedelta(hours=ctx.cancellation_deadline_hours)
        if ctx.now > deadline:
            raise DomainError(
                "CANCELLATION_DEADLINE_PASSED",
                f"Bronni uchrashuvdan kamida {ctx.cancellation_deadline_hours} soat oldin "
                "bekor qilish mumkin. Biznes bilan bogʻlaning.",
                422,
                title="Bekor qilish muddati oʻtgan",
            )


TRANSITIONS: dict[tuple[str, str], Transition] = {
    (PENDING, CONFIRMED): Transition(frozenset({PROVIDER, ADMIN, SYSTEM}), _not_started),
    (PENDING, CANCELLED): Transition(
        frozenset({CUSTOMER, PROVIDER, ADMIN, SYSTEM}), _cancel, STAFF
    ),
    (CONFIRMED, CANCELLED): Transition(
        frozenset({CUSTOMER, PROVIDER, ADMIN, SYSTEM}), _cancel, STAFF
    ),
    (CONFIRMED, COMPLETED): Transition(frozenset({PROVIDER, ADMIN}), _started),
}


def check_transition(ctx: Context, to_status: str) -> None:
    """Raise the DomainError that forbids ctx.status → to_status, or return if allowed.

    Order matters for the error the client sees: an impossible move is 409 whoever asks,
    a possible move by the wrong role is 403, and only then are time/reason guards applied.
    """
    transition = TRANSITIONS.get((ctx.status, to_status))
    if transition is None:
        why = "yakuniy holat." if ctx.status in (CANCELLED, COMPLETED) else "bunday oʻtish yoʻq."
        raise invalid(ctx, to_status, why)
    if ctx.actor_role not in transition.roles:
        raise DomainError("FORBIDDEN", "Bu amalni bajarishga ruxsatingiz yoʻq.", 403)
    transition.guard(ctx)
    if ctx.actor_role in transition.reason_required_for and not ctx.reason.strip():
        raise DomainError(
            "VALIDATION_ERROR",
            "Kiritilgan maʼlumotlarni tekshiring.",
            errors={"reason": ["Xodim yoki admin bekor qilganda sabab majburiy."]},
        )


def available_targets(ctx: Context) -> list[str]:
    """Statuses `ctx.actor_role` could move the booking to right now (reason aside).

    Drives which action buttons the dashboard shows, from the same table the service
    enforces, so the UI never offers an action the server would refuse for time or role.
    """
    targets = []
    for (from_status, to_status), transition in TRANSITIONS.items():
        if from_status != ctx.status or ctx.actor_role not in transition.roles:
            continue
        try:
            transition.guard(ctx)
        except DomainError:
            continue
        targets.append(to_status)
    return targets


def reason_required(status: str, to_status: str, actor_role: str) -> bool:
    transition = TRANSITIONS.get((status, to_status))
    return bool(transition and actor_role in transition.reason_required_for)
