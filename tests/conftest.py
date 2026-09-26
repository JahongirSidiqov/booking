# rest_framework.throttling is imported eagerly on purpose: SimpleRateThrottle stores
# `timer = time.time` at class creation. If the module is first imported inside a freezegun
# block, it captures freezegun's fake function, which then gets bound as a method and breaks
# every throttled request.
import pytest
import rest_framework.throttling  # noqa: F401
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.factories import DEFAULT_PASSWORD, ProviderFactory, UserFactory


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


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    api_client.user = admin_user
    return api_client


@pytest.fixture
def customer_client(api_client, customer):
    api_client.force_authenticate(customer)
    api_client.user = customer
    return api_client


@pytest.fixture
def provider_user(db):
    return UserFactory(role=User.Role.PROVIDER)


@pytest.fixture
def own_provider(provider_user):
    return ProviderFactory(user=provider_user)


@pytest.fixture
def provider_client(api_client, provider_user):
    api_client.force_authenticate(provider_user)
    api_client.user = provider_user
    return api_client
