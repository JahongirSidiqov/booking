"""Real parallel requests against PostgreSQL (edge case #1).

These tests need committed data visible across connections, so they run with
transaction=True (TransactionTestCase semantics) and each thread uses its own connection.
"""

import threading
from collections import Counter
from datetime import time

import pytest
from django.db import connections
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking
from apps.providers.models import Provider
from apps.scheduling.models import BusinessSettings
from tests.bookings_setup import BOOKINGS, NOW, SLOT_0900, booking_body
from tests.factories import AvailabilityRuleFactory, ProviderFactory, ServiceFactory, UserFactory

pytestmark = pytest.mark.django_db(transaction=True)

THREADS = 10


@pytest.fixture
def scenario():
    BusinessSettings.load()
    haircut = ServiceFactory(duration_minutes=30)
    sardor = ProviderFactory(with_services=[haircut])
    AvailabilityRuleFactory(provider=sardor, weekday=3, start_time=time(9), end_time=time(18))
    return haircut, sardor


def run_parallel(requests):
    """Fire all callables at the same moment; return their (status, code) results."""
    barrier = threading.Barrier(len(requests))
    results = [None] * len(requests)

    def worker(i, call):
        try:
            barrier.wait()
            response = call()
            body = response.json() if response.content else {}
            results[i] = (response.status_code, body.get("code") or body.get("status"))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(requests)]
    with freeze_time(NOW):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
    return results


def post_as(user, body, key=None):
    def call():
        client = APIClient()
        client.force_authenticate(user)
        headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
        return client.post(BOOKINGS, body, format="json", **headers)

    return call


def test_edge_01_ten_customers_one_slot_one_winner(scenario):
    haircut, sardor = scenario
    customers = [UserFactory(role=User.Role.CUSTOMER) for _ in range(THREADS)]
    body = booking_body(haircut, sardor, SLOT_0900)

    results = run_parallel([post_as(c, body) for c in customers])

    statuses = Counter(status for status, _ in results)
    assert statuses == {201: 1, 409: THREADS - 1}, results
    assert {code for status, code in results if status == 409} == {"SLOT_TAKEN"}
    assert Booking.objects.count() == 1


def test_constraint_alone_still_yields_one_winner(scenario, monkeypatch):
    """Without the provider lock every request passes validation; the DB must still decide."""
    haircut, sardor = scenario
    monkeypatch.setattr(
        services, "_lock_provider", lambda pk: Provider.objects.filter(pk=pk).first()
    )
    customers = [UserFactory(role=User.Role.CUSTOMER) for _ in range(THREADS)]
    body = booking_body(haircut, sardor, SLOT_0900)

    results = run_parallel([post_as(c, body) for c in customers])

    assert Counter(status for status, _ in results) == {201: 1, 409: THREADS - 1}, results
    assert {code for status, code in results if status == 409} == {"SLOT_TAKEN"}
    assert Booking.objects.count() == 1


def test_parallel_retries_with_same_key_replay_one_booking(scenario):
    haircut, sardor = scenario
    customer = UserFactory(role=User.Role.CUSTOMER)
    body = booking_body(haircut, sardor, SLOT_0900)

    results = run_parallel([post_as(customer, body, key="retry-1") for _ in range(5)])

    assert Counter(status for status, _ in results) == {201: 1, 200: 4}, results
    assert Booking.objects.count() == 1


def test_same_customer_two_providers_at_once(scenario):
    """Different providers take different locks; only the customer constraint can stop this."""
    haircut, sardor = scenario
    jasur = ProviderFactory(with_services=[haircut])
    AvailabilityRuleFactory(provider=jasur, weekday=3, start_time=time(9), end_time=time(18))
    customer = UserFactory(role=User.Role.CUSTOMER)

    results = run_parallel(
        [
            post_as(customer, booking_body(haircut, sardor, SLOT_0900)),
            post_as(customer, booking_body(haircut, jasur, SLOT_0900)),
        ]
    )

    assert sorted(status for status, _ in results) == [201, 409], results
    assert [code for status, code in results if status == 409] == ["CUSTOMER_OVERLAP"]
    assert Booking.objects.count() == 1


def test_other_providers_are_not_blocked(scenario):
    """The lock is per provider: parallel bookings for different providers all succeed."""
    haircut, _ = scenario
    calls = []
    for _ in range(4):
        provider = ProviderFactory(with_services=[haircut])
        AvailabilityRuleFactory(provider=provider, weekday=3, start_time=time(9), end_time=time(18))
        calls.append(post_as(UserFactory(role=User.Role.CUSTOMER), booking_body(haircut, provider)))

    results = run_parallel(calls)

    assert [status for status, _ in results] == [201] * 4, results
