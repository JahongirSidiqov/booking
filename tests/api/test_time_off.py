import uuid
from datetime import UTC, datetime

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.scheduling.models import TimeOff
from tests.api.test_auth import assert_problem
from tests.factories import ProviderFactory

pytestmark = pytest.mark.django_db


def url(provider, time_off_id=None):
    base = f"/api/v1/providers/{provider.pk}/time-off"
    return f"{base}/{time_off_id}" if time_off_id else base


def payload(**overrides):
    data = {
        "start_at": "2026-10-05T09:00:00+05:00",
        "end_at": "2026-10-05T18:00:00+05:00",
        "reason": "Shifokor qabuli",
    }
    data.update(overrides)
    return data


def test_admin_adds_time_off_stored_in_utc(admin_client):
    provider = ProviderFactory()
    response = admin_client.post(url(provider), payload(), format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["start_at"] == "2026-10-05T04:00:00Z"
    assert body["end_at"] == "2026-10-05T13:00:00Z"
    stored = TimeOff.objects.get(pk=body["id"])
    assert stored.start_at == datetime(2026, 10, 5, 4, 0, tzinfo=UTC)


def test_naive_datetime_rejected(admin_client):
    body = assert_problem(
        admin_client.post(
            url(ProviderFactory()), payload(start_at="2026-10-05T09:00:00"), format="json"
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert "start_at" in body["errors"]


def test_end_before_start_rejected(admin_client):
    body = assert_problem(
        admin_client.post(
            url(ProviderFactory()),
            payload(start_at="2026-10-05T18:00:00+05:00", end_at="2026-10-05T09:00:00+05:00"),
            format="json",
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert "end_at" in body["errors"]


def test_offsets_are_compared_as_instants(admin_client):
    # 10:00+05:00 (05:00Z) ends after 04:30Z even though "10:00" < "04:30" is false textually.
    response = admin_client.post(
        url(ProviderFactory()),
        payload(start_at="2026-10-05T04:30:00Z", end_at="2026-10-05T10:00:00+05:00"),
        format="json",
    )
    assert response.status_code == 201, response.content


def test_list_hides_past_unless_requested(admin_client):
    provider = ProviderFactory()
    TimeOff.objects.create(
        provider=provider,
        start_at=datetime(2026, 9, 1, 4, tzinfo=UTC),
        end_at=datetime(2026, 9, 2, 4, tzinfo=UTC),
    )
    upcoming = TimeOff.objects.create(
        provider=provider,
        start_at=datetime(2026, 10, 1, 4, tzinfo=UTC),
        end_at=datetime(2026, 10, 2, 4, tzinfo=UTC),
    )
    with freeze_time("2026-09-26 12:00:00"):
        assert [t["id"] for t in admin_client.get(url(provider)).json()] == [str(upcoming.pk)]
        assert len(admin_client.get(url(provider), {"include_past": "1"}).json()) == 2


def test_delete_time_off(admin_client):
    provider = ProviderFactory()
    item = admin_client.post(url(provider), payload(), format="json").json()
    assert admin_client.delete(url(provider, item["id"])).status_code == 204
    assert not TimeOff.objects.exists()


def test_delete_other_providers_time_off_is_404(admin_client):
    a, b = ProviderFactory(), ProviderFactory()
    item = admin_client.post(url(a), payload(), format="json").json()
    assert_problem(admin_client.delete(url(b, item["id"])), 404, "NOT_FOUND")
    assert TimeOff.objects.count() == 1


def test_delete_malformed_or_unknown_id_is_404(admin_client):
    provider = ProviderFactory()
    assert_problem(admin_client.delete(url(provider, "abc")), 404, "NOT_FOUND")
    assert_problem(admin_client.delete(url(provider, uuid.uuid4())), 404, "NOT_FOUND")


def test_provider_manages_own_time_off(provider_client, own_provider):
    response = provider_client.post(url(own_provider), payload(), format="json")
    assert response.status_code == 201
    assert provider_client.delete(url(own_provider, response.json()["id"])).status_code == 204


def test_provider_cannot_add_time_off_for_other(provider_client, own_provider):
    assert_problem(
        provider_client.post(url(ProviderFactory()), payload(), format="json"), 403, "FORBIDDEN"
    )


def test_customer_and_anon_blocked(customer_client):
    provider = ProviderFactory()
    assert_problem(customer_client.post(url(provider), payload(), format="json"), 403, "FORBIDDEN")
    assert_problem(APIClient().get(url(provider)), 401, "AUTH_REQUIRED")


def test_impossible_date_rejected(admin_client):
    assert_problem(
        admin_client.post(
            url(ProviderFactory()), payload(start_at="2026-02-30T09:00:00+05:00"), format="json"
        ),
        422,
        "VALIDATION_ERROR",
    )


def test_service_rejects_inverted_range_even_without_serializer():
    from apps.common.exceptions import DomainError
    from apps.scheduling.services import add_time_off

    with pytest.raises(DomainError) as exc:
        add_time_off(
            provider=ProviderFactory(),
            start_at=datetime(2026, 10, 5, 13, tzinfo=UTC),
            end_at=datetime(2026, 10, 5, 4, tzinfo=UTC),
        )
    assert exc.value.errors == {"end_at": ["Tugash vaqti boshlanishdan keyin boʻlsin."]}
