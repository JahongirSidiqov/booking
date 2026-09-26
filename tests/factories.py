import factory

from apps.accounts.models import User

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
