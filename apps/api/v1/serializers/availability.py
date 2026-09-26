from zoneinfo import ZoneInfo

from rest_framework import serializers

from apps.common.utils.time import validate_timezone

# --- query parameters ---------------------------------------------------------------------


class _SlotQueryBase(serializers.Serializer):
    service = serializers.UUIDField()
    provider = serializers.UUIDField()
    tz = serializers.CharField(
        max_length=64,
        required=False,
        validators=[validate_timezone],
        help_text="IANA zona. Yoʻq boʻlsa: foydalanuvchi profili, keyin biznes zonasi.",
    )


class SlotsQuerySerializer(_SlotQueryBase):
    date = serializers.DateField(
        input_formats=["%Y-%m-%d"], help_text="Mijoz zonasidagi kun (YYYY-MM-DD)."
    )


class DaysQuerySerializer(_SlotQueryBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # "from" is a Python keyword, so these fields cannot be declared as attributes.
        self.fields["from"] = serializers.DateField(input_formats=["%Y-%m-%d"])
        self.fields["to"] = serializers.DateField(
            input_formats=["%Y-%m-%d"], help_text="Inklyuziv; oraliq 31 kundan oshmasin."
        )


# --- responses ----------------------------------------------------------------------------


class ServiceBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)


class ProviderBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class SlotSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    start_local = serializers.SerializerMethodField(help_text="HH:MM, soʻrovdagi zonada.")
    end_local = serializers.SerializerMethodField()

    def get_start_local(self, slot) -> str:
        return slot.start_at.astimezone(ZoneInfo(self.context["tz"])).strftime("%H:%M")

    def get_end_local(self, slot) -> str:
        return slot.end_at.astimezone(ZoneInfo(self.context["tz"])).strftime("%H:%M")


class SlotsResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    timezone = serializers.CharField()
    service = ServiceBriefSerializer()
    provider = ProviderBriefSerializer()
    slots = SlotSerializer(many=True)


class DayCountSerializer(serializers.Serializer):
    date = serializers.DateField()
    available = serializers.IntegerField(help_text="Shu kundagi boʻsh slotlar soni.")


class DaysResponseSerializer(serializers.Serializer):
    timezone = serializers.CharField()
    service = ServiceBriefSerializer()
    provider = ProviderBriefSerializer()
    days = DayCountSerializer(many=True)

    def get_fields(self):
        fields = super().get_fields()
        fields["from"] = serializers.DateField(source="date_from")
        fields["to"] = serializers.DateField(source="date_to")
        order = ("from", "to", "timezone", "service", "provider", "days")
        return {name: fields[name] for name in order}
