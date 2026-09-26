from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.api.permissions import IsAdmin, IsAdminOrReadOnly, IsProviderOwnerOrAdmin, is_admin
from apps.api.schema import TIME_OFF_PATH, UUID_PATH, problems
from apps.api.utils import flag_query_param, uuid_or_404, uuid_query_param
from apps.api.v1.serializers.bookings import DeactivationSerializer, deactivation_payload
from apps.api.v1.serializers.providers import (
    ProviderAdminSerializer,
    ProviderSerializer,
    ProviderServicesSerializer,
)
from apps.api.v1.serializers.scheduling import (
    AvailabilityInputSerializer,
    AvailabilityResponseSerializer,
    TimeOffSerializer,
)
from apps.bookings import selectors as booking_selectors
from apps.providers import selectors, services
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling import services as scheduling_services
from apps.scheduling.models import BusinessSettings

ADMIN_ONLY = problems(s401="AUTH_REQUIRED", s403="FORBIDDEN")
MANAGE = problems(
    s401="AUTH_REQUIRED",
    s403="FORBIDDEN (faqat admin yoki shu xodimning oʻzi)",
    s404="NOT_FOUND",
)
CONFLICT = problems(s409="CONFLICTS_WITH_BOOKINGS (javobda `bookings` roʻyxati)")


@extend_schema_view(
    list=extend_schema(
        summary="Faol xodimlar",
        description="Admin uchun javobda qoʻshimcha `is_active`, `user_id`, `timezone`.",
        parameters=[
            OpenApiParameter("service", OpenApiTypes.UUID, description="Shu xizmatni koʻrsatadi."),
            OpenApiParameter("include_inactive", OpenApiTypes.BOOL, description="Faqat admin."),
        ],
        responses={200: ProviderSerializer(many=True), **problems(s422="VALIDATION_ERROR")},
    ),
    retrieve=extend_schema(
        summary="Xodim",
        parameters=[UUID_PATH],
        responses={200: ProviderSerializer, **problems(s404="NOT_FOUND")},
    ),
    create=extend_schema(
        summary="Xodim yaratish (admin)",
        request=ProviderAdminSerializer,
        responses={
            201: ProviderAdminSerializer,
            **problems(s422="VALIDATION_ERROR"),
            **ADMIN_ONLY,
        },
    ),
    partial_update=extend_schema(
        summary="Xodimni tahrirlash (admin)",
        parameters=[UUID_PATH],
        request=ProviderAdminSerializer,
        responses={
            200: ProviderAdminSerializer,
            **problems(s404="NOT_FOUND", s422="VALIDATION_ERROR"),
            **ADMIN_ONLY,
        },
    ),
    destroy=extend_schema(
        summary="Xodimni deaktivatsiya qilish (admin)",
        description="`is_active=false`; kelgusi bronlar saqlanadi va roʻyxat sifatida qaytadi.",
        parameters=[UUID_PATH],
        responses={200: DeactivationSerializer, **problems(s404="NOT_FOUND"), **ADMIN_ONLY},
    ),
)
@extend_schema(tags=["providers"])
class ProviderViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminOrReadOnly]

    def _admin(self) -> bool:
        return is_admin(self.request.user)

    def _serializer_class(self):
        return ProviderAdminSerializer if self._admin() else ProviderSerializer

    def _get(self, pk, *, include_inactive: bool):
        provider = selectors.provider_get(pk=uuid_or_404(pk), include_inactive=include_inactive)
        if provider is None:
            raise NotFound()
        return provider

    def list(self, request):
        include_inactive = self._admin() and flag_query_param(request, "include_inactive")
        qs = selectors.provider_list(
            service_id=uuid_query_param(request, "service"), include_inactive=include_inactive
        )
        return Response(self._serializer_class()(qs, many=True).data)

    def retrieve(self, request, pk=None):
        provider = self._get(pk, include_inactive=self._admin())
        return Response(self._serializer_class()(provider).data)

    def create(self, request):
        serializer = ProviderAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = services.create_provider(**serializer.validated_data)
        provider = self._get(provider.pk, include_inactive=True)
        return Response(ProviderAdminSerializer(provider).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        provider = self._get(pk, include_inactive=True)
        serializer = ProviderAdminSerializer(provider, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        service_ids = data.pop("service_ids", None)
        services.update_provider(provider=provider, **data)
        if service_ids is not None:
            services.set_provider_services(provider=provider, service_ids=service_ids)
        provider = self._get(pk, include_inactive=True)
        return Response(ProviderAdminSerializer(provider).data)

    def destroy(self, request, pk=None):
        provider = services.deactivate_provider(provider=self._get(pk, include_inactive=True))
        upcoming = list(booking_selectors.upcoming_active(now=timezone.now(), provider=provider))
        return Response(deactivation_payload(provider, upcoming))

    @extend_schema(
        summary="Xodim xizmatlarini butunlay almashtirish (admin)",
        parameters=[UUID_PATH],
        request=ProviderServicesSerializer,
        responses={
            200: ProviderAdminSerializer,
            **problems(s404="NOT_FOUND", s422="VALIDATION_ERROR"),
            **ADMIN_ONLY,
        },
    )
    @action(detail=True, methods=["put"], url_path="services", permission_classes=[IsAdmin])
    def replace_services(self, request, pk=None):
        provider = self._get(pk, include_inactive=True)
        serializer = ProviderServicesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_provider_services(
            provider=provider, service_ids=serializer.validated_data["service_ids"]
        )
        provider = self._get(pk, include_inactive=True)
        return Response(ProviderAdminSerializer(provider).data)

    # --- schedule management (admin, or the provider's own linked user) --------------------

    def _managed(self, request, pk):
        provider = self._get(pk, include_inactive=True)
        self.check_object_permissions(request, provider)
        return provider

    def _availability_response(self, provider):
        data = {
            "provider": provider,
            "timezone": scheduling_selectors.provider_timezone(provider, BusinessSettings.load()),
            "rules": scheduling_selectors.availability_rules(provider=provider),
        }
        return Response(AvailabilityResponseSerializer(data).data)

    @extend_schema(
        methods=["GET"],
        summary="Haftalik ish vaqti",
        parameters=[UUID_PATH],
        responses={200: AvailabilityResponseSerializer, **MANAGE},
    )
    @extend_schema(
        methods=["PUT"],
        summary="Haftalik ish vaqtini butunlay almashtirish",
        description="Bir kunda oraliqlar kesishmasin; yarim tundan oʻtuvchi smena yoʻq (ADR-004). "
        "Yangi jadvaldan tashqarida qoladigan faol bron boʻlsa — 409 (ADR-005).",
        parameters=[UUID_PATH],
        request=AvailabilityInputSerializer,
        responses={
            200: AvailabilityResponseSerializer,
            **problems(s422="VALIDATION_ERROR"),
            **CONFLICT,
            **MANAGE,
        },
    )
    @action(
        detail=True,
        methods=["get", "put"],
        url_path="availability",
        permission_classes=[IsProviderOwnerOrAdmin],
    )
    def availability(self, request, pk=None):
        provider = self._managed(request, pk)
        if request.method == "PUT":
            serializer = AvailabilityInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            scheduling_services.replace_availability(
                provider=provider, rules=serializer.validated_data["rules"]
            )
        return self._availability_response(provider)

    @extend_schema(
        methods=["GET"],
        summary="Dam olish / taʼtil roʻyxati",
        parameters=[
            UUID_PATH,
            OpenApiParameter("include_past", OpenApiTypes.BOOL, description="Oʻtganlarini ham."),
        ],
        responses={200: TimeOffSerializer(many=True), **MANAGE},
    )
    @extend_schema(
        methods=["POST"],
        summary="Dam olish qoʻshish",
        description="Faol bron bilan kesishsa — 409 va bronlar roʻyxati (ADR-005).",
        parameters=[UUID_PATH],
        request=TimeOffSerializer,
        responses={
            201: TimeOffSerializer,
            **problems(s422="VALIDATION_ERROR"),
            **CONFLICT,
            **MANAGE,
        },
    )
    @action(
        detail=True,
        methods=["get", "post"],
        url_path="time-off",
        permission_classes=[IsProviderOwnerOrAdmin],
    )
    def time_off(self, request, pk=None):
        provider = self._managed(request, pk)
        if request.method == "POST":
            serializer = TimeOffSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            item = scheduling_services.add_time_off(provider=provider, **serializer.validated_data)
            return Response(TimeOffSerializer(item).data, status=status.HTTP_201_CREATED)
        items = scheduling_selectors.time_off_list(
            provider=provider,
            now=timezone.now(),
            include_past=flag_query_param(request, "include_past"),
        )
        return Response(TimeOffSerializer(items, many=True).data)

    @extend_schema(
        summary="Dam olishni oʻchirish",
        parameters=[UUID_PATH, TIME_OFF_PATH],
        responses={204: None, **MANAGE},
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"time-off/(?P<time_off_id>[^/.]+)",
        permission_classes=[IsProviderOwnerOrAdmin],
    )
    def time_off_detail(self, request, pk=None, time_off_id=None):
        provider = self._managed(request, pk)
        scheduling_services.delete_time_off(provider=provider, time_off_id=uuid_or_404(time_off_id))
        return Response(status=status.HTTP_204_NO_CONTENT)
