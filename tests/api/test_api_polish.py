"""Cross-cutting API behaviour: error format everywhere, pagination, filters, OpenAPI."""

from datetime import UTC, datetime, timedelta

import pytest
from django.core.management import call_command
from django.db import OperationalError
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking, BookingStatusHistory
from apps.common.views import not_found, server_error
from tests.api.test_auth import assert_problem
from tests.bookings_setup import BOOKINGS, booking_body, frozen_now, haircut, sardor
from tests.factories import BookingFactory, ProviderFactory, ServiceFactory, UserFactory

__all__ = ["frozen_now", "haircut", "sardor"]

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 1, 4, tzinfo=UTC)


# --- error format -------------------------------------------------------------------------


def test_unknown_api_url_is_json_404(client):
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_unknown_non_api_url_keeps_html_404(client):
    response = client.get("/not-an-api-page/")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("text/html")


def test_api_500_handler_returns_problem(rf):
    response = server_error(rf.get("/api/v1/bookings"))
    assert response.status_code == 500
    assert b'"code": "SERVER_ERROR"' in response.content


def test_non_api_500_handler_is_html(rf):
    assert server_error(rf.get("/")).status_code == 500
    assert not_found(rf.get("/x"), None).status_code == 404


@pytest.mark.usefixtures("frozen_now")
def test_edge_37_database_outage_saves_nothing_and_returns_503(
    customer_client, haircut, sardor, monkeypatch
):
    real_create = BookingStatusHistory.objects.create

    def lose_connection(**kwargs):
        # The booking row is already inserted when the connection drops mid-transaction.
        assert Booking.objects.count() == 1
        raise OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(BookingStatusHistory.objects, "create", lose_connection)
    response = customer_client.post(BOOKINGS, booking_body(haircut, sardor), format="json")
    monkeypatch.setattr(BookingStatusHistory.objects, "create", real_create)

    body = assert_problem(response, 503, "SERVICE_UNAVAILABLE")
    assert response["Retry-After"] == "5"
    assert "saqlanmadi" in body["detail"]
    assert Booking.objects.count() == 0


@pytest.mark.usefixtures("frozen_now")
def test_exclusion_violation_from_any_path_is_409_not_500(
    customer_client, haircut, sardor, monkeypatch
):
    # Simulate a write path that skipped every service check: the handler still answers 409.
    BookingFactory(provider=sardor, service=haircut, start_at=T0)

    def unchecked_create(**kwargs):
        return BookingFactory(provider=sardor, service=haircut, start_at=T0)

    monkeypatch.setattr(services, "_create_locked", lambda **kw: unchecked_create())
    monkeypatch.setattr(services, "constraint_error_code", lambda exc: None)
    response = customer_client.post(BOOKINGS, booking_body(haircut, sardor), format="json")
    assert_problem(response, 409, "SLOT_TAKEN")


# --- pagination and filters ---------------------------------------------------------------


@pytest.fixture
def admin_api():
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def make_bookings(n, **kwargs):
    service = kwargs.pop("service", None) or ServiceFactory()
    provider = kwargs.pop("provider", None) or ProviderFactory()
    return [
        BookingFactory(
            service=service, provider=provider, start_at=T0 + timedelta(hours=i), **kwargs
        )
        for i in range(n)
    ]


def test_list_is_paginated_with_defaults(admin_api):
    make_bookings(25)
    body = admin_api.get(BOOKINGS).json()
    assert (body["count"], body["page"], body["page_size"], body["total_pages"]) == (25, 1, 20, 2)
    assert len(body["results"]) == 20
    assert body["next"].endswith("page=2")
    assert body["previous"] is None


def test_page_size_is_capped_at_100(admin_api):
    make_bookings(3)
    assert admin_api.get(BOOKINGS, {"page_size": 500}).json()["page_size"] == 100


def test_page_out_of_range_is_404(admin_api):
    make_bookings(1)
    assert_problem(admin_api.get(BOOKINGS, {"page": 9}), 404, "NOT_FOUND")


def test_default_order_is_newest_first(admin_api):
    first, second = make_bookings(2)
    ids = [b["id"] for b in admin_api.get(BOOKINGS).json()["results"]]
    assert ids == [str(second.pk), str(first.pk)]


def test_filter_by_status_list(admin_api):
    pending = make_bookings(1)[0]
    confirmed = make_bookings(1, status="confirmed")[0]
    make_bookings(1, status="cancelled")
    ids = {
        b["id"] for b in admin_api.get(BOOKINGS, {"status": "pending,confirmed"}).json()["results"]
    }
    assert ids == {str(pending.pk), str(confirmed.pk)}


def test_unknown_status_filter_is_422(admin_api):
    body = assert_problem(admin_api.get(BOOKINGS, {"status": "done"}), 422, "VALIDATION_ERROR")
    assert "status" in body["errors"]


def test_filter_by_provider_and_service(admin_api):
    mine = make_bookings(2)
    make_bookings(2)
    by_provider = admin_api.get(BOOKINGS, {"provider": str(mine[0].provider_id)}).json()
    by_service = admin_api.get(BOOKINGS, {"service": str(mine[0].service_id)}).json()
    assert by_provider["count"] == by_service["count"] == 2


def test_filter_by_local_date_range(admin_api):
    # 23:30 Tashkent on 30 Sep is 18:30Z; it belongs to 30 Sep locally, not 1 Oct.
    late = BookingFactory(start_at=datetime(2026, 9, 30, 18, 30, tzinfo=UTC))
    early = BookingFactory(start_at=datetime(2026, 9, 30, 19, 30, tzinfo=UTC))  # 00:30 1 Oct
    oct_1 = admin_api.get(BOOKINGS, {"from": "2026-10-01", "to": "2026-10-01"}).json()
    assert [b["id"] for b in oct_1["results"]] == [str(early.pk)]
    sep_30_utc = admin_api.get(
        BOOKINGS, {"from": "2026-09-30", "to": "2026-09-30", "tz": "UTC"}
    ).json()
    assert {b["id"] for b in sep_30_utc["results"]} == {str(late.pk), str(early.pk)}


def test_reversed_date_range_is_422(admin_api):
    assert_problem(
        admin_api.get(BOOKINGS, {"from": "2026-10-05", "to": "2026-10-01"}), 422, "VALIDATION_ERROR"
    )


def test_upcoming_hides_finished_and_sorts_soonest_first(admin_api):
    past = BookingFactory(start_at=datetime(2026, 9, 20, 4, tzinfo=UTC))
    later, sooner = BookingFactory(start_at=T0 + timedelta(days=2)), BookingFactory(start_at=T0)
    with freeze_time("2026-09-26 12:00:00"):
        ids = [b["id"] for b in admin_api.get(BOOKINGS, {"upcoming": "1"}).json()["results"]]
    assert ids == [str(sooner.pk), str(later.pk)]
    assert str(past.pk) not in ids


def test_filters_never_widen_visibility(customer_client):
    make_bookings(3)
    own = BookingFactory(customer=customer_client.user, start_at=T0 + timedelta(days=5))
    body = customer_client.get(BOOKINGS, {"status": "pending", "page_size": 100}).json()
    assert [b["id"] for b in body["results"]] == [str(own.pk)]


# --- OpenAPI ------------------------------------------------------------------------------


def test_openapi_schema_is_valid_without_warnings(tmp_path):
    call_command(
        "spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yaml")
    )
    schema = (tmp_path / "schema.yaml").read_text(encoding="utf-8")
    for path in (
        "/api/v1/bookings/{id}/cancel:",
        "/api/v1/availability/slots:",
        "/api/v1/providers/{id}/time-off/{time_off_id}:",
        "/api/v1/auth/token/refresh:",
    ):
        assert path in schema


def test_schema_and_swagger_are_served(client):
    assert client.get("/api/schema/").status_code == 200
    page = client.get("/api/docs/")
    assert page.status_code == 200
    assert b"swagger" in page.content.lower()


def test_every_operation_has_a_summary(client):
    import yaml

    schema = yaml.safe_load(client.get("/api/schema/").content)
    missing = [
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if not operation.get("summary")
    ]
    assert missing == []
