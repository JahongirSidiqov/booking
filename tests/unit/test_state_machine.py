"""Every cell of TASK 5.3: 4 statuses × 4 target statuses × 4 actor roles, plus the guards."""

from datetime import UTC, datetime, timedelta
from itertools import product

import pytest

from apps.bookings.state_machine import (
    ADMIN,
    CANCELLED,
    COMPLETED,
    CONFIRMED,
    CUSTOMER,
    PENDING,
    PROVIDER,
    STATUSES,
    SYSTEM,
    TRANSITIONS,
    Context,
    check_transition,
)
from apps.common.exceptions import DomainError

START = datetime(2026, 10, 1, 4, tzinfo=UTC)
BEFORE = START - timedelta(days=3)  # well before start and before the 24h deadline
AFTER = START + timedelta(minutes=10)
ROLES = (CUSTOMER, PROVIDER, ADMIN, SYSTEM)

# (from, to) → roles allowed, exactly as in TASK 5.3.
ALLOWED = {
    (PENDING, CONFIRMED): {PROVIDER, ADMIN, SYSTEM},
    (PENDING, CANCELLED): {CUSTOMER, PROVIDER, ADMIN, SYSTEM},
    (CONFIRMED, CANCELLED): {CUSTOMER, PROVIDER, ADMIN, SYSTEM},
    (CONFIRMED, COMPLETED): {PROVIDER, ADMIN},
}


def ctx(status, role, now=BEFORE, reason="Sabab", deadline_hours=24):
    return Context(
        status=status,
        start_at=START,
        actor_role=role,
        now=now,
        cancellation_deadline_hours=deadline_hours,
        reason=reason,
    )


def error_code(context, to_status):
    try:
        check_transition(context, to_status)
    except DomainError as exc:
        return exc.code, exc.http_status
    return None


def test_transition_table_matches_specification():
    assert {k: set(v.roles) for k, v in TRANSITIONS.items()} == ALLOWED


@pytest.mark.parametrize(
    ("from_status", "to_status", "role"), list(product(STATUSES, STATUSES, ROLES))
)
def test_matrix_cell(from_status, to_status, role):
    # completing needs the appointment to have started; everything else is checked before it.
    now = AFTER if to_status == COMPLETED else BEFORE
    result = error_code(ctx(from_status, role, now=now), to_status)
    if (from_status, to_status) not in ALLOWED:
        assert result == ("INVALID_TRANSITION", 409)
    elif role not in ALLOWED[(from_status, to_status)]:
        assert result == ("FORBIDDEN", 403)
    else:
        assert result is None


@pytest.mark.parametrize("terminal", [CANCELLED, COMPLETED])
@pytest.mark.parametrize("role", ROLES)
def test_edge_20_terminal_states_reject_everything(terminal, role):
    for target in STATUSES:
        assert error_code(ctx(terminal, role, now=AFTER), target) == ("INVALID_TRANSITION", 409)


# --- guards -------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [PROVIDER, ADMIN, SYSTEM])
def test_edge_22_cannot_confirm_after_start(role):
    assert error_code(ctx(PENDING, role, now=START), CONFIRMED) == ("INVALID_TRANSITION", 409)
    assert error_code(ctx(PENDING, role, now=START - timedelta(seconds=1)), CONFIRMED) is None


@pytest.mark.parametrize("role", [PROVIDER, ADMIN])
def test_edge_21_cannot_complete_before_start(role):
    assert error_code(ctx(CONFIRMED, role, now=BEFORE), COMPLETED) == ("INVALID_TRANSITION", 409)
    assert error_code(ctx(CONFIRMED, role, now=START), COMPLETED) is None


@pytest.mark.parametrize("status", [PENDING, CONFIRMED])
def test_edge_19_customer_cancel_deadline(status):
    deadline = START - timedelta(hours=24)
    assert error_code(ctx(status, CUSTOMER, now=deadline, reason=""), CANCELLED) is None
    late = deadline + timedelta(seconds=1)
    assert error_code(ctx(status, CUSTOMER, now=late, reason=""), CANCELLED) == (
        "CANCELLATION_DEADLINE_PASSED",
        422,
    )


def test_deadline_hours_come_from_settings():
    now = START - timedelta(hours=3)
    assert error_code(ctx(PENDING, CUSTOMER, now=now, deadline_hours=2), CANCELLED) is None
    assert error_code(ctx(PENDING, CUSTOMER, now=now, deadline_hours=4), CANCELLED) == (
        "CANCELLATION_DEADLINE_PASSED",
        422,
    )


@pytest.mark.parametrize("role", [PROVIDER, ADMIN])
@pytest.mark.parametrize("status", [PENDING, CONFIRMED])
def test_staff_cancel_requires_reason_but_no_deadline(role, status):
    assert error_code(ctx(status, role, now=AFTER, reason="  "), CANCELLED) == (
        "VALIDATION_ERROR",
        422,
    )
    assert error_code(ctx(status, role, now=AFTER, reason="Xodim kasal"), CANCELLED) is None


def test_system_cancel_needs_no_reason_or_deadline():
    assert error_code(ctx(PENDING, SYSTEM, now=AFTER, reason=""), CANCELLED) is None


def test_invalid_transition_error_names_both_states():
    with pytest.raises(DomainError) as exc:
        check_transition(ctx(CANCELLED, ADMIN), CONFIRMED)
    assert exc.value.extra == {"from": CANCELLED, "to": CONFIRMED}
