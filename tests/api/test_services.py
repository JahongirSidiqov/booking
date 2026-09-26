import uuid

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Service
from tests.api.test_auth import assert_problem
from tests.factories import ServiceFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/services"


def detail(service_or_id):
    return f"{URL}/{getattr(service_or_id, 'pk', service_or_id)}"


def payload(**overrides):
    data = {
        "name": "Soch olish",
        "description": "Klassik soch olish",
        "duration_minutes": 30,
        "price": "60000.00",
    }
    data.update(overrides)
    return data


# --- read ---------------------------------------------------------------------------------


def test_anon_lists_active_services_in_sort_order(api_client):
    b = ServiceFactory(name="B", sort_order=2)
    a = ServiceFactory(name="A", sort_order=1)
    ServiceFactory(name="Yopiq", is_active=False)
    body = api_client.get(URL).json()
    assert [s["id"] for s in body] == [str(a.pk), str(b.pk)]
    assert set(body[0]) == {"id", "name", "slug", "description", "duration_minutes", "price"}
    assert body[0]["price"] == "60000.00"


def test_edge_10_inactive_service_hidden_from_public(api_client):
    hidden = ServiceFactory(is_active=False)
    assert str(hidden.pk) not in {s["id"] for s in api_client.get(URL).json()}
    assert_problem(api_client.get(detail(hidden)), 404, "NOT_FOUND")


def test_include_inactive_only_for_admin(api_client, admin_client):
    ServiceFactory(is_active=False)
    ServiceFactory()
    assert len(APIClient().get(URL, {"include_inactive": "1"}).json()) == 1
    body = admin_client.get(URL, {"include_inactive": "1"}).json()
    assert len(body) == 2
    assert "is_active" in body[0]


def test_admin_can_retrieve_inactive(admin_client):
    hidden = ServiceFactory(is_active=False)
    assert admin_client.get(detail(hidden)).json()["is_active"] is False


def test_retrieve_unknown_or_malformed_id_is_404(api_client):
    assert_problem(api_client.get(detail(uuid.uuid4())), 404, "NOT_FOUND")
    assert_problem(api_client.get(detail("not-a-uuid")), 404, "NOT_FOUND")


# --- create -------------------------------------------------------------------------------


def test_admin_creates_service_with_generated_slug(admin_client):
    response = admin_client.post(URL, payload(name="Soqol oʻldirish"), format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["slug"] == "soqol-oldirish"
    assert body["is_active"] is True


def test_generated_slug_is_unique(admin_client):
    admin_client.post(URL, payload(), format="json")
    second = admin_client.post(URL, payload(), format="json").json()
    third = admin_client.post(URL, payload(), format="json").json()
    assert (second["slug"], third["slug"]) == ("soch-olish-2", "soch-olish-3")


def test_explicit_duplicate_slug_is_422(admin_client):
    ServiceFactory(slug="soch-olish")
    body = assert_problem(
        admin_client.post(URL, payload(slug="soch-olish"), format="json"), 422, "VALIDATION_ERROR"
    )
    assert "slug" in body["errors"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_minutes", 7),
        ("duration_minutes", 0),
        ("duration_minutes", 485),
        ("duration_minutes", 3),
        ("price", "-1.00"),
        ("price", "10.555"),
        ("name", "x" * 101),
        ("name", ""),
    ],
)
def test_create_validates_shape(admin_client, field, value):
    body = assert_problem(
        admin_client.post(URL, payload(**{field: value}), format="json"), 422, "VALIDATION_ERROR"
    )
    assert field in body["errors"]


@pytest.mark.parametrize("minutes", [5, 45, 480])
def test_duration_boundaries_accepted(admin_client, minutes):
    response = admin_client.post(URL, payload(duration_minutes=minutes), format="json")
    assert response.status_code == 201


def test_customer_cannot_create(customer_client):
    assert_problem(customer_client.post(URL, payload(), format="json"), 403, "FORBIDDEN")


def test_anon_cannot_create(api_client):
    assert_problem(api_client.post(URL, payload(), format="json"), 401, "AUTH_REQUIRED")


# --- update / delete ----------------------------------------------------------------------


def test_admin_patches_price_and_duration(admin_client):
    service = ServiceFactory()
    response = admin_client.patch(
        detail(service), {"price": "75000.00", "duration_minutes": 45}, format="json"
    )
    assert response.status_code == 200, response.content
    service.refresh_from_db()
    assert (str(service.price), service.duration_minutes) == ("75000.00", 45)


def test_patch_keeps_slug_when_name_changes(admin_client):
    service = ServiceFactory(slug="soch-olish")
    admin_client.patch(detail(service), {"name": "Yangi nom"}, format="json")
    service.refresh_from_db()
    assert service.slug == "soch-olish"


def test_put_is_not_allowed(admin_client):
    assert_problem(
        admin_client.put(detail(ServiceFactory()), payload(), format="json"),
        405,
        "METHOD_NOT_ALLOWED",
    )


def test_delete_deactivates_instead_of_deleting(admin_client):
    service = ServiceFactory()
    assert admin_client.delete(detail(service)).status_code == 204
    service.refresh_from_db()
    assert service.is_active is False
    assert str(service.pk) not in {s["id"] for s in APIClient().get(URL).json()}


def test_admin_can_reactivate(admin_client):
    service = ServiceFactory(is_active=False)
    admin_client.patch(detail(service), {"is_active": True}, format="json")
    service.refresh_from_db()
    assert service.is_active is True


def test_customer_cannot_delete(customer_client):
    service = ServiceFactory()
    assert_problem(customer_client.delete(detail(service)), 403, "FORBIDDEN")
    assert Service.objects.get(pk=service.pk).is_active


def test_patch_to_taken_slug_is_422(admin_client):
    ServiceFactory(slug="band")
    service = ServiceFactory()
    body = assert_problem(
        admin_client.patch(detail(service), {"slug": "band"}, format="json"),
        422,
        "VALIDATION_ERROR",
    )
    assert "slug" in body["errors"]


def test_patch_blank_slug_regenerates_from_name(admin_client):
    service = ServiceFactory(name="Soch olish", slug="eski")
    admin_client.patch(detail(service), {"slug": ""}, format="json")
    service.refresh_from_db()
    assert service.slug == "soch-olish"
