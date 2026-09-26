import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from rest_framework import serializers

from apps.api.fields import AwareDateTimeField
from apps.bookings.models import Booking

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def utc_z(moment) -> str | None:
    return moment.isoformat().replace("+00:00", "Z") if moment else None


class BookingCreateSerializer(serializers.Serializer):
    service_id = serializers.UUIDField()
    provider_id = serializers.UUIDField()
    start_at = AwareDateTimeField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


def validate_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    if not IDEMPOTENCY_KEY_RE.match(raw):
        raise serializers.ValidationError(
            {"Idempotency-Key": ["1–64 belgi: harf, raqam, . _ : - (masalan UUID)."]}
        )
    return raw


def history_entry(item) -> dict:
    actor = item.changed_by
    return {
        "from": item.from_status,
        "to": item.to_status,
        "by": actor.role if actor else "system",
        "reason": item.reason,
        "at": utc_z(item.created_at),
    }


def booking_payload(booking: Booking, *, tz: str, business) -> dict:
    """Booking representation shared by every booking endpoint (TASK 6.4)."""
    zone = ZoneInfo(tz)
    deadline = timedelta(hours=business.cancellation_deadline_hours)
    return {
        "id": str(booking.pk),
        "status": booking.status,
        "service": {"id": str(booking.service_id), "name": booking.service_name},
        "provider": {"id": str(booking.provider_id), "name": booking.provider.name},
        "start_at": utc_z(booking.start_at),
        "end_at": utc_z(booking.end_at),
        "start_at_local": booking.start_at.astimezone(zone).isoformat(),
        "end_at_local": booking.end_at.astimezone(zone).isoformat(),
        "timezone": tz,
        "duration_minutes": booking.duration_minutes,
        "price": f"{booking.price:.2f}",
        "currency": business.currency,
        "customer": {"id": str(booking.customer_id), "full_name": booking.customer.full_name},
        "customer_note": booking.customer_note,
        "can_cancel_until": utc_z(booking.start_at - deadline),
        "cancelled_at": utc_z(booking.cancelled_at),
        "cancel_reason": booking.cancel_reason,
        "created_at": utc_z(booking.created_at),
        "history": [history_entry(h) for h in booking.history.all()],
    }


def deactivation_payload(obj, upcoming) -> dict:
    """DELETE response: the resource is deactivated, its future bookings are kept (edge #25)."""
    return {
        "id": str(obj.pk),
        "is_active": obj.is_active,
        "upcoming_bookings_count": len(upcoming),
        "upcoming_bookings": [
            {
                "id": str(b.pk),
                "start_at": utc_z(b.start_at),
                "status": b.status,
                "service_name": b.service_name,
                "provider_id": str(b.provider_id),
            }
            for b in upcoming
        ],
    }
