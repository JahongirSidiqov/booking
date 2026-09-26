from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Mod
from django.db.models.lookups import Exact

from apps.common.models import BaseModel

DURATION_MIN = 5
DURATION_MAX = 480
DURATION_STEP = 5
BUFFER_MAX = 120


class Service(BaseModel):
    """Never hard-deleted: bookings keep pointing at it, so it is only deactivated."""

    name = models.CharField("nomi", max_length=100)
    slug = models.SlugField("slug", max_length=120, unique=True)
    description = models.TextField("tavsif", blank=True)
    duration_minutes = models.PositiveSmallIntegerField("davomiyligi (daqiqa)")
    price = models.DecimalField("narxi", max_digits=12, decimal_places=2)
    # Time the provider stays busy after each booking (cleanup, preparation). Not part of the
    # customer's appointment: their end time and overlap rules ignore it.
    buffer_after_minutes = models.PositiveSmallIntegerField("tanaffus (daqiqa)", default=0)
    is_active = models.BooleanField("faol", default=True)
    sort_order = models.PositiveIntegerField("tartib", default=0)

    class Meta:
        verbose_name = "xizmat"
        verbose_name_plural = "xizmatlar"
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=DURATION_MIN, duration_minutes__lte=DURATION_MAX),
                name="service_duration_range",
            ),
            models.CheckConstraint(
                condition=Exact(Mod(F("duration_minutes"), DURATION_STEP), 0),
                name="service_duration_step",
            ),
            models.CheckConstraint(condition=Q(price__gte=0), name="service_price_non_negative"),
            models.CheckConstraint(
                condition=Q(buffer_after_minutes__lte=BUFFER_MAX)
                & Exact(Mod(F("buffer_after_minutes"), DURATION_STEP), 0),
                name="service_buffer_range_step",
            ),
        ]
        indexes = [models.Index(fields=["is_active", "sort_order"])]

    def __str__(self):
        return self.name
