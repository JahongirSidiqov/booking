from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import DURATION_MAX, DURATION_MIN, DURATION_STEP, Service


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "slug", "description", "duration_minutes", "price"]


class ServiceAdminSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(max_length=120, required=False, allow_blank=True)
    duration_minutes = serializers.IntegerField(min_value=DURATION_MIN, max_value=DURATION_MAX)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "duration_minutes",
            "price",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"slug": {"validators": []}}

    def validate_duration_minutes(self, value):
        if value % DURATION_STEP:
            raise serializers.ValidationError(f"Davomiylik {DURATION_STEP} ga karrali boʻlsin.")
        return value


class ServiceRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "slug"]
