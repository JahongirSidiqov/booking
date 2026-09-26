from rest_framework import status, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.accounts.models import User
from apps.api.v1.serializers.bookings import (
    BookingCreateSerializer,
    booking_payload,
    validate_idempotency_key,
)
from apps.api.v1.views.availability import resolve_tz
from apps.bookings import selectors, services
from apps.scheduling.models import BusinessSettings


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.CUSTOMER)


class BookingCreateThrottle(UserRateThrottle):
    scope = "bookings_create"


class BookingViewSet(viewsets.ViewSet):
    permission_classes = [IsCustomer]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "create":
            throttles.append(BookingCreateThrottle())
        return throttles

    def create(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = validate_idempotency_key(request.headers.get("Idempotency-Key"))
        data = serializer.validated_data
        result = services.create_booking(
            customer=request.user,
            service_id=data["service_id"],
            provider_id=data["provider_id"],
            start_at=data["start_at"],
            note=data["note"],
            idempotency_key=key,
        )
        booking = selectors.booking_with_history(pk=result.booking.pk)
        body = booking_payload(
            booking, tz=resolve_tz(request, None), business=BusinessSettings.load()
        )
        if result.replayed:
            return Response(
                body, status=status.HTTP_200_OK, headers={"Idempotent-Replayed": "true"}
            )
        return Response(body, status=status.HTTP_201_CREATED)
