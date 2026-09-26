from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.common.models import BaseModel
from apps.common.utils.time import validate_timezone

phone_validator = RegexValidator(
    regex=r"^\+998\d{9}$",
    message="Telefon raqami +998XXXXXXXXX koʻrinishida boʻlishi kerak.",
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        # Emails are stored lowercased, so login must be case-insensitive too.
        return self.get(**{self.model.USERNAME_FIELD: normalize_email(username)})

    def _create_user(self, email, password, **extra_fields):
        email = normalize_email(email)
        if not email:
            raise ValueError("Email majburiy.")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser is_staff=True va is_superuser=True boʻlishi kerak.")
        return self._create_user(email, password, **extra_fields)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Mijoz"
        PROVIDER = "provider", "Xodim"
        ADMIN = "admin", "Administrator"

    email = models.EmailField("email", unique=True)
    full_name = models.CharField("toʻliq ism", max_length=120)
    phone = models.CharField("telefon", max_length=13, blank=True, validators=[phone_validator])
    role = models.CharField("rol", max_length=16, choices=Role.choices, default=Role.CUSTOMER)
    timezone = models.CharField(
        "vaqt zonasi", max_length=64, default=settings.DEFAULT_TZ, validators=[validate_timezone]
    )
    is_active = models.BooleanField("faol", default=True)
    is_staff = models.BooleanField("Django admin", default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "foydalanuvchi"
        verbose_name_plural = "foydalanuvchilar"
        ordering = ["email"]
        constraints = [
            # Uniqueness is case-insensitive only because every write stores the lowercase form.
            models.CheckConstraint(condition=Q(email=Lower("email")), name="user_email_lowercase"),
            models.CheckConstraint(
                condition=Q(role__in=["customer", "provider", "admin"]), name="user_role_valid"
            ),
        ]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = normalize_email(self.email)

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    @property
    def is_customer(self) -> bool:
        return self.role == self.Role.CUSTOMER

    @property
    def is_provider(self) -> bool:
        return self.role == self.Role.PROVIDER

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN
