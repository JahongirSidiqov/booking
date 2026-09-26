from rest_framework import serializers

from apps.common.utils.time import validate_timezone


class _SlotQueryBase(serializers.Serializer):
    service = serializers.UUIDField()
    provider = serializers.UUIDField()
    tz = serializers.CharField(max_length=64, required=False, validators=[validate_timezone])


class SlotsQuerySerializer(_SlotQueryBase):
    date = serializers.DateField(input_formats=["%Y-%m-%d"])


class DaysQuerySerializer(_SlotQueryBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # "from" is a Python keyword, so these fields cannot be declared as attributes.
        self.fields["from"] = serializers.DateField(input_formats=["%Y-%m-%d"])
        self.fields["to"] = serializers.DateField(input_formats=["%Y-%m-%d"])
