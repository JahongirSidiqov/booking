from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.api.permissions import IsAdmin, IsAdminOrReadOnly, is_admin
from apps.api.utils import flag_query_param, uuid_or_404, uuid_query_param
from apps.api.v1.serializers.providers import (
    ProviderAdminSerializer,
    ProviderSerializer,
    ProviderServicesSerializer,
)
from apps.providers import selectors, services


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
        services.deactivate_provider(provider=self._get(pk, include_inactive=True))
        return Response(status=status.HTTP_204_NO_CONTENT)

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
