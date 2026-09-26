import uuid
from datetime import UTC, datetime, time

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.scheduling.models import TimeOff
from tests.api.test_auth import assert_problem
from tests.factories import AvailabilityRuleFactory, ProviderFactory, ServiceFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_now")]

SLOTS = "/api/v1/availability/slots"
DAYS = "/api/v1/availability/days"


@pytest.fixture
def frozen_now():
    with freeze_time("2026-09-26 12:00:00"):
        yield


@pytest.fixture
def haircut():
    return ServiceFactory(name="Soch olish", duration_minutes=30)


@pytest.fixture
def sardor(haircut):
    provider = ProviderFactory(name="Sardor", with_services=[haircut])
    # Thursday 09:00–18:00 Tashkent
    AvailabilityRuleFactory(provider=provider, weekday=3, start_time=time(9), end_time=time(18))
    return provider


def params(service, provider, **extra):
    return {"service": str(service.pk), "provider": str(provider.pk), **extra}


def test_slots_match_documented_example(api_client, haircut, sardor):
    response = api_client.get(SLOTS, params(haircut, sardor, date="2026-10-01"))
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["date"] == "2026-10-01"
    assert body["timezone"] == "Asia/Tashkent"
    assert body["service"] == {
        "id": str(haircut.pk),
        "name": "Soch olish",
        "duration_minutes": 30,
        "price": "60000.00",
    }
    assert body["provider"] == {"id": str(sardor.pk), "name": "Sardor"}
    assert body["slots"][:2] == [
        {
            "start_at": "2026-10-01T04:00:00Z",
            "end_at": "2026-10-01T04:30:00Z",
            "start_local": "09:00",
            "end_local": "09:30",
        },
        {
            "start_at": "2026-10-01T04:15:00Z",
            "end_at": "2026-10-01T04:45:00Z",
            "start_local": "09:15",
            "end_local": "09:45",
        },
    ]
    assert len(body["slots"]) == 35


def test_edge_17_customer_timezone_changes_local_labels_only(api_client, haircut, sardor):
    body = api_client.get(SLOTS, params(haircut, sardor, date="2026-10-01", tz="Asia/Dubai")).json()
    assert body["timezone"] == "Asia/Dubai"
    assert body["slots"][0]["start_at"] == "2026-10-01T04:00:00Z"
    assert body["slots"][0]["start_local"] == "08:00"


def test_logged_in_user_timezone_is_default(api_client, haircut, sardor):
    api_client.force_authenticate(UserFactory(timezone="Asia/Dubai"))
    body = api_client.get(SLOTS, params(haircut, sardor, date="2026-10-01")).json()
    assert body["timezone"] == "Asia/Dubai"


def test_edge_28_invalid_timezone_is_422(api_client, haircut, sardor):
    body = assert_problem(
        api_client.get(SLOTS, params(haircut, sardor, date="2026-10-01", tz="Asia/Toshkent")),
        422,
        "VALIDATION_ERROR",
    )
    assert "tz" in body["errors"]


def test_time_off_removes_slots(api_client, haircut, sardor):
    TimeOff.objects.create(
        provider=sardor,
        start_at=datetime(2026, 10, 1, 4, tzinfo=UTC),
        end_at=datetime(2026, 10, 1, 13, tzinfo=UTC),
    )
    body = api_client.get(SLOTS, params(haircut, sardor, date="2026-10-01")).json()
    assert body["slots"] == []


def test_day_without_rules_is_empty(api_client, haircut, sardor):
    assert api_client.get(SLOTS, params(haircut, sardor, date="2026-10-02")).json()["slots"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("date", "01.10.2026"), ("date", "2026-02-30"), ("service", "abc"), ("provider", "")],
)
def test_bad_query_is_422(api_client, haircut, sardor, field, value):
    query = params(haircut, sardor, date="2026-10-01")
    query[field] = value
    body = assert_problem(api_client.get(SLOTS, query), 422, "VALIDATION_ERROR")
    assert field in body["errors"]


def test_missing_params_listed_in_errors(api_client):
    body = assert_problem(api_client.get(SLOTS), 422, "VALIDATION_ERROR")
    assert set(body["errors"]) == {"service", "provider", "date"}


def test_unknown_service_is_404(api_client, sardor):
    assert_problem(
        api_client.get(
            SLOTS, {"service": str(uuid.uuid4()), "provider": str(sardor.pk), "date": "2026-10-01"}
        ),
        404,
        "NOT_FOUND",
    )


def test_edge_09_provider_not_offering_service(api_client, sardor):
    other = ServiceFactory()
    assert_problem(
        api_client.get(SLOTS, params(other, sardor, date="2026-10-01")),
        422,
        "PROVIDER_NOT_OFFERING_SERVICE",
    )


@pytest.mark.parametrize("target", ["service", "provider"])
def test_edge_10_inactive_resource(api_client, haircut, sardor, target):
    obj = haircut if target == "service" else sardor
    obj.is_active = False
    obj.save()
    assert_problem(
        api_client.get(SLOTS, params(haircut, sardor, date="2026-10-01")),
        422,
        "INACTIVE_RESOURCE",
    )


# --- days ---------------------------------------------------------------------------------


def test_days_summary(api_client, haircut, sardor):
    response = api_client.get(
        DAYS, params(haircut, sardor, **{"from": "2026-09-30", "to": "2026-10-08"})
    )
    assert response.status_code == 200, response.content
    body = response.json()
    counts = {d["date"]: d["available"] for d in body["days"]}
    assert len(counts) == 9
    assert counts["2026-10-01"] == 35
    assert counts["2026-10-08"] == 35
    assert counts["2026-10-02"] == 0


def test_edge_27_range_too_large_is_400(api_client, haircut, sardor):
    body = assert_problem(
        api_client.get(DAYS, params(haircut, sardor, **{"from": "2026-10-01", "to": "2026-12-29"})),
        400,
        "RANGE_TOO_LARGE",
    )
    assert "errors" not in body


def test_days_reversed_range_is_422(api_client, haircut, sardor):
    assert_problem(
        api_client.get(DAYS, params(haircut, sardor, **{"from": "2026-10-05", "to": "2026-10-01"})),
        422,
        "VALIDATION_ERROR",
    )


def test_days_requires_from_and_to(api_client, haircut, sardor):
    body = assert_problem(api_client.get(DAYS, params(haircut, sardor)), 422, "VALIDATION_ERROR")
    assert {"from", "to"} <= set(body["errors"])


def test_slots_are_public(haircut, sardor):
    assert APIClient().get(SLOTS, params(haircut, sardor, date="2026-10-01")).status_code == 200
