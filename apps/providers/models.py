from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel
from apps.common.utils.time import validate_timezone

HEX_COLOR_RE = r"^#[0-9A-Fa-f]{6}$"
color_validator = RegexValidator(HEX_COLOR_RE, "Rang #RRGGBB koʻrinishida boʻlishi kerak.")


class Provider(BaseModel):
    """A staff member. `user` is optional: a provider may never log in and be managed by admin."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider",
    )
    name = models.CharField("ismi", max_length=100)
    bio = models.TextField("bio", blank=True)
    color = models.CharField(
        "kalendar rangi", max_length=7, default="#2563EB", validators=[color_validator]
    )
    is_active = models.BooleanField("faol", default=True)
    # NULL means "use the business timezone", resolved when schedules are interpreted;
    # an empty string would be ambiguous with "not validated yet".
    timezone = models.CharField(  # noqa: DJ001
        "vaqt zonasi", max_length=64, null=True, blank=True, validators=[validate_timezone]
    )
    services = models.ManyToManyField(
        "catalog.Service", through="ProviderService", related_name="providers", blank=True
    )

    class Meta:
        verbose_name = "xodim"
        verbose_name_plural = "xodimlar"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(color__regex=HEX_COLOR_RE), name="provider_color_hex"
            ),
        ]

    def __str__(self):
        return self.name


class ProviderService(BaseModel):
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="offerings")
    service = models.ForeignKey(
        "catalog.Service", on_delete=models.CASCADE, related_name="offerings"
    )

    class Meta:
        verbose_name = "xodim xizmati"
        verbose_name_plural = "xodim xizmatlari"
        constraints = [
            models.UniqueConstraint(fields=["provider", "service"], name="uniq_provider_service"),
        ]

    def __str__(self):
        return f"{self.provider} — {self.service}"
