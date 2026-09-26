from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.api.permissions import IsAdminOrReadOnly, is_admin
from apps.api.schema import UUID_PATH, problems
from apps.api.utils import flag_query_param, uuid_or_404
from apps.api.v1.serializers.bookings import DeactivationSerializer, deactivation_payload
from apps.api.v1.serializers.catalog import ServiceAdminSerializer, ServiceSerializer
from apps.bookings import selectors as booking_selectors
from apps.catalog import selectors, services

INCLUDE_INACTIVE = OpenApiParameter(
    "include_inactive", OpenApiTypes.BOOL, description="Faqat admin: nofaollarni ham koʻrsatish."
)
ADMIN_ONLY = problems(s401="AUTH_REQUIRED", s403="FORBIDDEN")


@extend_schema_view(
    list=extend_schema(
        summary="Faol xizmatlar",
        description="Admin uchun javobda qoʻshimcha `is_active`, `sort_order`, vaqt maydonlari.",
        parameters=[INCLUDE_INACTIVE],
        responses={200: ServiceSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Xizmat",
        parameters=[UUID_PATH],
        responses={200: ServiceSerializer, **problems(s404="NOT_FOUND")},
    ),
    create=extend_schema(
        summary="Xizmat yaratish (admin)",
        request=ServiceAdminSerializer,
        responses={201: ServiceAdminSerializer, **problems(s422="VALIDATION_ERROR"), **ADMIN_ONLY},
    ),
    partial_update=extend_schema(
        summary="Xizmatni tahrirlash (admin)",
        description="Narx/davomiylik oʻzgarishi faqat yangi bronlarga taʼsir qiladi (snapshot).",
        parameters=[UUID_PATH],
        request=ServiceAdminSerializer,
        responses={
            200: ServiceAdminSerializer,
            **problems(s404="NOT_FOUND", s422="VALIDATION_ERROR"),
            **ADMIN_ONLY,
        },
    ),
    destroy=extend_schema(
        summary="Xizmatni deaktivatsiya qilish (admin)",
        description="Hech qachon oʻchirilmaydi: `is_active=false`. Kelgusi faol bronlar saqlanadi "
        "va javobda roʻyxat sifatida qaytadi.",
        parameters=[UUID_PATH],
        responses={200: DeactivationSerializer, **problems(s404="NOT_FOUND"), **ADMIN_ONLY},
    ),
)
@extend_schema(tags=["services"])
class ServiceViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminOrReadOnly]

    def _admin(self) -> bool:
        return is_admin(self.request.user)

    def _serializer_class(self):
        return ServiceAdminSerializer if self._admin() else ServiceSerializer

    def _get(self, pk, *, include_inactive: bool):
        service = selectors.service_get(pk=uuid_or_404(pk), include_inactive=include_inactive)
        if service is None:
            raise NotFound()
        return service

    def list(self, request):
        include_inactive = self._admin() and flag_query_param(request, "include_inactive")
        qs = selectors.service_list(include_inactive=include_inactive)
        return Response(self._serializer_class()(qs, many=True).data)

    def retrieve(self, request, pk=None):
        service = self._get(pk, include_inactive=self._admin())
        return Response(self._serializer_class()(service).data)

    def create(self, request):
        serializer = ServiceAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = services.create_service(**serializer.validated_data)
        return Response(ServiceAdminSerializer(service).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        service = self._get(pk, include_inactive=True)
        serializer = ServiceAdminSerializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        service = services.update_service(service=service, **serializer.validated_data)
        return Response(ServiceAdminSerializer(service).data)

    def destroy(self, request, pk=None):
        service = services.deactivate_service(service=self._get(pk, include_inactive=True))
        upcoming = list(booking_selectors.upcoming_active(now=timezone.now(), service=service))
        return Response(deactivation_payload(service, upcoming))
