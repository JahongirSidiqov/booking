import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.api.fields import AwareDateTimeField
from apps.bookings.models import Booking
from apps.common.utils.time import validate_timezone

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def utc_z(moment) -> str | None:
    return moment.isoformat().replace("+00:00", "Z") if moment else None


def validate_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    if not IDEMPOTENCY_KEY_RE.match(raw):
        raise serializers.ValidationError(
            {"Idempotency-Key": ["1–64 belgi: harf, raqam, . _ : - (masalan UUID)."]}
        )
    return raw


# --- input --------------------------------------------------------------------------------


class BookingCreateSerializer(serializers.Serializer):
    service_id = serializers.UUIDField()
    provider_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Boʻlmasa yoki null — istalgan boʻsh xodim (oʻsha kuni eng kam band).",
    )
    start_at = AwareDateTimeField(help_text="ISO 8601, offset majburiy: 2026-10-01T09:00:00+05:00")
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default="",
        help_text="Xodim yoki admin bekor qilganda majburiy.",
    )


class StatusListField(serializers.CharField):
    """Comma-separated statuses: ?status=pending,confirmed."""

    def to_internal_value(self, data):
        values = [v.strip() for v in super().to_internal_value(data).split(",") if v.strip()]
        unknown = sorted(set(values) - set(Booking.Status.values))
        if unknown:
            raise serializers.ValidationError(f"Nomaʼlum status: {', '.join(unknown)}.")
        return values


class BookingFilterSerializer(serializers.Serializer):
    status = StatusListField(required=False)
    provider = serializers.UUIDField(required=False)
    service = serializers.UUIDField(required=False)
    upcoming = serializers.BooleanField(required=False, default=False)
    tz = serializers.CharField(max_length=64, required=False, validators=[validate_timezone])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # "from" is a Python keyword, so these fields cannot be declared as attributes.
        self.fields["from"] = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
        self.fields["to"] = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])

    def validate(self, attrs):
        if attrs.get("from") and attrs.get("to") and attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": ["'to' sanasi 'from' dan oldin boʻlmasin."]})
        return attrs


# --- output -------------------------------------------------------------------------------


class _ServiceSnapshotSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="service_id")
    name = serializers.CharField(source="service_name")


class _ProviderRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class _CustomerRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()


class HistoryEntrySerializer(serializers.Serializer):
    to = serializers.CharField(source="to_status")
    by = serializers.SerializerMethodField(help_text="Kim oʻzgartirdi: rol yoki 'system'.")
    reason = serializers.CharField()
    at = serializers.DateTimeField(source="created_at")

    def get_fields(self):
        fields = super().get_fields()
        fields["from"] = serializers.CharField(source="from_status", allow_null=True)
        return {name: fields[name] for name in ("from", "to", "by", "reason", "at")}

    def get_by(self, obj) -> str:
        return obj.changed_by.role if obj.changed_by else "system"


class BookingSerializer(serializers.Serializer):
    """Booking as every endpoint returns it (TASK 6.4). Context: `tz`, `business`."""

    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=Booking.Status.choices)
    service = _ServiceSnapshotSerializer(source="*")
    provider = _ProviderRefSerializer()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    start_at_local = serializers.SerializerMethodField()
    end_at_local = serializers.SerializerMethodField()
    timezone = serializers.SerializerMethodField()
    duration_minutes = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.SerializerMethodField()
    customer = _CustomerRefSerializer()
    customer_note = serializers.CharField()
    can_cancel_until = serializers.SerializerMethodField(
        help_text="Mijoz shu vaqtgacha bekor qila oladi (bekor qilish siyosati)."
    )
    cancelled_at = serializers.DateTimeField(allow_null=True)
    cancel_reason = serializers.CharField()
    created_at = serializers.DateTimeField()
    history = HistoryEntrySerializer(many=True)

    def _zone(self) -> ZoneInfo:
        return ZoneInfo(self.context["tz"])

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_start_at_local(self, obj) -> str:
        return obj.start_at.astimezone(self._zone()).isoformat()

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_end_at_local(self, obj) -> str:
        return obj.end_at.astimezone(self._zone()).isoformat()

    def get_timezone(self, obj) -> str:
        return self.context["tz"]

    def get_currency(self, obj) -> str:
        return self.context["business"].currency

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_can_cancel_until(self, obj) -> str:
        hours = self.context["business"].cancellation_deadline_hours
        return utc_z(obj.start_at - timedelta(hours=hours))


class _UpcomingBookingSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    start_at = serializers.DateTimeField()
    status = serializers.CharField()
    service_name = serializers.CharField()
    provider_id = serializers.UUIDField()


class DeactivationSerializer(serializers.Serializer):
    """DELETE response: the resource is deactivated, its future bookings are kept (edge #25)."""

    id = serializers.UUIDField(source="obj.pk")
    is_active = serializers.BooleanField(source="obj.is_active")
    upcoming_bookings_count = serializers.SerializerMethodField()
    upcoming_bookings = _UpcomingBookingSerializer(many=True)

    def get_upcoming_bookings_count(self, data) -> int:
        return len(data["upcoming_bookings"])


def deactivation_payload(obj, upcoming) -> dict:
    return DeactivationSerializer({"obj": obj, "upcoming_bookings": upcoming}).data
