from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.api.permissions import IsAdminOrReadOnly, is_admin
from apps.api.utils import flag_query_param, uuid_or_404
from apps.api.v1.serializers.catalog import ServiceAdminSerializer, ServiceSerializer
from apps.catalog import selectors, services


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
        services.deactivate_service(service=self._get(pk, include_inactive=True))
        return Response(status=status.HTTP_204_NO_CONTENT)
