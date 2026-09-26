from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import IsAdmin, is_admin
from apps.api.v1.serializers.scheduling import SettingsAdminSerializer, SettingsPublicSerializer
from apps.scheduling import services
from apps.scheduling.models import BusinessSettings


class SettingsView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAdmin()]

    def get(self, request):
        serializer_class = (
            SettingsAdminSerializer if is_admin(request.user) else SettingsPublicSerializer
        )
        return Response(serializer_class(BusinessSettings.load()).data)

    def patch(self, request):
        serializer = SettingsAdminSerializer(
            BusinessSettings.load(), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        obj = services.update_settings(**serializer.validated_data)
        return Response(SettingsAdminSerializer(obj).data)
