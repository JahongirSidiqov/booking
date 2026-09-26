import pytest
from django.conf import settings
from django.db import connection


def test_settings_use_utc_storage():
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == "UTC"


def test_database_engine_is_postgresql():
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


@pytest.mark.django_db
def test_database_accepts_queries():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
