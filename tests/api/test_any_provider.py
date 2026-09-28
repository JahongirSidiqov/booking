"""Bonus: "any provider" — union of free slots and fair automatic assignment."""

import re
from datetime import UTC, datetime, time

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking
from apps.common.exceptions import DomainError
from apps.scheduling.slot_engine import Slot, union_slots
from tests.api.test_auth import assert_problem
from tests.bookings_setup import BOOKINGS, SLOT_0900, frozen_now
from tests.factories import (
    AvailabilityRuleFactory,
    BookingFactory,
    ProviderFactory,
    ServiceFactory,
    UserFactory,
)

__all__ = ["frozen_now"]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

T_0900 = datetime(2026, 10, 1, 4, tzinfo=UTC)
START = datetime.fromisoformat(SLOT_0900)


@pytest.fixture
def team():
    """Three barbers offer the haircut on Thursday; Bobur starts later (10:00)."""
    haircut = ServiceFactory(name="Soch olish", duration_minutes=30)
    barbers = []
    for name, opens in (("Akmal", 9), ("Bobur", 10), ("Sardor", 9)):
        provider = ProviderFactory(name=name, with_services=[haircut])
        AvailabilityRuleFactory(
            provider=provider, weekday=3, start_time=time(opens), end_time=time(18)
        )
        barbers.append(provider)
    return haircut, barbers


def customer():
    return UserFactory(role=User.Role.CUSTOMER)


def book_any(service, user=None, start=START, **kwargs):
    return services.create_booking_any(
        customer=user or customer(), service_id=service.pk, start_at=start, **kwargs
    )


# --- union --------------------------------------------------------------------------------


def test_union_slots_deduplicates_and_sorts():
    a = Slot(T_0900, T_0900.replace(minute=30))
    b = Slot(T_0900.replace(hour=5), T_0900.replace(hour=5, minute=30))
    assert union_slots([[b, a], [a]]) == [a, b]


def test_slots_api_any_is_union(team):
    haircut, (akmal, _bobur, sardor) = team
    BookingFactory(provider=akmal, service=haircut, start_at=T_0900)
    BookingFactory(provider=sardor, service=haircut, start_at=T_0900)
    body = (
        APIClient()
        .get(
            "/api/v1/availability/slots",
            {"service": str(haircut.pk), "provider": "any", "date": "2026-10-01"},
        )
        .json()
    )
    starts = [s["start_local"] for s in body["slots"]]
    assert body["provider"] is None
    assert "09:00" not in starts  # both 09:00 barbers are busy, Bobur starts at 10:00
    assert starts[0] == "09:30"
    assert len(starts) == len(set(starts))


def test_days_api_any_counts_union_not_sum(team):
    haircut, _ = team
    days = (
        APIClient()
        .get(
            "/api/v1/availability/days",
            {
                "service": str(haircut.pk),
                "provider": "any",
                "from": "2026-10-01",
                "to": "2026-10-01",
            },
        )
        .json()["days"]
    )
    assert days == [{"date": "2026-10-01", "available": 35}]  # 09:00–17:30, not 35 + 31 + 35


def test_slots_api_rejects_garbage_provider(team):
    haircut, _ = team
    body = assert_problem(
        APIClient().get(
            "/api/v1/availability/slots",
            {"service": str(haircut.pk), "provider": "anyone", "date": "2026-10-01"},
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert "provider" in body["errors"]


# --- assignment ---------------------------------------------------------------------------


def test_least_busy_provider_is_chosen_ties_by_name(team):
    haircut, (akmal, _bobur, sardor) = team
    BookingFactory(provider=akmal, service=haircut, start_at=T_0900.replace(hour=8))  # 13:00
    assert book_any(haircut).booking.provider == sardor  # Akmal already has one that day


def test_falls_back_when_first_choice_is_taken(team):
    haircut, (akmal, _bobur, sardor) = team
    BookingFactory(provider=akmal, service=haircut, start_at=T_0900)
    assert book_any(haircut).booking.provider == sardor


def test_provider_who_does_not_work_then_is_skipped(team):
    haircut, (akmal, _bobur, sardor) = team
    BookingFactory(provider=akmal, service=haircut, start_at=T_0900)
    BookingFactory(provider=sardor, service=haircut, start_at=T_0900)
    with pytest.raises(DomainError) as exc:
        book_any(haircut)  # Bobur only starts at 10:00
    assert exc.value.code == "SLOT_TAKEN"


def test_nobody_works_then_is_slot_unavailable(team):
    haircut, _ = team
    with pytest.raises(DomainError) as exc:
        book_any(haircut, start=datetime.fromisoformat("2026-10-01T19:00:00+05:00"))
    assert exc.value.code == "SLOT_UNAVAILABLE"


def test_general_rule_fails_fast_without_trying_everyone(team):
    haircut, _ = team
    with pytest.raises(DomainError) as exc:
        book_any(haircut, start=datetime.fromisoformat("2026-09-24T09:00:00+05:00"))
    assert exc.value.code == "IN_PAST"


def test_customer_overlap_is_not_retried_on_other_providers(team):
    haircut, _ = team
    user = customer()
    book_any(haircut, user=user)
    with pytest.raises(DomainError) as exc:
        book_any(haircut, user=user)
    assert exc.value.code == "CUSTOMER_OVERLAP"
    assert Booking.objects.filter(customer=user).count() == 1


def test_inactive_or_unknown_service(team):
    haircut, _ = team
    haircut.is_active = False
    haircut.save()
    with pytest.raises(DomainError) as exc:
        book_any(haircut)
    assert exc.value.code == "INACTIVE_RESOURCE"


def test_idempotent_retry_returns_same_provider(team):
    haircut, (_akmal, _bobur, _sardor) = team
    user = customer()
    first = book_any(haircut, user=user, idempotency_key="k-any")
    # Load changes so a fresh choice would now pick someone else — the retry must not care.
    BookingFactory(
        provider=first.booking.provider, service=haircut, start_at=T_0900.replace(hour=10)
    )
    again = book_any(haircut, user=user, idempotency_key="k-any")
    assert again.replayed and again.booking.pk == first.booking.pk
    with pytest.raises(DomainError) as exc:
        book_any(haircut, user=user, idempotency_key="k-any", note="boshqa")
    assert exc.value.code == "IDEMPOTENCY_MISMATCH"


# --- API ----------------------------------------------------------------------------------


def test_post_without_provider_assigns_one(team):
    haircut, barbers = team
    client = APIClient()
    client.force_authenticate(customer())
    response = client.post(
        BOOKINGS, {"service_id": str(haircut.pk), "start_at": SLOT_0900}, format="json"
    )
    assert response.status_code == 201, response.content
    assert response.json()["provider"]["id"] in {str(b.pk) for b in barbers}


def test_post_with_null_provider_when_all_taken_is_409(team):
    haircut, (akmal, _bobur, sardor) = team
    for barber in (akmal, sardor):
        BookingFactory(provider=barber, service=haircut, start_at=T_0900)
    client = APIClient()
    client.force_authenticate(customer())
    response = client.post(
        BOOKINGS,
        {"service_id": str(haircut.pk), "provider_id": None, "start_at": SLOT_0900},
        format="json",
    )
    assert_problem(response, 409, "SLOT_TAKEN")


# --- web ----------------------------------------------------------------------------------


def test_web_flow_with_any_provider(client, team):
    haircut, _barbers = team
    user = customer()
    client.force_login(user)
    step1 = client.get(f"/book/{haircut.slug}/").content.decode()
    assert 'value="any"' in step1 and "Istalgan xodim" in step1

    step2 = client.get(f"/book/{haircut.slug}/?provider=any&date=2026-10-01").content.decode()
    assert "Istalgan xodim" in step2
    assert 'value="2026-10-01T04:00:00Z"' in step2

    step3 = client.get(f"/book/{haircut.slug}/?provider=any&start=2026-10-01T04:00:00Z")
    html = step3.content.decode()
    assert "tasdiqlashda tizim tanlaydi" in html
    key = re.search(r'name="idempotency_key" value="([^"]+)"', html).group(1)
    response = client.post(
        f"/book/{haircut.slug}/confirm/",
        {"provider": "any", "start_at": "2026-10-01T04:00:00Z", "idempotency_key": key},
    )
    booking = Booking.objects.get(customer=user)
    assert response["Location"] == f"/book/{haircut.slug}/done/{booking.pk}/"
    done = client.get(response["Location"]).content.decode()
    assert booking.provider.name in done


def test_any_option_hidden_when_only_one_provider(client):
    service = ServiceFactory()
    ProviderFactory(with_services=[service])
    assert 'value="any"' not in client.get(f"/book/{service.slug}/").content.decode()


def test_web_any_when_taken_returns_to_picker(client, team):
    haircut, (akmal, _bobur, sardor) = team
    client.force_login(customer())
    for barber in (akmal, sardor):
        BookingFactory(provider=barber, service=haircut, start_at=T_0900)
    response = client.post(
        f"/book/{haircut.slug}/confirm/",
        {"provider": "any", "start_at": "2026-10-01T04:00:00Z", "idempotency_key": "k1"},
    )
    assert "provider=any" in response["Location"]
