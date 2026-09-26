from datetime import time
from decimal import Decimal

import factory

from apps.accounts.models import User
from apps.catalog.models import Service
from apps.providers.models import Provider
from apps.scheduling.models import AvailabilityRule

DEFAULT_PASSWORD = "Navbat-Test-2026"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    role = User.Role.CUSTOMER
    timezone = "Asia/Tashkent"
    password = factory.PostGenerationMethodCall("set_password", DEFAULT_PASSWORD)

    @factory.post_generation
    def _persist_password(obj, create, extracted, **kwargs):
        if create:
            obj.save(update_fields=["password"])


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    name = factory.Sequence(lambda n: f"Xizmat {n}")
    slug = factory.Sequence(lambda n: f"xizmat-{n}")
    description = ""
    duration_minutes = 30
    price = Decimal("60000.00")
    is_active = True


class ProviderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Provider
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Xodim {n}")
    color = "#2563EB"
    is_active = True

    @factory.post_generation
    def with_services(obj, create, extracted, **kwargs):
        if create and extracted:
            obj.services.add(*extracted)


class AvailabilityRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AvailabilityRule

    provider = factory.SubFactory(ProviderFactory)
    weekday = 0
    start_time = time(9, 0)
    end_time = time(18, 0)
