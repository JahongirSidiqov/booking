import re
import uuid
from zoneinfo import available_timezones

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import User, normalize_email, phone_validator
from apps.common.utils.time import validate_timezone

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class StyledFormMixin:
    """Adds the design-system input class and wires errors to inputs for screen readers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(
                field.widget, forms.HiddenInput | forms.CheckboxInput | forms.CheckboxSelectMultiple
            ):
                continue
            field.widget.attrs.setdefault("class", "input")
            if field.help_text:
                field.widget.attrs["aria-describedby"] = f"id_{name}-help"

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                attrs["aria-invalid"] = "true"
                attrs["aria-describedby"] = f"id_{name}-error"


def timezone_choices():
    return [(tz, tz.replace("_", " ")) for tz in sorted(available_timezones()) if "/" in tz]


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )
    password = forms.CharField(
        label="Parol",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    error_messages = {
        "invalid_login": "Email yoki parol notoʻgʻri.",
        "inactive": "Bu akkaunt faol emas.",
    }


class RegisterForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(
        label="Toʻliq ism",
        max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    email = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )
    phone = forms.CharField(
        label="Telefon",
        required=False,
        max_length=13,
        validators=[phone_validator],
        help_text="Ixtiyoriy. Masalan +998901234567",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    password = forms.CharField(
        label="Parol",
        strip=False,
        help_text="Kamida 8 belgi, faqat raqamlardan iborat boʻlmasin.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self):
        email = normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Bu email bilan akkaunt allaqachon mavjud.")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("email"):
            candidate = User(email=cleaned["email"], full_name=cleaned.get("full_name", ""))
            try:
                password_validation.validate_password(cleaned["password"], user=candidate)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class ProfileForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(label="Toʻliq ism", max_length=120)
    phone = forms.CharField(
        label="Telefon",
        required=False,
        max_length=13,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={"inputmode": "tel"}),
    )
    timezone = forms.ChoiceField(
        label="Vaqt zonasi",
        help_text="Bron vaqtlari shu zonada koʻrsatiladi.",
        validators=[validate_timezone],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["timezone"].choices = timezone_choices()


class BookingConfirmForm(StyledFormMixin, forms.Form):
    # A provider UUID, or "any" (cleaned to None): let the system pick a free provider.
    provider = forms.CharField(widget=forms.HiddenInput, max_length=36)
    start_at = forms.CharField(widget=forms.HiddenInput)
    idempotency_key = forms.CharField(widget=forms.HiddenInput, max_length=64)
    note = forms.CharField(
        label="Izoh (ixtiyoriy)",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 500}),
    )

    def clean_provider(self):
        raw = self.cleaned_data["provider"]
        if raw == "any":
            return None
        try:
            return uuid.UUID(raw)
        except ValueError as exc:
            raise forms.ValidationError("Xodim notoʻgʻri.") from exc

    def clean_start_at(self):
        raw = self.cleaned_data["start_at"]
        try:
            value = parse_datetime(raw)
        except ValueError:
            value = None
        if value is None or timezone.is_naive(value):
            raise forms.ValidationError("Vaqt notoʻgʻri. Qaytadan tanlang.")
        return value

    def clean_idempotency_key(self):
        key = self.cleaned_data["idempotency_key"]
        if not IDEMPOTENCY_KEY_RE.match(key):
            raise forms.ValidationError("Sahifani yangilab, qaytadan urinib koʻring.")
        return key


class CancelForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(
        label="Sabab (ixtiyoriy)",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 500}),
    )
