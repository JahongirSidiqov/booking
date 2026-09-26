import uuid

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.scheduling.models import AvailabilityRule
from tests.api.test_auth import assert_problem
from tests.factories import AvailabilityRuleFactory, ProviderFactory, UserFactory

pytestmark = pytest.mark.django_db


def url(provider_or_id):
    return f"/api/v1/providers/{getattr(provider_or_id, 'pk', provider_or_id)}/availability"


def rule(weekday, start, end):
    return {"weekday": weekday, "start_time": start, "end_time": end}


WEEK = [rule(d, "09:00", "13:00") for d in range(5)] + [rule(d, "14:00", "18:00") for d in range(5)]


def test_admin_puts_whole_week(admin_client):
    provider = ProviderFactory()
    response = admin_client.put(url(provider), {"rules": WEEK}, format="json")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["provider_id"] == str(provider.pk)
    assert body["timezone"] == "Asia/Tashkent"
    assert len(body["rules"]) == 10
    assert body["rules"][:2] == [rule(0, "09:00", "13:00"), rule(0, "14:00", "18:00")]


def test_put_replaces_previous_rules(admin_client):
    provider = ProviderFactory()
    AvailabilityRuleFactory(provider=provider, weekday=6)
    admin_client.put(url(provider), {"rules": [rule(2, "10:00", "12:00")]}, format="json")
    assert list(provider.availability_rules.values_list("weekday", flat=True)) == [2]


def test_put_empty_week_clears_schedule(admin_client):
    provider = ProviderFactory()
    AvailabilityRuleFactory(provider=provider)
    response = admin_client.put(url(provider), {"rules": []}, format="json")
    assert response.json()["rules"] == []


def test_timezone_uses_provider_override(admin_client):
    provider = ProviderFactory(timezone="Asia/Dubai")
    assert admin_client.get(url(provider)).json()["timezone"] == "Asia/Dubai"


def test_touching_windows_are_allowed(admin_client):
    rules = [rule(0, "09:00", "13:00"), rule(0, "13:00", "18:00")]
    assert (
        admin_client.put(url(ProviderFactory()), {"rules": rules}, format="json").status_code == 200
    )


def test_edge_15_overlapping_rules_same_day_rejected(admin_client):
    provider = ProviderFactory()
    AvailabilityRuleFactory(provider=provider)
    rules = [rule(0, "09:00", "14:00"), rule(0, "13:00", "18:00")]
    body = assert_problem(
        admin_client.put(url(provider), {"rules": rules}, format="json"), 422, "VALIDATION_ERROR"
    )
    assert "Dushanba" in body["errors"]["rules"][0]
    # A rejected PUT leaves the old schedule intact.
    assert provider.availability_rules.count() == 1


def test_same_times_on_different_days_do_not_overlap(admin_client):
    rules = [rule(0, "09:00", "14:00"), rule(1, "09:00", "14:00")]
    assert (
        admin_client.put(url(ProviderFactory()), {"rules": rules}, format="json").status_code == 200
    )


def test_edge_16_rule_crossing_midnight_rejected(admin_client):
    body = assert_problem(
        admin_client.put(
            url(ProviderFactory()), {"rules": [rule(4, "22:00", "02:00")]}, format="json"
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert "Yarim tundan" in str(body["errors"])


@pytest.mark.parametrize(
    "bad",
    [
        rule(0, "10:00", "10:00"),
        rule(7, "09:00", "10:00"),
        rule(-1, "09:00", "10:00"),
        rule(0, "25:00", "26:00"),
        rule(0, "09:00:30", "10:00"),
        {"weekday": 0, "start_time": "09:00"},
    ],
)
def test_rule_shape_validation(admin_client, bad):
    assert_problem(
        admin_client.put(url(ProviderFactory()), {"rules": [bad]}, format="json"),
        422,
        "VALIDATION_ERROR",
    )


def test_missing_rules_key_is_422(admin_client):
    assert_problem(
        admin_client.put(url(ProviderFactory()), {}, format="json"), 422, "VALIDATION_ERROR"
    )


# --- permissions --------------------------------------------------------------------------


def test_provider_manages_own_schedule(provider_client, own_provider):
    response = provider_client.put(url(own_provider), {"rules": WEEK}, format="json")
    assert response.status_code == 200, response.content
    assert provider_client.get(url(own_provider)).status_code == 200


def test_provider_cannot_touch_other_provider(provider_client, own_provider):
    other = ProviderFactory()
    assert_problem(provider_client.get(url(other)), 403, "FORBIDDEN")
    assert_problem(
        provider_client.put(url(other), {"rules": WEEK}, format="json"), 403, "FORBIDDEN"
    )


def test_edge_35_provider_without_user_is_admin_only(admin_client):
    unlinked = ProviderFactory(user=None)
    stranger = APIClient()
    stranger.force_authenticate(UserFactory(role=User.Role.PROVIDER))
    assert_problem(stranger.get(url(unlinked)), 403, "FORBIDDEN")
    assert admin_client.get(url(unlinked)).status_code == 200


def test_customer_forbidden_anon_unauthenticated(customer_client):
    provider = ProviderFactory()
    assert_problem(customer_client.get(url(provider)), 403, "FORBIDDEN")
    assert_problem(APIClient().get(url(provider)), 401, "AUTH_REQUIRED")


def test_unknown_provider_is_404(admin_client):
    assert_problem(admin_client.get(url(uuid.uuid4())), 404, "NOT_FOUND")


def test_admin_manages_inactive_provider(admin_client):
    provider = ProviderFactory(is_active=False)
    assert admin_client.put(url(provider), {"rules": WEEK}, format="json").status_code == 200
    assert AvailabilityRule.objects.filter(provider=provider).count() == 10
