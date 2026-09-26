from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services
from apps.accounts.models import User, normalize_email, phone_validator
from apps.common.utils.time import validate_timezone


class UserSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(
        max_length=13, allow_blank=True, required=False, validators=[phone_validator]
    )
    timezone = serializers.CharField(max_length=64, required=False, validators=[validate_timezone])

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role", "timezone", "created_at"]
        read_only_fields = ["id", "email", "role", "created_at"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    full_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(
        max_length=13, allow_blank=True, required=False, default="", validators=[phone_validator]
    )

    def validate_email(self, value):
        email = normalize_email(value)
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Bu email bilan akkaunt allaqachon mavjud.")
        return email

    def validate(self, attrs):
        candidate = User(email=attrs["email"], full_name=attrs["full_name"])
        try:
            password_validation.validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class TokenObtainSerializer(TokenObtainPairSerializer):
    default_error_messages = {"no_active_account": "Email yoki parol notoʻgʻri."}

    @classmethod
    def get_token(cls, user):
        return services.issue_tokens(user)


class TokenRotateSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except TokenError:
            self._revoke_family_on_reuse(attrs["refresh"])
            raise

    @staticmethod
    def _revoke_family_on_reuse(raw: str) -> None:
        # A signature-valid, unexpired refresh token that is already blacklisted can only be
        # a replay of a rotated token: treat the session as stolen.
        try:
            payload = token_backend.decode(raw, verify=True)
        except Exception:
            return
        if payload.get(jwt_settings.TOKEN_TYPE_CLAIM) != "refresh":
            return
        jti = payload.get(jwt_settings.JTI_CLAIM)
        family = payload.get(services.FAMILY_CLAIM)
        if family and BlacklistedToken.objects.filter(token__jti=jti).exists():
            services.revoke_token_family(
                user_id=payload.get(jwt_settings.USER_ID_CLAIM), family=family
            )


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        user = self.context["request"].user
        if str(token.get(jwt_settings.USER_ID_CLAIM)) != str(user.pk):
            raise InvalidToken("Token boshqa foydalanuvchiga tegishli.")
        return token
