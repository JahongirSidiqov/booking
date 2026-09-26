from rest_framework import serializers

from apps.api.fields import AwareDateTimeField
from apps.common.utils.time import validate_timezone
from apps.scheduling.models import SLOT_STEP_CHOICES, BusinessSettings, TimeOff

MAX_RULES_PER_WEEK = 7 * 6


class RuleSerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    start_time = serializers.TimeField(format="%H:%M")
    end_time = serializers.TimeField(format="%H:%M")

    def validate(self, attrs):
        start, end = attrs["start_time"], attrs["end_time"]
        for name in ("start_time", "end_time"):
            if attrs[name].second or attrs[name].microsecond:
                raise serializers.ValidationError({name: "Vaqt soniyasiz boʻlsin (HH:MM)."})
        if end < start:
            raise serializers.ValidationError(
                {
                    "end_time": "Yarim tundan oʻtuvchi smena qoʻllab-quvvatlanmaydi. "
                    "Uni ikki kunga boʻling (masalan 22:00–23:55 va ertasi 00:00–02:00)."
                }
            )
        if end == start:
            raise serializers.ValidationError(
                {"end_time": "Tugash vaqti boshlanishdan keyin boʻlsin."}
            )
        return attrs


class AvailabilityInputSerializer(serializers.Serializer):
    rules = RuleSerializer(many=True, allow_empty=True, max_length=MAX_RULES_PER_WEEK)


class TimeOffSerializer(serializers.ModelSerializer):
    start_at = AwareDateTimeField()
    end_at = AwareDateTimeField()
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    class Meta:
        model = TimeOff
        fields = ["id", "start_at", "end_at", "reason", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        if attrs["start_at"] >= attrs["end_at"]:
            raise serializers.ValidationError(
                {"end_at": "Tugash vaqti boshlanishdan keyin boʻlsin."}
            )
        return attrs


class SettingsPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessSettings
        fields = [
            "name",
            "timezone",
            "currency",
            "slot_step_minutes",
            "min_lead_time_minutes",
            "max_advance_days",
            "cancellation_deadline_hours",
        ]
        read_only_fields = fields


class SettingsAdminSerializer(serializers.ModelSerializer):
    timezone = serializers.CharField(max_length=64, validators=[validate_timezone])
    currency = serializers.RegexField(r"^[A-Z]{3}$", max_length=3)
    slot_step_minutes = serializers.ChoiceField(choices=SLOT_STEP_CHOICES)
    min_lead_time_minutes = serializers.IntegerField(min_value=0, max_value=60 * 24 * 7)
    max_advance_days = serializers.IntegerField(min_value=1, max_value=365)
    cancellation_deadline_hours = serializers.IntegerField(min_value=0, max_value=24 * 14)

    class Meta:
        model = BusinessSettings
        fields = [*SettingsPublicSerializer.Meta.fields, "auto_confirm", "updated_at"]
        read_only_fields = ["updated_at"]
