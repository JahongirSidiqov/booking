import pytest
from rest_framework.test import APIClient

from apps.scheduling.models import BusinessSettings
from tests.api.test_auth import assert_problem

pytestmark = pytest.mark.django_db

URL = "/api/v1/settings"

PUBLIC = {
    "name",
    "timezone",
    "currency",
    "slot_step_minutes",
    "min_lead_time_minutes",
    "max_advance_days",
    "cancellation_deadline_hours",
}


def test_anon_sees_public_defaults(api_client):
    body = api_client.get(URL).json()
    assert set(body) == PUBLIC
    assert body["timezone"] == "Asia/Tashkent"
    assert body["slot_step_minutes"] == 15
    assert body["min_lead_time_minutes"] == 60
    assert body["max_advance_days"] == 30
    assert body["cancellation_deadline_hours"] == 24
    assert BusinessSettings.objects.count() == 1


def test_admin_sees_full_settings(admin_client):
    body = admin_client.get(URL).json()
    assert set(body) == PUBLIC | {"auto_confirm", "updated_at"}
    assert body["auto_confirm"] is False


def test_admin_patches_settings(admin_client):
    response = admin_client.patch(
        URL,
        {"slot_step_minutes": 30, "auto_confirm": True, "timezone": "Asia/Dubai"},
        format="json",
    )
    assert response.status_code == 200, response.content
    obj = BusinessSettings.load()
    assert (obj.slot_step_minutes, obj.auto_confirm, obj.timezone) == (30, True, "Asia/Dubai")
    assert BusinessSettings.objects.count() == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slot_step_minutes", 7),
        ("timezone", "Asia/Toshkent"),
        ("max_advance_days", 0),
        ("max_advance_days", 400),
        ("min_lead_time_minutes", -5),
        ("cancellation_deadline_hours", 1000),
        ("currency", "sum"),
    ],
)
def test_patch_validation(admin_client, field, value):
    body = assert_problem(
        admin_client.patch(URL, {field: value}, format="json"), 422, "VALIDATION_ERROR"
    )
    assert field in body["errors"]


def test_customer_cannot_patch(customer_client):
    assert_problem(
        customer_client.patch(URL, {"auto_confirm": True}, format="json"), 403, "FORBIDDEN"
    )


def test_anon_cannot_patch():
    assert_problem(
        APIClient().patch(URL, {"auto_confirm": True}, format="json"), 401, "AUTH_REQUIRED"
    )
