import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser_client(client):
    user = User.objects.create_superuser(email="root@example.com", password="x", full_name="Root")
    client.force_login(user)
    return client


def test_admin_user_pages_render(superuser_client):
    user = User.objects.create_user(email="c@example.com", password="x", full_name="C")
    assert superuser_client.get("/django-admin/accounts/user/").status_code == 200
    assert superuser_client.get("/django-admin/accounts/user/add/").status_code == 200
    assert superuser_client.get(f"/django-admin/accounts/user/{user.pk}/change/").status_code == 200


def test_admin_creates_user_with_lowercase_email(superuser_client):
    response = superuser_client.post(
        "/django-admin/accounts/user/add/",
        {
            "email": "Yangi.Xodim@Example.com",
            "full_name": "Yangi Xodim",
            "role": "provider",
            "password1": "Kuchli-Parol-77",
            "password2": "Kuchli-Parol-77",
        },
    )
    assert response.status_code == 302, response.content
    user = User.objects.get(email="yangi.xodim@example.com")
    assert user.role == User.Role.PROVIDER
    assert user.check_password("Kuchli-Parol-77")
