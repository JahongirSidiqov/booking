import uuid

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.providers.models import Provider
from tests.api.test_auth import assert_problem
from tests.factories import ProviderFactory, ServiceFactory, UserFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/providers"


def detail(provider_or_id, suffix=""):
    return f"{URL}/{getattr(provider_or_id, 'pk', provider_or_id)}{suffix}"


# --- read ---------------------------------------------------------------------------------


def test_anon_lists_active_providers_with_active_services(api_client):
    haircut = ServiceFactory(name="Soch olish")
    retired = ServiceFactory(name="Eski xizmat", is_active=False)
    sardor = ProviderFactory(name="Sardor", with_services=[haircut, retired])
    ProviderFactory(name="Ketgan", is_active=False)

    body = api_client.get(URL).json()
    assert [p["id"] for p in body] == [str(sardor.pk)]
    assert set(body[0]) == {"id", "name", "bio", "color", "services"}
    assert [s["id"] for s in body[0]["services"]] == [str(haircut.pk)]


def test_filter_by_service(api_client):
    haircut, beard = ServiceFactory(), ServiceFactory()
    a = ProviderFactory(with_services=[haircut])
    ProviderFactory(with_services=[beard])
    ProviderFactory(with_services=[haircut], is_active=False)

    body = api_client.get(URL, {"service": str(haircut.pk)}).json()
    assert [p["id"] for p in body] == [str(a.pk)]


def test_edge_10_filter_by_inactive_service_is_empty(api_client):
    retired = ServiceFactory(is_active=False)
    ProviderFactory(with_services=[retired])
    assert api_client.get(URL, {"service": str(retired.pk)}).json() == []


def test_filter_with_malformed_service_id_is_422(api_client):
    body = assert_problem(api_client.get(URL, {"service": "abc"}), 422, "VALIDATION_ERROR")
    assert "service" in body["errors"]


def test_edge_10_inactive_provider_is_404_for_public(api_client, admin_client):
    gone = ProviderFactory(is_active=False)
    assert_problem(APIClient().get(detail(gone)), 404, "NOT_FOUND")
    assert admin_client.get(detail(gone)).json()["is_active"] is False


# --- create / update ----------------------------------------------------------------------


def test_admin_creates_provider_with_services_and_user(admin_client):
    haircut = ServiceFactory()
    staff = UserFactory(role=User.Role.PROVIDER)
    response = admin_client.post(
        URL,
        {
            "name": "Jasur",
            "bio": "12 yil tajriba",
            "color": "#16A34A",
            "timezone": "Asia/Tashkent",
            "user_id": str(staff.pk),
            "service_ids": [str(haircut.pk)],
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["user_id"] == str(staff.pk)
    assert [s["id"] for s in body["services"]] == [str(haircut.pk)]
    assert Provider.objects.get(pk=body["id"]).user == staff


def test_provider_without_user_and_timezone(admin_client):
    response = admin_client.post(URL, {"name": "Akmal"}, format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["user_id"] is None
    assert body["timezone"] is None
    assert body["color"] == "#2563EB"


def test_linking_customer_user_is_rejected(admin_client, customer):
    body = assert_problem(
        admin_client.post(URL, {"name": "X", "user_id": str(customer.pk)}, format="json"),
        422,
        "VALIDATION_ERROR",
    )
    assert "user_id" in body["errors"]


def test_user_cannot_be_linked_to_two_providers(admin_client):
    staff = UserFactory(role=User.Role.PROVIDER)
    ProviderFactory(user=staff)
    assert_problem(
        admin_client.post(URL, {"name": "X", "user_id": str(staff.pk)}, format="json"),
        422,
        "VALIDATION_ERROR",
    )


def test_unknown_user_is_rejected(admin_client):
    assert_problem(
        admin_client.post(URL, {"name": "X", "user_id": str(uuid.uuid4())}, format="json"),
        422,
        "VALIDATION_ERROR",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("color", "blue"), ("color", "#12345"), ("timezone", "Asia/Toshkent"), ("name", "")],
)
def test_create_validates_shape(admin_client, field, value):
    body = assert_problem(
        admin_client.post(URL, {"name": "X", field: value}, format="json"),
        422,
        "VALIDATION_ERROR",
    )
    assert field in body["errors"]


def test_create_with_unknown_service_is_422(admin_client):
    body = assert_problem(
        admin_client.post(URL, {"name": "X", "service_ids": [str(uuid.uuid4())]}, format="json"),
        422,
        "VALIDATION_ERROR",
    )
    assert "service_ids" in body["errors"]
    assert not Provider.objects.exists()


def test_patch_can_unlink_user(admin_client):
    staff = UserFactory(role=User.Role.PROVIDER)
    provider = ProviderFactory(user=staff)
    response = admin_client.patch(detail(provider), {"user_id": None}, format="json")
    assert response.status_code == 200, response.content
    provider.refresh_from_db()
    assert provider.user is None


def test_patch_keeps_own_user_link(admin_client):
    staff = UserFactory(role=User.Role.PROVIDER)
    provider = ProviderFactory(user=staff)
    response = admin_client.patch(
        detail(provider), {"user_id": str(staff.pk), "name": "Yangi"}, format="json"
    )
    assert response.status_code == 200, response.content


def test_customer_and_provider_roles_cannot_write(api_client):
    for role in (User.Role.CUSTOMER, User.Role.PROVIDER):
        client = APIClient()
        client.force_authenticate(UserFactory(role=role))
        assert_problem(client.post(URL, {"name": "X"}, format="json"), 403, "FORBIDDEN")


# --- services replacement -----------------------------------------------------------------


def test_put_services_replaces_whole_list(admin_client):
    a, b, c = ServiceFactory(), ServiceFactory(), ServiceFactory()
    provider = ProviderFactory(with_services=[a, b])
    response = admin_client.put(
        detail(provider, "/services"), {"service_ids": [str(b.pk), str(c.pk)]}, format="json"
    )
    assert response.status_code == 200, response.content
    assert set(provider.services.values_list("pk", flat=True)) == {b.pk, c.pk}


def test_put_services_empty_list_clears(admin_client):
    provider = ProviderFactory(with_services=[ServiceFactory()])
    admin_client.put(detail(provider, "/services"), {"service_ids": []}, format="json")
    assert not provider.services.exists()


def test_put_services_unknown_id_changes_nothing(admin_client):
    a = ServiceFactory()
    provider = ProviderFactory(with_services=[a])
    assert_problem(
        admin_client.put(
            detail(provider, "/services"),
            {"service_ids": [str(uuid.uuid4())]},
            format="json",
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert list(provider.services.all()) == [a]


def test_put_services_forbidden_for_customer(customer_client):
    provider = ProviderFactory()
    assert_problem(
        customer_client.put(detail(provider, "/services"), {"service_ids": []}, format="json"),
        403,
        "FORBIDDEN",
    )


def test_put_services_duplicate_ids_are_collapsed(admin_client):
    a = ServiceFactory()
    provider = ProviderFactory()
    admin_client.put(
        detail(provider, "/services"), {"service_ids": [str(a.pk), str(a.pk)]}, format="json"
    )
    assert provider.services.count() == 1


# --- delete -------------------------------------------------------------------------------


def test_delete_deactivates_provider(admin_client):
    provider = ProviderFactory()
    assert admin_client.delete(detail(provider)).status_code == 204
    provider.refresh_from_db()
    assert provider.is_active is False
