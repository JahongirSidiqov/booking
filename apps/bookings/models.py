from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q

from apps.common.models import BaseModel

ACTIVE_STATUSES = ("pending", "confirmed")


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = models.DateTimeField()


class Booking(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        CONFIRMED = "confirmed", "Tasdiqlangan"
        CANCELLED = "cancelled", "Bekor qilingan"
        COMPLETED = "completed", "Bajarilgan"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings"
    )
    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.PROTECT, related_name="bookings"
    )
    service = models.ForeignKey(
        "catalog.Service", on_delete=models.PROTECT, related_name="bookings"
    )
    start_at = models.DateTimeField("boshlanishi")
    end_at = models.DateTimeField("tugashi")
    # Only apps/bookings/services.py may change this field (enforced by tests/test_architecture.py).
    status = models.CharField(
        "holat", max_length=16, choices=Status.choices, default=Status.PENDING
    )

    # Snapshot of the service at booking time: later price/duration edits never rewrite history.
    service_name = models.CharField("xizmat nomi", max_length=100)
    duration_minutes = models.PositiveSmallIntegerField("davomiyligi (daqiqa)")
    price = models.DecimalField("narxi", max_digits=12, decimal_places=2)
    buffer_minutes = models.PositiveSmallIntegerField("tanaffus (daqiqa)", default=0)
    # The provider is busy until here (end_at + buffer). The provider exclusion constraint uses
    # this bound; the customer's appointment and their own constraint still end at end_at.
    blocked_until = models.DateTimeField("xodim band (tanaffus bilan)")

    customer_note = models.CharField("mijoz izohi", max_length=500, blank=True)
    internal_note = models.TextField("ichki izoh", blank=True)

    cancelled_at = models.DateTimeField("bekor qilingan vaqt", null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    cancel_reason = models.CharField("bekor qilish sababi", max_length=500, blank=True)

    idempotency_key = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    # sha256 of the create payload: same key + different payload is a client bug, not a retry.
    idempotency_fingerprint = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "bron"
        verbose_name_plural = "bronlar"
        ordering = ["-start_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_at__lt=F("end_at")), name="booking_start_before_end"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "confirmed", "cancelled", "completed"]),
                name="booking_status_valid",
            ),
            # Last line of defence against double booking. The provider row lock in
            # create_booking makes races wait and fail politely; this constraint guarantees
            # correctness for every other write path (admin, shell, future bugs).
            # Default range bounds are "[)", so 10:00–10:30 and 10:30–11:00 do not overlap.
            models.CheckConstraint(
                condition=Q(blocked_until__gte=F("end_at")), name="booking_blocked_after_end"
            ),
            ExclusionConstraint(
                name="no_overlap_per_provider",
                expressions=[
                    (F("provider"), RangeOperators.EQUAL),
                    (
                        TsTzRange("start_at", "blocked_until", RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status__in=ACTIVE_STATUSES),
            ),
            ExclusionConstraint(
                name="no_overlap_per_customer",
                expressions=[
                    (F("customer"), RangeOperators.EQUAL),
                    (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=ACTIVE_STATUSES),
            ),
            models.UniqueConstraint(
                fields=["customer", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_idempotency_per_customer",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "start_at"], name="booking_provider_start_idx"),
            models.Index(fields=["customer", "-start_at"], name="booking_customer_start_idx"),
            models.Index(fields=["status", "start_at"], name="booking_status_start_idx"),
        ]

    def __str__(self):
        return f"{self.service_name} · {self.start_at:%Y-%m-%d %H:%M}Z · {self.status}"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_status = instance.status
        return instance

    def save(self, *args, **kwargs):
        if self.blocked_until is None and self.end_at is not None:
            self.blocked_until = self.end_at + timedelta(minutes=self.buffer_minutes or 0)
        # A status change outside bookings.services would skip guards and history; the
        # service marks its own changes with _status_change_allowed.
        loaded = getattr(self, "_loaded_status", None)
        if (
            not self._state.adding
            and loaded is not None
            and loaded != self.status
            and not getattr(self, "_status_change_allowed", False)
        ):
            raise StatusChangeError(
                "Booking.status faqat apps.bookings.services orqali oʻzgartiriladi."
            )
        super().save(*args, **kwargs)
        self._loaded_status = self.status
        self._status_change_allowed = False


class StatusChangeError(Exception):
    pass


class ImmutableHistoryError(Exception):
    pass


class BookingStatusHistoryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableHistoryError("Status tarixi oʻzgartirilmaydi.")

    def delete(self):
        raise ImmutableHistoryError("Status tarixi oʻchirilmaydi.")


class BookingStatusHistory(models.Model):
    """Append-only audit trail: who changed the status, when and why."""

    id = models.BigAutoField(primary_key=True)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="history")
    from_status = models.CharField(max_length=16, null=True, blank=True)  # noqa: DJ001
    to_status = models.CharField(max_length=16)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BookingStatusHistoryQuerySet.as_manager()

    class Meta:
        verbose_name = "status tarixi"
        verbose_name_plural = "status tarixi"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["booking", "created_at"])]

    def __str__(self):
        return f"{self.from_status} → {self.to_status}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableHistoryError("Status tarixi oʻzgartirilmaydi.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableHistoryError("Status tarixi oʻchirilmaydi.")
