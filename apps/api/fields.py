from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


class AwareDateTimeField(serializers.DateTimeField):
    """ISO 8601 datetime that must carry an explicit UTC offset.

    A naive value would silently be read as server time (UTC) and shift the appointment by
    the client's offset, so it is rejected instead of guessed (ADR-009).
    """

    default_error_messages = {
        "naive": "Vaqtni UTC offset bilan kiriting, masalan 2026-10-01T09:00:00+05:00.",
    }

    def to_internal_value(self, value):
        if isinstance(value, str):
            try:
                parsed = parse_datetime(value.strip())
            except ValueError:
                parsed = None
            if parsed is not None and timezone.is_naive(parsed):
                self.fail("naive")
        return super().to_internal_value(value)
