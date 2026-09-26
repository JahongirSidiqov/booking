from rest_framework import serializers

from apps.api.v1.serializers.catalog import ServiceRefSerializer
from apps.common.utils.time import validate_timezone
from apps.providers.models import Provider, color_validator


class ProviderSerializer(serializers.ModelSerializer):
    services = ServiceRefSerializer(many=True, read_only=True)

    class Meta:
        model = Provider
        fields = ["id", "name", "bio", "color", "services"]


class ProviderAdminSerializer(serializers.ModelSerializer):
    services = ServiceRefSerializer(many=True, read_only=True)
    service_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )
    user_id = serializers.UUIDField(allow_null=True, required=False)
    color = serializers.CharField(max_length=7, required=False, validators=[color_validator])
    timezone = serializers.CharField(
        max_length=64, allow_null=True, required=False, validators=[validate_timezone]
    )

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "bio",
            "color",
            "timezone",
            "is_active",
            "user_id",
            "services",
            "service_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProviderServicesSerializer(serializers.Serializer):
    service_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)
