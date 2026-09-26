import pytest
from django.db import IntegrityError, connection

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_email_is_stored_lowercase():
    user = User.objects.create_user(email="  Ali.Valiyev@Example.COM ", password="x", full_name="A")
    assert user.email == "ali.valiyev@example.com"


def test_email_uniqueness_is_case_insensitive():
    User.objects.create_user(email="dup@example.com", password="x", full_name="A")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="DUP@example.com", password="x", full_name="B")


def test_db_rejects_uppercase_email_written_around_the_orm():
    user = User.objects.create_user(email="raw@example.com", password="x", full_name="A")
    with pytest.raises(IntegrityError), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE accounts_user SET email = %s WHERE id = %s", ["RAW@example.com", user.id]
        )


def test_create_user_defaults_to_customer():
    user = User.objects.create_user(email="c@example.com", password="x", full_name="C")
    assert user.role == User.Role.CUSTOMER
    assert user.timezone == "Asia/Tashkent"
    assert not user.is_staff and not user.is_superuser


def test_create_superuser_is_admin():
    user = User.objects.create_superuser(email="root@example.com", password="x", full_name="R")
    assert user.role == User.Role.ADMIN
    assert user.is_staff and user.is_superuser


def test_login_lookup_is_case_insensitive():
    User.objects.create_user(email="case@example.com", password="x", full_name="C")
    assert User.objects.get_by_natural_key("CASE@Example.com").email == "case@example.com"
