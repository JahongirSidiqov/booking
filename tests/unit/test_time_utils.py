import pytest
from django.core.exceptions import ValidationError

from apps.common.utils.time import is_valid_timezone, validate_timezone


@pytest.mark.parametrize("name", ["Asia/Tashkent", "Asia/Dubai", "Europe/Berlin", "UTC"])
def test_valid_iana_names_accepted(name):
    assert is_valid_timezone(name)
    validate_timezone(name)


@pytest.mark.parametrize("name", ["Asia/Toshkent", "Tashkent", "", "+05:00", "asia/tashkent"])
def test_edge_28_invalid_timezone_rejected(name):
    assert not is_valid_timezone(name)
    with pytest.raises(ValidationError):
        validate_timezone(name)
