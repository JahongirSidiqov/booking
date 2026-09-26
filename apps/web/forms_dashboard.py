"""Dashboard forms: shape validation only; business rules are enforced by the services."""

from decimal import Decimal
from zoneinfo import ZoneInfo

from django import forms
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.catalog.models import (
    BUFFER_MAX,
    DURATION_MAX,
    DURATION_MIN,
    DURATION_STEP,
    Service,
)
from apps.providers.models import Provider, color_validator
from apps.scheduling.models import SLOT_STEP_CHOICES
from apps.web.forms import StyledFormMixin, timezone_choices

DATETIME_LOCAL = "%Y-%m-%dT%H:%M"


class BookingFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(label="Qidiruv", required=False, max_length=100)
    status = forms.ChoiceField(
        label="Holat", required=False, choices=[("", "Barchasi"), *Booking.Status.choices]
    )
    provider = forms.ChoiceField(label="Xodim", required=False)
    date_from = forms.DateField(
        label="Sanadan", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        label="Sanagacha", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, providers=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "Barchasi")] + [(str(p.pk), p.name) for p in providers or []]
        self.fields["provider"].choices = choices

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and end < start:
            self.add_error("date_to", "Tugash sanasi boshlanishdan oldin boʻlmasin.")
        return cleaned


class StaffCancelForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(
        label="Sabab",
        max_length=500,
        help_text="Mijozga koʻrsatiladi.",
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 500}),
    )


class ServiceForm(StyledFormMixin, forms.Form):
    # autofocus: showModal() focuses the first focusable element, which would be the close
    # button; the first field is what the admin wants to type into.
    name = forms.CharField(
        label="Nomi", max_length=100, widget=forms.TextInput(attrs={"autofocus": True})
    )
    slug = forms.SlugField(
        label="Slug (URL)",
        max_length=120,
        required=False,
        help_text="Boʻsh qoldirilsa, nomdan yasaladi.",
    )
    description = forms.CharField(
        label="Tavsif", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    duration_minutes = forms.IntegerField(
        label="Davomiyligi (daqiqa)",
        min_value=DURATION_MIN,
        max_value=DURATION_MAX,
        widget=forms.NumberInput(attrs={"step": DURATION_STEP, "inputmode": "numeric"}),
    )
    price = forms.DecimalField(
        label="Narxi (soʻm)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"step": "1000", "inputmode": "decimal"}),
    )
    buffer_after_minutes = forms.IntegerField(
        label="Tanaffus (daqiqa)",
        min_value=0,
        max_value=BUFFER_MAX,
        initial=0,
        help_text="Har bron keyin xodim band boʻladi (tozalash). Mijozga koʻrinmaydi.",
        widget=forms.NumberInput(attrs={"step": DURATION_STEP, "inputmode": "numeric"}),
    )
    sort_order = forms.IntegerField(label="Tartib", min_value=0, initial=0)
    is_active = forms.BooleanField(label="Faol (mijozlarga koʻrinadi)", required=False)

    def clean_buffer_after_minutes(self):
        value = self.cleaned_data["buffer_after_minutes"]
        if value % DURATION_STEP:
            raise forms.ValidationError(f"Tanaffus {DURATION_STEP} ga karrali boʻlsin.")
        return value

    def clean_duration_minutes(self):
        value = self.cleaned_data["duration_minutes"]
        if value % DURATION_STEP:
            raise forms.ValidationError(f"Davomiylik {DURATION_STEP} ga karrali boʻlsin.")
        return value


class ProviderForm(StyledFormMixin, forms.Form):
    name = forms.CharField(
        label="Ismi", max_length=100, widget=forms.TextInput(attrs={"autofocus": True})
    )
    bio = forms.CharField(
        label="Qisqacha", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    color = forms.CharField(
        label="Kalendar rangi",
        max_length=7,
        validators=[color_validator],
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    timezone = forms.ChoiceField(label="Vaqt zonasi", required=False)
    user = forms.ModelChoiceField(
        label="Tizimga kiradigan foydalanuvchi",
        required=False,
        queryset=User.objects.none(),
        empty_label="— bogʻlanmagan (faqat admin boshqaradi) —",
    )
    services = forms.ModelMultipleChoiceField(
        label="Koʻrsatadigan xizmatlari",
        required=False,
        queryset=Service.objects.order_by("sort_order", "name"),
        widget=forms.CheckboxSelectMultiple,
    )
    is_active = forms.BooleanField(label="Faol (bron qabul qiladi)", required=False)

    def __init__(self, *args, provider: Provider | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["timezone"].choices = [("", "Biznes zonasi"), *timezone_choices()]
        linked = Provider.objects.exclude(user=None)
        if provider is not None:
            linked = linked.exclude(pk=provider.pk)
        self.fields["user"].queryset = (
            User.objects.filter(role=User.Role.PROVIDER)
            .exclude(pk__in=linked.values("user_id"))
            .order_by("full_name")
        )


class RuleForm(forms.Form):
    """One working window of one weekday (the grid posts several)."""

    weekday = forms.IntegerField(min_value=0, max_value=6)
    start_time = forms.TimeField(input_formats=["%H:%M"])
    end_time = forms.TimeField(input_formats=["%H:%M"])

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end:
            if end < start:
                raise forms.ValidationError(
                    "Yarim tundan oʻtuvchi smena qoʻllab-quvvatlanmaydi — ikki kunga boʻling."
                )
            if end == start:
                raise forms.ValidationError("Tugash vaqti boshlanishdan keyin boʻlsin.")
        return cleaned


class TimeOffForm(StyledFormMixin, forms.Form):
    start_at = forms.DateTimeField(
        label="Boshlanishi",
        input_formats=[DATETIME_LOCAL],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL),
    )
    end_at = forms.DateTimeField(
        label="Tugashi",
        input_formats=[DATETIME_LOCAL],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL),
    )
    reason = forms.CharField(label="Sabab (ixtiyoriy)", required=False, max_length=200)

    def __init__(self, *args, tz: str, **kwargs):
        self.tz = tz
        super().__init__(*args, **kwargs)

    def _aware(self, value):
        # datetime-local has no offset: it is the provider's wall clock, stated next to the form.
        naive = timezone.make_naive(value) if timezone.is_aware(value) else value
        return naive.replace(tzinfo=ZoneInfo(self.tz))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start_at") and cleaned.get("end_at"):
            cleaned["start_at"] = self._aware(cleaned["start_at"])
            cleaned["end_at"] = self._aware(cleaned["end_at"])
            if cleaned["end_at"] <= cleaned["start_at"]:
                self.add_error("end_at", "Tugash vaqti boshlanishdan keyin boʻlsin.")
        return cleaned


class SettingsForm(StyledFormMixin, forms.Form):
    name = forms.CharField(label="Biznes nomi", max_length=120)
    timezone = forms.ChoiceField(label="Vaqt zonasi")
    currency = forms.RegexField(label="Valyuta", regex=r"^[A-Z]{3}$", max_length=3)
    slot_step_minutes = forms.TypedChoiceField(
        label="Slot qadami", coerce=int, choices=SLOT_STEP_CHOICES
    )
    min_lead_time_minutes = forms.IntegerField(
        label="Eng kam oldindan (daqiqa)",
        min_value=0,
        max_value=60 * 24 * 7,
        help_text="Hozirdan kamida shuncha keyingi vaqtga bron qilish mumkin.",
    )
    max_advance_days = forms.IntegerField(
        label="Eng koʻp oldindan (kun)", min_value=1, max_value=365
    )
    cancellation_deadline_hours = forms.IntegerField(
        label="Bekor qilish muddati (soat)",
        min_value=0,
        max_value=24 * 14,
        help_text="Mijoz uchrashuvdan shuncha soat oldingacha bepul bekor qila oladi.",
    )
    auto_confirm = forms.BooleanField(label="Yangi bronlarni avtomatik tasdiqlash", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["timezone"].choices = timezone_choices()
