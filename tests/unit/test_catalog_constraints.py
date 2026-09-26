"""DB-level guarantees: they must hold even when the service layer is bypassed."""

from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.catalog.models import Service
from apps.providers.models import Provider, ProviderService
from tests.factories import ProviderFactory, ServiceFactory

pytestmark = pytest.mark.django_db


def make_service(**overrides):
    fields = {"name": "S", "slug": "s", "duration_minutes": 30, "price": Decimal("1.00")}
    fields.update(overrides)
    return Service.objects.create(**fields)


@pytest.mark.parametrize("minutes", [0, 4, 7, 485, 1000])
def test_service_duration_check(minutes):
    with pytest.raises(IntegrityError):
        make_service(duration_minutes=minutes)


def test_service_price_check():
    with pytest.raises(IntegrityError):
        make_service(price=Decimal("-0.01"))


def test_service_slug_unique():
    make_service()
    with pytest.raises(IntegrityError):
        make_service(name="Other")


def test_provider_color_check():
    with pytest.raises(IntegrityError):
        Provider.objects.create(name="X", color="red")


def test_provider_service_pair_unique():
    service = ServiceFactory()
    provider = ProviderFactory(with_services=[service])
    with pytest.raises(IntegrityError):
        ProviderService.objects.create(provider=provider, service=service)
