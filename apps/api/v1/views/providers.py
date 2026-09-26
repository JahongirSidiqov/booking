from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.api.permissions import IsAdmin, IsAdminOrReadOnly, IsProviderOwnerOrAdmin, is_admin
from apps.api.utils import flag_query_param, uuid_or_404, uuid_query_param
from apps.api.v1.serializers.bookings import deactivation_payload
from apps.api.v1.serializers.providers import (
    ProviderAdminSerializer,
    ProviderSerializer,
    ProviderServicesSerializer,
)
from apps.api.v1.serializers.scheduling import (
    AvailabilityInputSerializer,
    RuleSerializer,
    TimeOffSerializer,
)
from apps.bookings import selectors as booking_selectors
from apps.providers import selectors, services
from apps.scheduling import selectors as scheduling_selectors
from apps.scheduling import services as scheduling_services
from apps.scheduling.models import BusinessSettings


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
        rules = scheduling_selectors.availability_rules(provider=provider)
        return Response(
            {
                "provider_id": str(provider.pk),
                "timezone": scheduling_selectors.provider_timezone(
                    provider, BusinessSettings.load()
                ),
                "rules": RuleSerializer(rules, many=True).data,
            }
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
