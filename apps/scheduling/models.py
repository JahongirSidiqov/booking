from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.common.models import BaseModel
from apps.common.utils.time import validate_timezone

SLOT_STEP_CHOICES = [(m, f"{m} daqiqa") for m in (5, 10, 15, 20, 30, 60)]


class AvailabilityRule(BaseModel):
    """Weekly recurring working window in the provider's local time.

    Stored as local wall-clock time (not UTC) on purpose: "09:00 every Monday" must stay
    09:00 across DST changes, so conversion to UTC happens per concrete date.
    """

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Dushanba"
        TUESDAY = 1, "Seshanba"
        WEDNESDAY = 2, "Chorshanba"
        THURSDAY = 3, "Payshanba"
        FRIDAY = 4, "Juma"
        SATURDAY = 5, "Shanba"
        SUNDAY = 6, "Yakshanba"

    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.CASCADE, related_name="availability_rules"
    )
    weekday = models.PositiveSmallIntegerField("hafta kuni", choices=Weekday.choices)
    start_time = models.TimeField("boshlanishi")
    end_time = models.TimeField("tugashi")

    class Meta:
        verbose_name = "ish vaqti qoidasi"
        verbose_name_plural = "ish vaqti qoidalari"
        ordering = ["weekday", "start_time"]
        constraints = [
            # Shifts crossing midnight are out of scope for v1 (ADR-004).
            models.CheckConstraint(
                condition=Q(start_time__lt=F("end_time")), name="rule_start_before_end"
            ),
            models.CheckConstraint(
                condition=Q(weekday__gte=0, weekday__lte=6), name="rule_weekday_range"
            ),
        ]
        indexes = [models.Index(fields=["provider", "weekday"])]

    def __str__(self):
        return f"{self.provider} {self.get_weekday_display()} {self.start_time}–{self.end_time}"


class TimeOff(BaseModel):
    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.CASCADE, related_name="time_offs"
    )
    start_at = models.DateTimeField("boshlanishi")
    end_at = models.DateTimeField("tugashi")
    reason = models.CharField("sabab", max_length=200, blank=True)

    class Meta:
        verbose_name = "dam olish"
        verbose_name_plural = "dam olishlar"
        ordering = ["start_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_at__lt=F("end_at")), name="timeoff_start_before_end"
            ),
        ]
        indexes = [models.Index(fields=["provider", "start_at"])]

    def __str__(self):
        return f"{self.provider} {self.start_at:%Y-%m-%d %H:%M}–{self.end_at:%Y-%m-%d %H:%M}"


class BusinessSettings(BaseModel):
    """Single row (pk=1): the whole installation serves one business (ADR-001)."""

    SINGLETON_PK = 1

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_PK, editable=False)
    name = models.CharField("biznes nomi", max_length=120, default="Navbat Barbershop")
    timezone = models.CharField(
        "vaqt zonasi", max_length=64, default=settings.DEFAULT_TZ, validators=[validate_timezone]
    )
    currency = models.CharField("valyuta", max_length=3, default="UZS")
    slot_step_minutes = models.PositiveSmallIntegerField(
        "slot qadami (daqiqa)", choices=SLOT_STEP_CHOICES, default=15
    )
    min_lead_time_minutes = models.PositiveIntegerField("eng kam oldindan (daqiqa)", default=60)
    max_advance_days = models.PositiveSmallIntegerField("eng koʻp oldindan (kun)", default=30)
    cancellation_deadline_hours = models.PositiveSmallIntegerField(
        "bekor qilish muddati (soat)", default=24
    )
    auto_confirm = models.BooleanField("avtomatik tasdiqlash", default=False)

    class Meta:
        verbose_name = "biznes sozlamalari"
        verbose_name_plural = "biznes sozlamalari"
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="settings_singleton"),
            models.CheckConstraint(
                condition=Q(slot_step_minutes__in=[m for m, _ in SLOT_STEP_CHOICES]),
                name="settings_slot_step_choices",
            ),
            models.CheckConstraint(
                condition=Q(max_advance_days__gte=1, max_advance_days__lte=365),
                name="settings_max_advance_range",
            ),
            models.CheckConstraint(
                condition=Q(min_lead_time_minutes__lte=60 * 24 * 7),
                name="settings_lead_time_max_week",
            ),
            models.CheckConstraint(
                condition=Q(cancellation_deadline_hours__lte=24 * 14),
                name="settings_deadline_max_two_weeks",
            ),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def load(cls) -> "BusinessSettings":
        # Created lazily rather than in a data migration: TransactionTestCase flushes tables,
        # and a fresh install must work before an admin ever opens the settings page.
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
