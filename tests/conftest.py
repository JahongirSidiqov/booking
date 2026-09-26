import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.factories import DEFAULT_PASSWORD, UserFactory


@pytest.fixture(autouse=True)
def _clear_cache():
    # Throttle counters live in the cache; without this, one test's requests throttle the next.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    return DEFAULT_PASSWORD


@pytest.fixture
def customer(db):
    return UserFactory(role=User.Role.CUSTOMER)


@pytest.fixture
def admin_user(db):
    return UserFactory(role=User.Role.ADMIN)


@pytest.fixture
def auth_client(api_client, customer, password):
    response = api_client.post(
        "/api/v1/auth/token", {"email": customer.email, "password": password}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    api_client.user = customer
    return api_client
