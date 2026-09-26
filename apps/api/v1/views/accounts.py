from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import services
from apps.api.schema import problems
from apps.api.v1.serializers.accounts import (
    LogoutSerializer,
    RegisterSerializer,
    TokenObtainSerializer,
    TokenRotateSerializer,
    UserSerializer,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["auth"],
        summary="Mijoz sifatida roʻyxatdan oʻtish",
        request=RegisterSerializer,
        responses={201: UserSerializer, **problems(s422="VALIDATION_ERROR", s429="THROTTLED")},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_customer(**serializer.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=extend_schema(
        tags=["auth"],
        summary="Login: access (15 daq) + refresh (7 kun)",
        responses={
            200: TokenObtainSerializer,
            **problems(s401="AUTH_REQUIRED", s429="THROTTLED (10/daq, IP)"),
        },
    )
)
class TokenObtainView(TokenObtainPairView):
    serializer_class = TokenObtainSerializer
    throttle_classes = [ScopedRateThrottle, AnonRateThrottle]
    throttle_scope = "auth_token"


@extend_schema_view(
    post=extend_schema(
        tags=["auth"],
        summary="Refresh rotation: eski refresh blacklist'ga tushadi",
        description="Blacklist'dagi refresh qayta ishlatilsa, shu login oilasi butunlay bekor "
        "qilinadi (TASK edge #30).",
        responses={200: TokenRotateSerializer, **problems(s401="AUTH_REQUIRED")},
    )
)
class TokenRefreshRotateView(TokenRefreshView):
    serializer_class = TokenRotateSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Chiqish: refresh token blacklist'ga",
        request=LogoutSerializer,
        responses={204: None, **problems(s401="AUTH_REQUIRED")},
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.logout(refresh=serializer.validated_data["refresh"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["auth"], summary="Profil", responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        tags=["auth"],
        summary="Profilni yangilash (ism, telefon, timezone)",
        request=UserSerializer,
        responses={200: UserSerializer, **problems(s422="VALIDATION_ERROR")},
    )
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = services.update_profile(user=request.user, **serializer.validated_data)
        return Response(UserSerializer(user).data)
