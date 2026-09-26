"""Service paths that real concurrency reaches only by chance, forced deterministically."""

from types import SimpleNamespace

import pytest
from django.db import IntegrityError

from apps.bookings import services
from apps.common.exceptions import DomainError
from tests.bookings_setup import SLOT_0900, frozen_now, haircut, sardor
from tests.factories import UserFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]


class _DriverError(Exception):
    """Stands in for the psycopg error Django wraps; only `.diag` is read."""

    def __init__(self, constraint: str):
        super().__init__(constraint)
        self.diag = SimpleNamespace(constraint_name=constraint)


def violation(constraint: str) -> IntegrityError:
    exc = IntegrityError("duplicate key")
    exc.__cause__ = _DriverError(constraint)
    return exc


def create(customer, service, provider, key="k1"):
    from django.utils.dateparse import parse_datetime

    return services.create_booking(
        customer=customer,
        service_id=service.pk,
        provider_id=provider.pk,
        start_at=parse_datetime(SLOT_0900),
        idempotency_key=key,
    )


def test_idempotency_race_lost_on_unique_key_replays_winner(haircut, sardor, monkeypatch):
    customer = UserFactory()
    winner = create(customer, haircut, sardor)

    # The racing twin passed the replay check before the winner committed, then hit the
    # unique (customer, idempotency_key) index on insert.
    def lose_race(**kwargs):
        raise violation("uniq_idempotency_per_customer")

    monkeypatch.setattr(services, "_create_locked", lose_race)
    result = create(customer, haircut, sardor)
    assert result.replayed is True
    assert result.booking.pk == winner.booking.pk


def test_unrelated_integrity_error_is_not_swallowed(haircut, sardor, monkeypatch):
    def broken(**kwargs):
        raise violation("some_other_constraint")

    monkeypatch.setattr(services, "_create_locked", broken)
    with pytest.raises(IntegrityError):
        create(UserFactory(), haircut, sardor)


def test_customer_constraint_violation_maps_to_409(haircut, sardor, monkeypatch):
    def lose(**kwargs):
        raise violation("no_overlap_per_customer")

    monkeypatch.setattr(services, "_create_locked", lose)
    with pytest.raises(DomainError) as exc:
        create(UserFactory(), haircut, sardor)
    assert (exc.value.code, exc.value.status) == ("CUSTOMER_OVERLAP", 409)
