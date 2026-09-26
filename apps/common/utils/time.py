from functools import lru_cache
from zoneinfo import available_timezones

from django.core.exceptions import ValidationError


@lru_cache(maxsize=1)
def _iana_zones() -> frozenset[str]:
    # available_timezones() scans the tz database on every call.
    return frozenset(available_timezones())


def is_valid_timezone(name: str) -> bool:
    return bool(name) and name in _iana_zones()


def validate_timezone(value: str) -> None:
    if not is_valid_timezone(value):
        raise ValidationError(
            "Notoʻgʻri vaqt zonasi. IANA nomini kiriting, masalan Asia/Tashkent.",
            code="invalid_timezone",
        )
